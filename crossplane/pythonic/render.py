
import pathlib
import sys
import yaml
from crossplane.function.proto.v1 import run_function_pb2 as fnv1

from . import (
    command,
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
            metavar='PATH',
            help='A YAML file containing the Composite resource to render.',
        )
        parser.add_argument(
            'composition',
            type=pathlib.Path,
            nargs='?',
            metavar='PATH/CLASS',
            help='A YAML file containing the Composition resource or the complete path of a function=-pythonic BaseComposite subclass.',
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
            help='Include informational and warning messages from Functions in the rendered output as resources of kind: Result..',
        )
        parser.add_argument(
            '--include-context', '-c',
            action='store_true',
            help='Include the context in the rendered output as a resource of kind: Context.',
        )

    def initialize(self):
        self.initialize_function()

    async def run(self):
        # Obtain the Composite to render.
        if not self.args.composite.is_file():
            print(f"Composite \"{self.args.composite}\" is not a file", file=sys.stderr)
            sys.exit(1)
        composite = protobuf.Yaml(self.args.composite.read_text())

        # Obtain the Composition that will be used to render the Composite.
        if composite.apiVersion in ('pythonic.crossplane.io/v1alpha1', 'pythonic.fortra.com/v1alpha1') and composite.kind == 'Composite':
            if self.args.composition:
                print('Composite type of "composite.pythonic.crossplane.io" does not use "composition" argument', file=sys.stderr)
                sys.exit(1)
            composition = self.create_composition(composite, '')
        else:
            if not self.args.composition:
                print('"composition" argument required', file=sys.stderr)
                sys.exit(1)
            if self.args.composition.is_file():
                composition = protobuf.Yaml(self.args.composition.read_text())
            else:
                composite = self.args.composition.rsplit('.', 1)
                if len(composite) == 1:
                    print(f"Composition class name does not include module: {self.args.composition}", file=sys.stderr)
                    sys.exit(1)
                try:
                    module = importlib.import_module(composite[0])
                except Exception as e:
                    print(f"Unable to import composition class: {composite[0]}", file=sys.stderr)
                    sys.exit(1)
                clazz = getattr(module, composite[1], None)
                if not clazz:
                    print(f"Composition class {composite[0]} does not define: {composite[1]}", file=sys.stderr)
                    sys.exit(1)
                if not inspect.isclass(clazz):
                    print(f"Composition class {self.args.composition} is not a class", file=sys.stderr)
                    sys.exit(1)
                if not issubclass(clazz, pythonic.BaseComposite):
                    print(f"Composition class {self.args.composition} is not a subclass of BaseComposite", file=sys.stderr)
                    sys.exit(1)
                composition = self.create_composition(composite, str(self.args.composition))

        # Build up the RunFunctionRequest protobuf message used to call function-pythonic.
        request = protobuf.Message(None, 'request', fnv1.RunFunctionRequest.DESCRIPTOR, fnv1.RunFunctionRequest())

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
            request.context[key_path[0]] = protobuf.Yaml(path.read_text())
        for entry in self.args.context_values:
            key_value = entry.split('=', 1)
            if len(key_value) != 2:
                print(f"Invalid --context-values: {entry}", file=sys.stderr)
                sys.exit(1)
            request.context[key_value[0]] = protobuf.Yaml(key_value[1])

        # Collect specified required/extra resources. Sort for stable order when processed.
        requireds = sorted(
            self.collect_resources(self.args.required_resources),
            key=lambda required: str(required.metadata.name),
        )

        # Collect specified connection and credential secrets.
        secrets = []
        for secret in self.collect_resources(self.args.secret_store):
            if secret.apiVersion == 'v1' and secret.kind == 'Secret':
                secrets.append(secret)

        # Establish the request observed composite.
        self.setup_resource(composite, secrets, request.observed.composite)

        # Establish the configured observed resources.
        for resource in self.collect_resources(self.args.observed_resources):
            name = resource.metadata.annotations['crossplane.io/composition-resource-name']
            if name:
                self.setup_resource(resource, secrets, request.observed.resources[name])

        # These will hold the response conditions and results.
        conditions = protobuf.List()
        results = protobuf.List()

        # Create a function-pythonic function runner used to run pipeline steps.
        runner = function.FunctionRunner(self.args.debug, self.args.render_unknowns, self.args.crossplane_v1)
        fatal = False

        # Process the composition pipeline steps.
        for step in composition.spec.pipeline:
            if step.functionRef.name != 'function-pythonic':
                print(f"Only function-pythonic functions can be run: {step.functionRef.name}", file=sys.stderr)
                sys.exit(1)
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
                        for secret in secrets:
                            if secret.metadata.namespace == namespace and secret.metadata.name == name:
                                data = request.credentials[credential.name].credential_data.data
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
                request.required_resources()
                for requirement in step.requirements:
                    self.fetch_requireds(requireds, secrets, requirement.requirementName, requirement, request.required_resources)
                # Fetch the required resources requested.
                for name, selector in requirements.resources:
                    self.fetch_requireds(requireds, secrets, name, selector, request.required_resources)
                # Fetch the now deprecated extra resources requested.
                request.extra_resources()
                for name, selector in requirements.extra_resources:
                    self.fetch_requireds(requireds, secrets, name, selector, request.extra_resources)
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
            if resource.ready != fnv1.Ready.READY_TRUE:
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
            resources[protobuf.append] = resource

        # Format the returned desired composite
        composite = protobuf.Map()
        for name, value in request.desired.composite.resource:
            composite[name] = value
        composite.apiVersion = request.observed.composite.resource.apiVersion
        composite.kind = request.observed.composite.resource.kind
        if self.args.include_full_xr:
            composite.metadata = request.observed.composite.resource.metadata
            if request.observed.composite.resource.spec:
                composite.spec = request.observed.composite.resource.spec
        else:
            if request.observed.composite.resource.metadata.namespace:
                composite.metadata.namespace = request.observed.composite.resource.metadata.namespace
            composite.metadata.name = request.observed.composite.resource.metadata.name
        # Add in the composite's status.conditions.
        if request.desired.composite.ready == fnv1.Ready.READY_FALSE:
            condition = self.create_condition('Ready', False, 'Creating')
        elif request.desired.composite.ready == fnv1.Ready.READY_UNSPECIFIED and len(unready):
            condition = self.create_condition('Ready', False, 'Creating', f"Unready resources: {', '.join(str(name) for name in unready)}")
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
            for key, value in request.desired.composite.connection_details:
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
                    values = request.context,
                )),
                end='',
            )

    def create_composition(self, composite, module):
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
        composition.spec.pipeline[0].input.composite = module
        return composition

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

    def setup_resource(self, source, secrets, resource):
        resource.resource = source
        namespace = source.spec.writeConnectionSecretToRef.namespace or source.metadata.namespace
        name = source.spec.writeConnectionSecretToRef.name
        if namespace and name:
            for secret in secrets:
                if secret.metadata.namespace == namespace and secret.metadata.name == name:
                    resource.connection_details()
                    for key, value in secret.data:
                        resource.connection_details[key] = protobuf.B64Decode(value)
                    break

    def fetch_requireds(self, requireds, secrets, name, selector, resources):
        if not name:
            return
        name = str(name)
        items = resources[name].items
        items() # Force this to get created
        for required in requireds:
            if selector.api_version == required.apiVersion and selector.kind == required.kind:
                if selector.match_name == required.metadata.name:
                    self.setup_resource(required, secrets, items[protobuf.append])
                elif selector.match_labels.labels:
                    for key, value in selector.match_labels.labels:
                        if value != required.metadata.labels[key]:
                            break
                    else:
                        self.setup_resource(required, secrets, items[protobuf.append])

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
