
import asyncio
import kr8s.asyncio
import importlib
import inflect
import inspect
import logging
import pathlib
import sys
import yaml
from crossplane.function.proto.v1 import run_function_pb2 as fnv1

from . import (
    command,
    composite,
    function,
    protobuf,
)


class Command(command.Command):
    name = 'render'
    help = 'Render a function-pythonic Composition'

    @classmethod
    def add_parser_arguments(cls, parser):
        cls.add_function_arguments(parser)
        parser.add_argument(
            'composite',
            type=pathlib.Path,
            metavar='COMPOSITE',
            help='A YAML file containing the Composite resource to render, or kind:apiVersion:namespace:name of cluster Composite.',
        )
        parser.add_argument(
            'composition',
            type=pathlib.Path,
            nargs='?',
            metavar='COMPOSITION',
            help='A YAML file containing the Composition resource, or the complete path of a function-pythonic BaseComposite subclass.',
        )
        parser.add_argument(
            '--kube-context', '-k',
            metavar='CONTEXT',
            help='The kubectl context to use to obtain external resources from, such as required resources, connections, etc.'
        )
        parser.add_argument(
            '--context-files',
            action='append',
            default=[],
            metavar='KEY=PATH',
            help='Context key-value pairs to pass to the Function pipeline. Values must be files containing YAML/JSON.',
        )
        parser.add_argument(
            '--context-values',
            action='append',
            default=[],
            metavar='KEY=VALUE',
            help='Context key-value pairs to pass to the Function pipeline. Values must be YAML/JSON. Keys take precedence over --context-files.',
        )
        parser.add_argument(
            '--observed-resources', '-o',
            action='append',
            type=pathlib.Path,
            default=[],
            metavar='PATH',
            help='A YAML file or directory of YAML files specifying the observed state of composed resources.'
        )
        parser.add_argument(
            '--required-resources', '-e',
            action='append',
            type=pathlib.Path,
            default=[],
            metavar='PATH',
            help='A YAML file or directory of YAML files specifying required resources to pass to the Function pipeline.',
        )
        parser.add_argument(
            '--secret-store', '-s',
            action='append',
            type=pathlib.Path,
            default=[],
            metavar='PATH',
            help='A YAML file or directory of YAML files specifying Secrets to use to resolve connections and credentials.',
        )
        parser.add_argument(
            '--include-full-xr', '-x',
            action='store_true',
            help="Include a direct copy of the input XR's spedc and metadata fields in the rendered output.",
        )
        parser.add_argument(
            '--include-connection-xr',
            action='store_true',
            help="Include the Composite connection values in the rendered output as a resource of kind: Connection.",
        )
        parser.add_argument(
            '--include-function-results', '-r',
            action='store_true',
            help='Include informational and warning messages from Functions in the rendered output as resources of kind: Result.',
        )
        parser.add_argument(
            '--include-context', '-c',
            action='store_true',
            help='Include the context in the rendered output as a resource of kind: Context.',
        )

    def initialize(self):
        self.initialize_function()
        self.logger = logging.getLogger(__name__)
        self.inflect = inflect.engine()
        self.inflect.classical(all=False)

    async def run(self):
        if self.args.kube_context:
            self.kube_context = await kr8s.asyncio.api(context=self.args.kube_context)
        else:
            self.kube_context = None

        await self.setup_composite()
        await self.setup_composition()

        # Build up the RunFunctionRequest protobuf message used to call function-pythonic.
        self.request = protobuf.Message(None, 'request', fnv1.RunFunctionRequest.DESCRIPTOR, fnv1.RunFunctionRequest())
        self.setup_local_resources()
        await self.setup_observed_resources()

        # These will hold the response conditions and results.
        conditions = protobuf.List()
        results = protobuf.List()

        # Create a function-pythonic function runner used to run pipeline steps.
        runner = function.FunctionRunner(self.args.debug, self.args.render_unknowns, self.args.crossplane_v1)
        fatal = False

        # Process the composition pipeline steps.
        for step in self.composition.spec.pipeline:
            if step.functionRef.name != 'function-pythonic':
                print(f"Only function-pythonic functions can be run: {step.functionRef.name}", file=sys.stderr)
                sys.exit(1)
            if not step.input.step:
                step.input.step = step.step
            self.request.input = step.input

            # Supply step requested credentials.
            self.request.credentials()
            for credential in step.credentials:
                if credential.source == 'Secret' and credential.secretRef:
                    namespace = credential.secretRef.namespace
                    name = credential.secretRef.name
                    if namespace and name:
                        for secret in self.secrets:
                            if secret.metadata.namespace == namespace and secret.metadata.name == name:
                                data = self.request.credentials[credential.name].credential_data.data
                                data()
                                for key, value in secret.data:
                                    data[key] = protobuf.B64Decode(value)
                                break
                        else:
                            print(f"Step \"{step.step}\" secret not found: {namespace}/{name}", file=sys.stderr)
                            sys.exit(1)

            # Track what extra/required resources have been processed.
            requirements = protobuf.Message(None, 'requirements', fnv1.Requirements.DESCRIPTOR, fnv1.Requirements())
            for _ in range(5):
                # Fetch the step bootstrap resources specified.
                self.request.required_resources()
                for requirement in step.requirements.requiredResources:
                    await self.fetch_requireds(requirement.requirementName, requirement, self.request.required_resources)
                # Fetch the required resources requested.
                for name, selector in requirements.resources:
                    await self.fetch_requireds(name, selector, self.request.required_resources)
                # Fetch the now deprecated extra resources requested.
                self.request.extra_resources()
                for name, selector in requirements.extra_resources:
                    await self.fetch_requireds(name, selector, self.request.extra_resources)
                # Run the step using the function-pythonic function runner.
                response = protobuf.Message(
                    None,
                    'response',
                    fnv1.RunFunctionResponse.DESCRIPTOR,
                    await runner.RunFunction(self.request._message, None),
                )
                # All done if there is a fatal result.
                for result in response.results:
                    if result.severity == fnv1.Severity.SEVERITY_FATAL:
                        fatal = True
                        break
                # Copy the response context to the request context to use in subsequent steps.
                self.request.context = response.context
                # Exit this loop if the function has not requested additional extra/required resources.
                if response.requirements == requirements:
                    break
                # Establish the new set of requested extra/required resoruces.
                requirements = response.requirements

            # Copy the response desired state to the request desired state to use in subsequent steps.
            self.request.desired.resources()
            self.copy_resource(response.desired.composite, self.request.desired.composite)
            for name, resource in response.desired.resources:
                self.copy_resource(resource, self.request.desired.resources[name])

            # Collect the step's returned conditions.
            for condition in response.conditions:
                if condition.type not in ('Ready', 'Synced', 'Healthy'):
                    conditions[protobuf.append] = self.create_condition(condition.type, condition.status, condition.reason, condition.message)
            # Collect the step's returned results.
            for result in response.results:
                ix = len(results)
                results[ix].apiVersion = 'render.crossplane.io/v1beta1'
                results[ix].kind = 'Result'
                results[ix].step = step.step
                results[ix].severity = fnv1.Severity.Name(result.severity._value)
                if result.reason:
                    results[ix].reason = result.reason
                if result.message:
                    results[ix].message = result.message

            # All done if a fatal result was returned
            if fatal:
                break

        # Collect and format all the returned desired composed resources.
        resources = protobuf.List()
        unready = protobuf.List()
        prefix = self.composite.metadata.labels['crossplane.io/composite']
        if not prefix:
            prefix = self.composite.metadata.name
        for name, resource in self.request.desired.resources:
            if resource.ready == fnv1.Ready.READY_TRUE:
                ready = True
            elif resource.ready == fnv1.Ready.READY_FALSE:
                ready = False
            else:
                ready = None
            if not ready:
                unready[protobuf.append] = name
            resource = resource.resource
            observed = self.request.observed.resources[name].resource
            if observed:
                for key in ('namespace', 'generateName', 'name'):
                    if observed.metadata[key]:
                        resource.metadata[key] = observed.metadata[key]
            if not resource.metadata.name and not resource.metadata.generateName:
                resource.metadata.generateName = f"{prefix}-"
            if self.composite.metadata.namespace:
                resource.metadata.namespace = self.composite.metadata.namespace
            resource.metadata.annotations['crossplane.io/composition-resource-name'] = name
            resource.metadata.labels['crossplane.io/composite'] = prefix
            if self.composite.metadata.labels['crossplane.io/claim-name'] and self.composite.metadata.labels['crossplane.io/claim-namespace']:
                resource.metadata.labels['crossplane.io/claim-namespace'] = self.composite.metadata.labels['crossplane.io/claim-namespace']
                resource.metadata.labels['crossplane.io/claim-name'] = self.composite.metadata.labels['crossplane.io/claim-name']
            elif self.composite.spec.claimRef.namespace and self.composite.spec.claimRef.name:
                resource.metadata.labels['crossplane.io/claim-namespace'] = self.composite.spec.claimRef.namespace
                resource.metadata.labels['crossplane.io/claim-name'] = self.composite.spec.claimRef.name
            resource.metadata.ownerReferences[0].controller = True
            resource.metadata.ownerReferences[0].blockOwnerDeletion = True
            resource.metadata.ownerReferences[0].apiVersion = self.composite.apiVersion
            resource.metadata.ownerReferences[0].kind = self.composite.kind
            resource.metadata.ownerReferences[0].name = self.composite.metadata.name
            resource.metadata.ownerReferences[0].uid = ''
            resource.ready = ready
            resources[protobuf.append] = resource

        # Format the returned desired composite
        composite = protobuf.Map()
        for name, value in self.request.desired.composite.resource:
            composite[name] = value
        composite.apiVersion = self.request.observed.composite.resource.apiVersion
        composite.kind = self.request.observed.composite.resource.kind
        if self.args.include_full_xr:
            composite.metadata = self.request.observed.composite.resource.metadata
            del composite.metadata.managedFields
            if self.request.observed.composite.resource.spec:
                composite.spec = self.request.observed.composite.resource.spec
        else:
            if self.request.observed.composite.resource.metadata.namespace:
                composite.metadata.namespace = self.request.observed.composite.resource.metadata.namespace
            composite.metadata.name = self.request.observed.composite.resource.metadata.name
        # Add in the composite's status.conditions.
        if self.request.desired.composite.ready == fnv1.Ready.READY_FALSE:
            condition = self.create_condition('Ready', False, 'Creating')
        elif self.request.desired.composite.ready == fnv1.Ready.READY_UNSPECIFIED and len(unready):
            condition = self.create_condition('Ready', False, 'Creating', f"Unready resources: {','.join(str(name) for name in unready)}")
        else:
            condition = self.create_condition('Ready', True, 'Available')
        composite.status.conditions[protobuf.append] = condition
        for condition in conditions:
            composite.status.conditions[protobuf.append] = condition

        # Print the composite.
        print('---')
        print(str(composite), end='')

        # Print Composite connection if requested.
        if self.args.include_connection_xr:
            connection = protobuf.Map(
                apiVersion = 'render.crossplane.io/v1beta1',
                kind = 'Connection',
            )
            for key, value in self.request.desired.composite.connection_details:
                connection.values[key] = value
            print('---')
            print(str(connection), end='')

        # Print the composed resources.
        for resource in sorted(resources, key=lambda resource: str(resource.metadata.annotations['crossplane.io/composition-resource-name'])):
            print('---')
            print(str(resource), end='')

        # Print the results (AKA events) if requested.
        if self.args.include_function_results:
            for result in results:
                print('---')
                print(str(result), end='')

        # Print the final context if requested.
        if self.args.include_context:
            print('---')
            print(
                str(protobuf.Map(
                    apiVersion = 'render.crossplane.io/v1beta1',
                    kind = 'Context',
                    values = self.request.context,
                )),
                end='',
            )

    async def setup_composite(self):
        # Obtain the Composite to render.
        if self.args.composite.is_file():
            self.composite = protobuf.Yaml(self.args.composite.read_text())
            return
        if not self.kube_context:
            print(f"Composite \"{self.args.composite}\" is not a file", file=sys.stderr)
            sys.exit(1)
        composite = str(self.args.composite).split(':')
        if len(composite) == 3:
            namespace = None
        elif len(composite) == 4:
            if len(composite[2]):
                namespace = composite[2]
            else:
                namespace = None
        else:
            print(f"Composite \"{self.args.composite}\" is not kind:apiVersion:namespace:name", file=sys.stderr)
            sys.exit(1)
        self.composite = await self.kube_get(composite[0], composite[1], namespace, composite[-1])

    async def setup_composition(self):
        # Obtain the Composition that will be used to render the Composite.
        if self.composite.apiVersion in ('pythonic.crossplane.io/v1alpha1', 'pythonic.fortra.com/v1alpha1') and self.composite.kind == 'Composite':
            if self.args.composition:
                print('Composite type of "composite.pythonic.crossplane.io" does not use "composition" argument', file=sys.stderr)
                sys.exit(1)
            self.create_composition()
            return
        if not self.args.composition:
            if not self.kube_context:
                print('"composition" argument required', file=sys.stderr)
                sys.exit(1)
            if self.args.crossplane_v1:
                revision = self.composite.spec.compositionRevisionRef
            else:
                revision = self.composite.spec.crossplane.compositionRevisionRef
            if not revision.name:
                print('Composite does not contain a CompositionRevision name', file=sys.stderr)
                sys.exit(1)
            self.composition = await self.kube_get('CompositionRevision', 'apiextensions.crossplane.io/v1', None, str(revision.name))
            return
        if self.args.composition.is_file():
            composition = self.args.composition.read_text()
            if self.args.composition.suffix == '.py':
                self.create_composition(composition)
            else:
                self.composition = protobuf.Yaml(composition)
                if not len(self.composition.spec.pipeline):
                    print(f"Composition file does not contain any pipeline steps: {self.args.composition}", file=sys.stderr)
                    sys.exit(1)
            return
        composition = str(self.args.composition).rsplit('.', 1)
        if len(composition) == 1:
            print(f"Composition class name does not include module: {self.args.composition}", file=sys.stderr)
            sys.exit(1)
        try:
            module = importlib.import_module(composition[0])
        except Exception as e:
            print(e)
            print(f"Unable to import composition module: {composition[0]}", file=sys.stderr)
            sys.exit(1)
        clazz = getattr(module, composition[1], None)
        if not clazz:
            print(f"Composition class {composition[0]} does not define: {composition[1]}", file=sys.stderr)
            sys.exit(1)
        if not inspect.isclass(clazz):
            print(f"Composition class {self.args.composition} is not a class", file=sys.stderr)
            sys.exit(1)
        if not issubclass(clazz, composite.BaseComposite):
            print(f"Composition class {self.args.composition} is not a subclass of BaseComposite", file=sys.stderr)
            sys.exit(1)
        self.create_composition(self.args.composition)

    def setup_local_resources(self):
        # Load the request context with any specified command line options.
        for entry in self.args.context_files:
            key_path = entry.split('=', 1)
            if len(key_path) != 2:
                print(f"Invalid --context-files: {entry}", file=sys.stderr)
                sys.exit(1)
            path = pathlib.Path(key_path[1])
            if not path.is_file():
                print(f"Invalid --context-files {path} is not a file", file=sys.stderr)
                sys.exit(1)
            self.request.context[key_path[0]] = protobuf.Yaml(path.read_text())
        for entry in self.args.context_values:
            key_value = entry.split('=', 1)
            if len(key_value) != 2:
                print(f"Invalid --context-values: {entry}", file=sys.stderr)
                sys.exit(1)
            self.request.context[key_value[0]] = protobuf.Yaml(key_value[1])
        # Collect specified required/extra resources. Sort for stable order when processed.
        self.requireds = sorted(
            self.collect_resources(self.args.required_resources),
            key=lambda required: str(required.metadata.name),
        )
        # Collect specified connection and credential secrets.
        self.secrets = [
            secret
            for secret in self.collect_resources(self.args.secret_store)
            if secret.apiVersion == 'v1' and secret.kind == 'Secret'
        ]

    async def setup_observed_resources(self):
        # Establish the request observed composite.
        await self.setup_resource(self.composite, self.request.observed.composite)

        # Obtain observed resources if using external cluster
        if self.kube_context:
            async with asyncio.TaskGroup() as group:
                if self.args.crossplane_v1:
                    refs = self.composite.spec.resourceRefs
                else:
                    refs = self.composite.spec.crossplane.resourceRefs
                for ref in refs:
                    group.create_task(self.setup_observed_resource(ref))

        # Establish the manually configured observed resources.
        for resource in self.collect_resources(self.args.observed_resources):
            name = resource.metadata.annotations['crossplane.io/composition-resource-name']
            if name:
                await self.setup_resource(resource, self.request.observed.resources[name])

    async def setup_observed_resource(self, ref):
        if ref.namespace:
            namespace = str(ref.namespace)
        elif self.composite.metadata.namespace:
            namespace = str(self.composite.metadata.namespace)
        else:
            namespace = None
        source = await self.kube_get(
            str(ref.kind),
            str(ref.apiVersion),
            namespace,
            str(ref.name),
            False,
        )
        if source:
            name = source.metadata.annotations['crossplane.io/composition-resource-name']
            if name:
                resource = self.request.observed.resources[name]
                if not resource:
                    await self.setup_resource(source, resource)

    def create_composition(self, module=''):
        self.composition = protobuf.Map()
        self.composition.apiVersion = 'apiextensions.crossplane.io/v1'
        self.composition.kind = 'Composition'
        self.composition.metadata.name = 'function-pythonic-render'
        self.composition.spec.compositeTypeRef.apiVersion = self.composite.apiVersion
        self.composition.spec.compositeTypeRef.kind = self.composite.kind
        self.composition.spec.mode = 'Pipeline'
        self.composition.spec.pipeline[0].step = 'function-pythonic-render'
        self.composition.spec.pipeline[0].functionRef.name = 'function-pythonic'
        self.composition.spec.pipeline[0].input.apiVersion = 'pythonic.fn.crossplane.io/v1alpha1'
        self.composition.spec.pipeline[0].input.kind = 'Composite'
        self.composition.spec.pipeline[0].input.composite = str(module)

    def collect_resources(self, resources):
        files = []
        for resource in resources:
            if resource.is_file():
                files.append(resource)
            elif resource.is_dir():
                for file in resource.iterdir():
                    if file.suffix in ('.yaml', '.yml'):
                        files.append(file)
            else:
                print(f"Specified resource is not a file or a directory: {resource}", file=sys.stderr)
                sys.exit(1)
        for file in files:
            for document in yaml.safe_load_all(file.read_text()):
                yield protobuf.Value(None, None, document)

    async def setup_resource(self, source, resource):
        resource.resource = source
        namespace = source.spec.writeConnectionSecretToRef.namespace or source.metadata.namespace
        name = source.spec.writeConnectionSecretToRef.name
        if namespace and name:
            connection = None
            for secret in self.secrets:
                if secret.metadata.namespace == namespace and secret.metadata.name == name:
                    connection = secret
                    break
            else:
                if self.kube_context:
                    connection = await self.kube_get('Secret', 'v1', namespace, name, False)
            if connection:
                resource.connection_details()
                for key, value in connection.data:
                    resource.connection_details[key] = protobuf.B64Decode(value)

    async def fetch_requireds(self, name, selector, resources):
        if not name:
            return
        name = str(name)
        items = resources[name].items
        items() # Force this to get created
        for required in self.requireds:
            if selector.api_version == required.apiVersion and selector.kind == required.kind:
                if ((not selector.namespace and not required.metadata.namespace)
                    or (selector.namespace == required.metadata.namespace)
                    ):
                    if selector.match_name == required.metadata.name:
                        await self.setup_resource(required, items[protobuf.append])
                    elif selector.match_labels.labels:
                        for key, value in selector.match_labels.labels:
                            if value != required.metadata.labels[key]:
                                break
                        else:
                            await self.setup_resource(required, items[protobuf.append])
        if not len(items) and self.kube_context:
            if selector.match_name:
                required = await self.kube_get(selector.kind, selector.api_version, selector.namespace, selector.match_name, False)
                if required:
                    await self.setup_resource(required, items[protobuf.append])
            elif selector.match_labels.labels:
                for requiest in await kube_list(selector.kind, selector.api_version, selector.namespace, selector.match_labels.labels):
                    await self.setup_resource(required, items[protobuf.append])

    def copy_resource(self, source, destination):
        destination.resource = source.resource
        destination.connection_details()
        for key, value in source.connection_details:
            destination.connection_details[key] = value
        destination.ready = source.ready

    def create_condition(self, type, status, reason, message=None):
        if isinstance(status, protobuf.FieldMessage):
            if status._value == fnv1.Status.STATUS_CONDITION_TRUE:
                status = 'True'
            elif status._value == fnv1.Status.STATUS_CONDITION_FALSE:
                status = 'False'
            else:
                status = 'Unknown'
        elif isinstance(status, bool):
            if status:
                status = 'True'
            else:
                status = 'False'
        elif status is None:
            status = 'Unknown'
        condition = {
            'type': type,
            'status': status,
            'reason': reason,
            'lastTransitionTime': '2026-01-01T00:00:00Z'
        }
        if message:
            condition['message'] = message
        return condition

    def kube_clazz(self, kind, apiVersion, namespaced):
        kind = str(kind)
        apiVersion = str(apiVersion)
        try:
            return kr8s.asyncio.objects.get_class(kind, apiVersion, True)
        except KeyError:
            pass
        return kr8s.asyncio.objects.new_class(kind, apiVersion, True, bool(namespaced) and len(namespaced), plural=self.inflect.plural_noun(kind))

    async def kube_get(self, kind, apiVersion, namespace, name, required=True):
        clazz = self.kube_clazz(kind, apiVersion, namespace)
        try:
            fullName = [str(kind), str(apiVersion), str(name)]
            if namespace and len(namespace):
                fullName.insert(-1, str(namespace))
                resource = await clazz.get(str(name), namespace=str(namespace), api=self.kube_context)
            else:
                resource = await clazz.get(str(name), api=self.kube_context)
            resource = protobuf.Value(None, None, resource.raw)
            result = 'found'
        except kr8s.NotFoundError:
            if required:
                print(f"Resource not found: {':'.join(fullName)}", file=sys.stderr)
                sys.exit(1)
            resource = None
            result = 'missing'
        self.logger.debug(f"Resource {result}: {':'.join(fullName)}")
        return resource

    async def kube_list(self, kind, apiVersion, namespace, labelSelector):
        clazz = self.kube_clazz(kind, apiVersion, namespace)
        resources = [
            protobuf.Value(None, None, resource.raw)
            async for resource in clazz.list(
                    namespace=str(namespace) if namespace and len(namespace) else None,
                    label_selector={
                        label: str(value)
                        for label, value in labelSelector
                    },
            )
        ]
        if self.logger.isEnabledFor(logging.DEBUG):
            fullName = [str(kind), str(apiVersion)]
            if namespace and len(namespace):
                fullName.append(str(namespace))
            fullName.append('&'.join(f"{label}={value}" for label, value in labelSelector))
            if resources:
                result = f"found {self.inflect.number_to_words(len(resources))}"
            else:
                result = 'missing'
            self.logger.debug(f"Resources {result}: {':'.join(fullName)}")
        return resources
