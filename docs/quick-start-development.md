# Quick Start Development


function-pythonic includes a pure python implementation of the `crossplane render ...`
command, which can be used to render Compositions that only use function-pythonic. This
makes it very easy to test and debug using your IDE of choice. It is also blindingly
fast compared to `crossplane render`. To use, install the `crossplane-function-pythonic`
python package into the python environment.
```shell
$ pip install crossplane-function-pythonic
```
Then to render function-pythonic Compositions, use the `function-pythonic render ...`
command.
```shell
$ function-pythonic render --help
usage: Crossplane Function Pythonic render [-h] [--debug] [--log-name-width WIDTH] [--logger-level LOGGER=LEVEL] [--python-path DIRECTORY]
                                           [--render-unknowns] [--allow-oversize-protos] [--crossplane-v1] [--kube-context CONTEXT]
                                           [--context-files KEY=PATH] [--context-values KEY=VALUE] [--observed-resources PATH]
                                           [--required-resources PATH] [--secret-store PATH] [--include-full-xr] [--include-connection-xr]
                                           [--include-function-results] [--include-context]
                                           COMPOSITE [COMPOSITION]

positional arguments:
  COMPOSITE             A YAML file containing the Composite resource to render, or kind:apiVersion:namespace:name of cluster Composite.
  COMPOSITION           A YAML file containing the Composition resource, or the complete path of a function-pythonic BaseComposite subclass.

options:
  -h, --help            show this help message and exit
  --debug, -d           Emit debug logs.
  --log-name-width WIDTH
                        Width of the logger name in the log output, default 40.
  --logger-level LOGGER=LEVEL
                        Logger level, for example: botocore.hooks=INFO
  --python-path DIRECTORY
                        Filing system directories to add to the python path.
  --render-unknowns, -u
                        Render resources with unknowns, useful during local development.
  --allow-oversize-protos
                        Allow oversized protobuf messages
  --crossplane-v1       Enable Crossplane V1 compatibility mode
  --kube-context, -k CONTEXT
                        The kubectl context to use to obtain external resources from, such as required resources, connections, etc.
  --context-files KEY=PATH
                        Context key-value pairs to pass to the Function pipeline. Values must be files containing YAML/JSON.
  --context-values KEY=VALUE
                        Context key-value pairs to pass to the Function pipeline. Values must be YAML/JSON. Keys take precedence over --context-files.
  --observed-resources, -o PATH
                        A YAML file or directory of YAML files specifying the observed state of composed resources.
  --required-resources, -e PATH
                        A YAML file or directory of YAML files specifying required resources to pass to the Function pipeline.
  --secret-store, -s PATH
                        A YAML file or directory of YAML files specifying Secrets to use to resolve connections and credentials.
  --include-full-xr, -x
                        Include a direct copy of the input XR's spedc and metadata fields in the rendered output.
  --include-connection-xr
                        Include the Composite connection values in the rendered output as a resource of kind: Connection.
  --include-function-results, -r
                        Include informational and warning messages from Functions in the rendered output as resources of kind: Result.
  --include-context, -c
                        Include the context in the rendered output as a resource of kind: Context.
```
The following example demonstrates how to locally render function-python compositions. First, create the following files:
#### xr.yaml
```yaml
apiVersion: pythonic.fn.crossplane.io/v1alpha1
kind: Hello
metadata:
  name: world
spec:
  who: World
```
#### composition.yaml
```yaml
apiVersion: apiextensions.crossplane.io/v1
kind: Composition
metadata:
  name: hellos.pythonic.crossplane.io
spec:
  compositeTypeRef:
    apiVersion: pythonic.crossplane.io/v1alpha1
    kind: Hello
  mode: Pipeline
  pipeline:
  - step: pythonic
    functionRef:
      name: function-pythonic
    input:
      apiVersion: pythonic.fn.crossplane.io/v1alpha1
      kind: Composite
      composite: |
        class GreetingComposite(BaseComposite):
          def compose(self):
            self.status.greeting = f"Hello, {self.spec.who}!"
```
Then, to render the above composite and composition, run:
```shell
$ function-pythonic render --debug --render-unknowns xr.yaml composition.yaml
[2025-12-29 09:44:57.949] io.crossplane.fn.pythonic.Hello.world    [DEBUG   ] Starting compose, 1st step, 1st pass
[2025-12-29 09:44:57.949] io.crossplane.fn.pythonic.Hello.world    [INFO    ] Completed compose
---
apiVersion: pythonic.fn.crossplane.io/v1alpha1
kind: Hello
metadata:
  name: world
status:
  conditions:
  - lastTransitionTime: '2026-01-01T00:00:00Z'
    reason: Available
    status: 'True'
    type: Ready
  - lastTransitionTime: '2026-01-01T00:00:00Z'
    message: All resources are composed
    reason: AllComposed
    status: 'True'
    type: ResourcesComposed
  greeting: Hello, World!
```
Most of the examples contain a `render.sh` command which uses `function-pythonic render` to
render the example.
