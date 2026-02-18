
import asyncio
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
        if self.args:
            self.initialize_function()
        self.logger = logging.getLogger(__name__)

    async def run(self):
        if self.args.kube_context:
            kapi = Kr8sApi(self.args.kube_context, self.logger)
        else:
            kapi = None
        composite = await self.setup_composite(kapi)
        observed = self.collect_resources(self.args.observed_resources)
        composition = await self.setup_composition(composite, kapi)
        resources = self.collect_resources(self.args.required_resources)
        resources += self.collect_resources(self.args.secret_store)
        resources.sort(key=lambda resource: str(resource.metadata.name))
        context = self.setup_context()

        render = await self.render(composite, observed, composition, resources, context, kapi, self.args.render_unknowns, self.args.crossplane_v1)
        if not render:
            sys.exit(1)

        if self.args.include_full_xr:
            render.composite.metadata = composite.metadata
            del render.composite.metadata.managedFields
            if composite.spec:
                render.composite.spec = composite.spec
        else:
            if composite.metadata.namespace:
                render.composite.metadata.namespace = composite.metadata.namespace
            render.composite.metadata.name = composite.metadata.name

        # Print the composite.
        print('---')
        print(str(render.composite), end='')
        # Print Composite connection if requested.
        if self.args.include_connection_xr:
            print('---')
            print(str(render.connection), end='')
        # Print the composed resources.
        for resource in sorted(render.resources, key=lambda resource: str(resource.metadata.annotations['crossplane.io/composition-resource-name'])):
            print('---')
            print(str(resource), end='')
        # Print the results (AKA events) if requested.
        if self.args.include_function_results:
            for result in render.results:
                print('---')
                print(str(result), end='')
        # Print the final context if requested.
        if self.args.include_context:
            print('---')
            print(str(render.context), end='')

    async def setup_composite(self, kapi=None):
        # Obtain the Composite to render.
        if self.args.composite.is_file():
            return protobuf.Yaml(self.args.composite.read_text())
        if not kapi:
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
        composite = await kapi.get(composite[0], composite[1], namespace, composite[-1])
        if not composite:
            print(f"Composite \"{self.args.composite}\" not found", file=sys.stderr)
            sys.exit(1)
        return composite

    async def setup_composition(self, composite, kapi=None):
        # Obtain the Composition that will be used to render the Composite.
        if not self.args.composition:
            return None
        if self.args.composition.is_file():
            composition = self.args.composition.read_text()
            if self.args.composition.suffix == '.py':
                return self.create_composition(compsite, composition)
            composition = protobuf.Yaml(composition)
            if not len(composition.spec.pipeline):
                print(f"Composition file does not contain any pipeline steps: {self.args.composition}", file=sys.stderr)
                sys.exit(1)
            return composition
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
        return self.create_composition(composite, self.args.composition)

    def create_composition(self, composite, module=''):
        composition = protobuf.Map()
        composition.apiVersion = 'apiextensions.crossplane.io/v1'
        composition.kind = 'Composition'
        composition.metadata.name = 'function-pythonic-render'
        composition.spec.compositeTypeRef.apiVersion = composite.apiVersion
        composition.spec.compositeTypeRef.kind = composite.kind
        composition.spec.mode = 'Pipeline'
        composition.spec.pipeline[0].step = 'function-pythonic-render'
        composition.spec.pipeline[0].functionRef.name = 'function-pythonic'
        composition.spec.pipeline[0].input.apiVersion = 'pythonic.fn.crossplane.io/v1alpha1'
        composition.spec.pipeline[0].input.kind = 'Composite'
        composition.spec.pipeline[0].input.composite = str(module)
        return composition

    def collect_resources(self, entries):
        resources = []
        for entry in entries:
            if entry.is_file():
                for document in yaml.safe_load_all(entry.read_text()):
                    resources.append(protobuf.Value(None, None, document))
            elif entry.is_dir():
                for file in entry.iterdir():
                    if file.suffix in ('.yaml', '.yml'):
                        for document in yaml.safe_load_all(file.read_text()):
                            resources.append(protobuf.Value(None, None, document))
            else:
                print(f"Specified resource is not a file or a directory: {entry}", file=sys.stderr)
                sys.exit(1)
        return resources

    def setup_context(self):
        # Load the request context with any specified command line options.
        context = protobuf.Map()
        for entry in self.args.context_files:
            key_path = entry.split('=', 1)
            if len(key_path) != 2:
                print(f"Invalid --context-files: {entry}", file=sys.stderr)
                sys.exit(1)
            path = pathlib.Path(key_path[1])
            if not path.is_file():
                print(f"Invalid --context-files {path} is not a file", file=sys.stderr)
                sys.exit(1)
            context[key_path[0]] = protobuf.Yaml(path.read_text())
        for entry in self.args.context_values:
            key_value = entry.split('=', 1)
            if len(key_value) != 2:
                print(f"Invalid --context-values: {entry}", file=sys.stderr)
                sys.exit(1)
            context[key_value[0]] = protobuf.Yaml(key_value[1])
        return context

    async def render(self, composite, observed=[], composition=None, resources=[], context=None, kapi=None, render_unknowns=False, crossplane_v1=False):
        # Create the request used when running Composition steps.
        request = protobuf.Message(None, 'request', fnv1.RunFunctionRequest.DESCRIPTOR, fnv1.RunFunctionRequest())
        if context is not None:
            request.context = context

        # Establish the request observed composite.
        await self.set_resource(composite, request.observed.composite, resources, kapi)
        # Establish the manually configured observed resources.
        if observed:
            async with asyncio.TaskGroup() as group:
                for resource in observed:
                    name = resource.metadata.annotations['crossplane.io/composition-resource-name']
                    if name:
                        group.create_task(self.set_resource(resource, request.observed.resources[name], resources, kapi))
        if kapi:
            refs = composite.spec.crossplane.resourceRefs
            if not refs:
                refs = composite.spec.resourceRefs
            if refs:
                async with asyncio.TaskGroup() as group:
                    for ref in refs:
                        group.create_task(self.get_composite_ref(composite, ref, request, resources, kapi))

        if not composition:
            if composite.apiVersion in ('pythonic.crossplane.io/v1alpha1', 'pythonic.fortra.com/v1alpha1') and composite.kind == 'Composite':
                composition = self.create_composition(composite)
            else:
                if not kapi:
                    print('"composition" required', file=sys.stderr)
                    return None
                revision = composite.spec.crossplane.compositionRevisionRef
                if not revision.name:
                    # Crossplane V1 location
                    revision = composite.spec.compositionRevisionRef
                    if not revision.name:
                        print('Composite does not contain a CompositionRevision name', file=sys.stderr)
                        return None
                composition = await kapi.get('CompositionRevision', 'apiextensions.crossplane.io/v1', None, revision.name)
                if not composition:
                    print(f"Compositioin \"{revision.name}\" not found", file=sys.stderr)
                    return None

        # These will hold the response conditions and results.
        conditions = protobuf.List()
        results = protobuf.List()

        # Create a function-pythonic function runner used to run pipeline steps.
        runner = function.FunctionRunner(render_unknowns, crossplane_v1)
        fatal = False

        # Process the composition pipeline steps.
        for step in composition.spec.pipeline:
            if step.functionRef.name != 'function-pythonic':
                print(f"Only function-pythonic functions can be run: {step.functionRef.name}", file=sys.stderr)
                return None
            if not step.input.step:
                step.input.step = step.step
            request.input = step.input

            # Supply step requested credentials.
            request.credentials()
            for credential in step.credentials:
                if credential.source == 'Secret' and credential.secretRef:
                    namespace = credential.secretRef.namespace
                    name = credential.secretRef.name
                    if namespace and name:
                        for resource in resources:
                            if resource.kind == 'Secret' and resource.apiVersion == 'v1':
                                if resource.metadata.namespace == namespace and resource.metadata.name == name:
                                    data = request.credentials[credential.name].credential_data.data
                                    data()
                                    for key, value in resource.data:
                                        data[key] = protobuf.B64Decode(value)
                                    break
                        else:
                            print(f"Step \"{step.step}\" secret not found: {namespace}/{name}", file=sys.stderr)
                            return None

            # Track what extra/required resources have been processed.
            requirements = protobuf.Message(None, 'requirements', fnv1.Requirements.DESCRIPTOR, fnv1.Requirements())
            for _ in range(5):
                # Fetch the step bootstrap resources specified.
                request.required_resources()
                for requirement in step.requirements.requiredResources:
                    await self.set_required(requirement.requirementName, requirement, request.required_resources, resources, kapi)
                # Fetch the required resources requested.
                for name, selector in requirements.resources:
                    await self.set_required(name, selector, request.required_resources, resources, kapi)
                # Fetch the now deprecated extra resources requested.
                request.extra_resources()
                for name, selector in requirements.extra_resources:
                    await self.set_required(name, selector, request.extra_resources, resources, kapi)
                # Run the step using the function-pythonic function runner.
                response = protobuf.Message(
                    None,
                    'response',
                    fnv1.RunFunctionResponse.DESCRIPTOR,
                    await runner.RunFunction(request._message, None),
                )
                # All done if there is a fatal result.
                for result in response.results:
                    if result.severity == fnv1.Severity.SEVERITY_FATAL:
                        fatal = True
                        break
                # Copy the response context to the request context to use in subsequent steps.
                request.context = response.context
                # Exit this loop if the function has not requested additional extra/required resources.
                if response.requirements == requirements:
                    break
                # Establish the new set of requested extra/required resoruces.
                requirements = response.requirements

            # Copy the response desired state to the request desired state to use in subsequent steps.
            request.desired.resources()
            self.copy_resource(response.desired.composite, request.desired.composite)
            for name, resource in response.desired.resources:
                self.copy_resource(resource, request.desired.resources[name])

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
        prefix = composite.metadata.labels['crossplane.io/composite']
        if not prefix:
            prefix = composite.metadata.name
        for name, resource in request.desired.resources:
            if resource.ready == fnv1.Ready.READY_TRUE:
                ready = True
            elif resource.ready == fnv1.Ready.READY_FALSE:
                ready = False
            else:
                ready = None
            if not ready:
                unready[protobuf.append] = name
            resource = resource.resource
            observed = request.observed.resources[name].resource
            if observed:
                for key in ('namespace', 'generateName', 'name'):
                    if observed.metadata[key]:
                        resource.metadata[key] = observed.metadata[key]
            if not resource.metadata.name and not resource.metadata.generateName:
                resource.metadata.generateName = f"{prefix}-"
            if composite.metadata.namespace:
                resource.metadata.namespace = composite.metadata.namespace
            resource.metadata.annotations['crossplane.io/composition-resource-name'] = name
            resource.metadata.labels['crossplane.io/composite'] = prefix
            if composite.metadata.labels['crossplane.io/claim-name'] and composite.metadata.labels['crossplane.io/claim-namespace']:
                resource.metadata.labels['crossplane.io/claim-namespace'] = composite.metadata.labels['crossplane.io/claim-namespace']
                resource.metadata.labels['crossplane.io/claim-name'] = composite.metadata.labels['crossplane.io/claim-name']
            elif composite.spec.claimRef.namespace and composite.spec.claimRef.name:
                resource.metadata.labels['crossplane.io/claim-namespace'] = composite.spec.claimRef.namespace
                resource.metadata.labels['crossplane.io/claim-name'] = composite.spec.claimRef.name
            resource.metadata.ownerReferences[0].controller = True
            resource.metadata.ownerReferences[0].blockOwnerDeletion = True
            resource.metadata.ownerReferences[0].apiVersion = composite.apiVersion
            resource.metadata.ownerReferences[0].kind = composite.kind
            resource.metadata.ownerReferences[0].name = composite.metadata.name
            resource.metadata.ownerReferences[0].uid = ''
            resource.ready = ready
            resources[protobuf.append] = resource

        # Format the returned desired composite
        composite = protobuf.Map()
        for name, value in request.desired.composite.resource:
            composite[name] = value
        composite.apiVersion = request.observed.composite.resource.apiVersion
        composite.kind = request.observed.composite.resource.kind
        # Add in the composite's status.conditions.
        if request.desired.composite.ready == fnv1.Ready.READY_FALSE:
            condition = self.create_condition('Ready', False, 'Creating')
        elif request.desired.composite.ready == fnv1.Ready.READY_UNSPECIFIED and len(unready):
            condition = self.create_condition('Ready', False, 'Creating', f"Unready resources: {','.join(str(name) for name in unready)}")
        else:
            condition = self.create_condition('Ready', True, 'Available')
        composite.status.conditions[protobuf.append] = condition
        for condition in conditions:
            composite.status.conditions[protobuf.append] = condition

        return protobuf.Map(
            composite=composite,
            connection=protobuf.Map(
                apiVersion='render.crossplane.io/v1beta1',
                kind='Connection',
                values={key: value for key, value in request.desired.composite.connection_details}
            ),
            resources=resources,
            results=results,
            context=protobuf.Map(
                apiVersion='render.crossplane.io/v1beta1',
                kind='Context',
                values=request.context,
            ),
        )

    async def get_composite_ref(self, composite, ref, request, resources, kapi):
        namespace = ref.namespace
        if not namespace:
            namespace = composite.metadata.namespace
            if not namespace:
                namespace = None
        source = await kapi.get(ref.kind, ref.apiVersion, namespace, ref.name)
        if source:
            name = source.metadata.annotations['crossplane.io/composition-resource-name']
            if name:
                destination = request.observed.resources[name]
                if not destination: # Do not override manual observed
                    await self.set_resource(source, destination, resources, kapi)

    async def set_required(self, name, selector, requireds, resources=[], kapi=None):
        if not name:
            return
        name = str(name)
        items = requireds[name].items
        items() # Force this to get created
        for resource in resources:
            if selector.api_version == resource.apiVersion and selector.kind == resource.kind:
                if ((not len(selector.namespace) and not len(resource.metadata.namespace))
                    or (selector.namespace == resource.metadata.namespace)
                    ):
                    if selector.match_name == resource.metadata.name:
                        await self.set_resource(resource, items[protobuf.append], resources, kapi)
                    elif selector.match_labels.labels:
                        for key, value in selector.match_labels.labels:
                            if value != resource.metadata.labels[key]:
                                break
                        else:
                            await self.set_resource(resource, items[protobuf.append], resources, kapi)
        if not len(items) and kapi:
            if len(selector.match_name):
                resource = await kapi.get(selector.kind, selector.api_version, selector.namespace, selector.match_name)
                if resource:
                    await self.set_resource(resource, items[protobuf.append], resources, kapi)
            elif len(selector.match_labels.labels):
                for resource in await kapi.list(selector.kind, selector.api_version, selector.namespace, selector.match_labels.labels):
                    await self.set_resource(resource, items[protobuf.append], resources, kapi)

    async def set_resource(self, source, destination, resources=[], kapi=None):
        destination.resource = source
        namespace = source.spec.writeConnectionSecretToRef.namespace or source.metadata.namespace
        name = source.spec.writeConnectionSecretToRef.name
        if namespace and name:
            connection = None
            for resource in resources:
                if resource.kind == 'Secret' and resource.apiVersion == 'v1':
                    if resource.metadata.namespace == namespace and resource.metadata.name == name:
                        connection = resource
                        break
            else:
                if kapi:
                    connection = await kapi.get('Secret', 'v1', namespace, name)
            if connection:
                destination.connection_details()
                for key, value in connection.data:
                    destination.connection_details[key] = protobuf.B64Decode(value)

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


class Kr8sApi:
    def __init__(self, context=None, logger=None):
        self.kr8s = importlib.import_module('kr8s')
        self.inflect = inflect.engine()
        self.inflect.classical(all=False)
        self.context = context
        self.logger = logger
        self._api = None

    async def api(self):
        if not self._api:
            self._api = await self.kr8s.asyncio.api(context=self.context)
        return self._api

    async def get(self, kind, apiVersion, namespace, name):
        clazz = self._get_clazz(kind, apiVersion, namespace)
        try:
            fullName = [str(kind), str(apiVersion), str(name)]
            if namespace and len(namespace):
                fullName.insert(-1, str(namespace))
                resource = await clazz.get(str(name), namespace=str(namespace), api=await self.api())
            else:
                resource = await clazz.get(str(name), api=await self.api())
            resource = protobuf.Value(None, None, resource.raw)
            result = 'found'
        except self.kr8s.NotFoundError:
            resource = None
            result = 'missing'
        if self.logger:
            self.logger.debug(f"Resource {result}: {':'.join(fullName)}")
        return resource

    async def list(self, kind, apiVersion, namespace, labelSelector):
        clazz = self._get_clazz(kind, apiVersion, namespace)
        resources = [
            protobuf.Value(None, None, resource.raw)
            async for resource in clazz.list(
                namespace=str(namespace) if namespace and len(namespace) else None,
                label_selector={
                    label: str(value)
                    for label, value in labelSelector
                },
                api=await self.api()
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

    def _get_clazz(self, kind, apiVersion, namespaced):
        kind = str(kind)
        apiVersion = str(apiVersion)
        try:
            return self.kr8s.asyncio.objects.get_class(kind, apiVersion, True)
        except KeyError:
            pass
        return self.kr8s.asyncio.objects.new_class(kind, apiVersion, True, bool(namespaced) and len(namespaced), plural=self.inflect.plural_noun(kind))
