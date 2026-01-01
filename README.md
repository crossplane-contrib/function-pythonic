# function-pythonic

## Introduction

A Crossplane composition function that lets you compose Composites using a set
of python classes enabling an elegant and terse syntax. Here is what the following
example is doing:

* Create an MR named 'vpc' with apiVersion 'ec2.aws.crossplane.io/v1beta1' and kind 'VPC'
* Set the vpc region and cidr from the XR spec values
* Set the XR status.vpcId to the created vpc id

```yaml
apiVersion: apiextensions.crossplane.io/v1
kind: Composition
metadata:
  name: create-vpc
spec:
  compositeTypeRef:
    apiVersion: example.crossplane.io/v1
    kind: XR
  mode: Pipeline
  pipeline:
  - step:
    functionRef:
      name: function-pythonic
    input:
      apiVersion: pythonic.fn.crossplane.io/v1alpha1
      kind: Composite
      composite: |
        class VpcComposite(BaseComposite):
          def compose(self):
            vpc = self.resources.vpc('ec2.aws.crossplane.io/v1beta1', 'VPC')
            vpc.spec.forProvider.region = self.spec.region
            vpc.spec.forProvider.cidrBlock = self.spec.cidr
            self.status.vpcId = vpc.status.atProvider.vpcId
```

In addtion to an inline script, the python implementation can be specified
as the complete path to a python class. Python packages can be deployed using
ConfigMaps, enabling using your IDE of choice for writting the code. See
[ConfigMap Packages](#configmap-packages) and
[Filing System Packages](#filing-system-packages).

## Examples

In the [examples](./examples) directory are many exemples, including all of the
function-go-templating examples implemented using function-pythonic.
The [eks-cluster](./examples/eks-cluster/composition.yaml) example is a good
complex example creating the entire vpc structure needed for an EKS cluster.

## Installing function-pythonic

```yaml
apiVersion: pkg.crossplane.io/v1
kind: Function
metadata:
  name: function-pythonic
spec:
  package: xpkg.upbound.io/crossplane-contrib/function-pythonic:v0.2.1
```
## Composed Resource Dependencies

function-pythonic automatically handles dependencies between composed resources.

Just compose everything as if it is immediately created and the framework will delay
the creation of any resources which depend on other resources which do not exist yet.
In other words, it accomplishes what [function-sequencer](https://github.com/crossplane-contrib/function-sequencer)
provides, but it automatically detects the dependencies.

If a resource has been created and a dependency no longer exists due to some unexpected
condition, the composition will be terminated or the observed value for that field will
be used, depending on the `unknownsFatal` settings.

Take the following example:
```yaml
vpc = self.resources.VPC('ec2.aws.crossplane.io/v1beta1', 'VPC')
vpc.spec.forProvider.region = 'us-east-1
vpc.spec.forProvider.cidrBlock = '10.0.0.0/16'

subnet = self.resources.SubnetA('ec2.aws.crossplane.io/v1beta1', 'Subnet')
subnet.spec.forProvider.region = 'us-east-1'
subnet.spec.forProvider.vpcId = vpc.status.atProvider.vpcId
subnet.spec.forProvider.availabilityZone = 'us-east-1a'
subnet.spec.forProvider.cidrBlock = '10.0.0.0/20'
```
If the Subnet does not yet exist, the framework will detect if the vpcId set
in the Subnet is unknown, and will delay the creation of the subnet.

Once the Subnet has been created, if for some unexpected reason the vpcId passed
to the Subnet is unknown, the framework will detect it and either terminate
the Composite composition or use the vpcId in the observed Subnet. The default
action taken is to fast fail by terminating the composition. This can be
overridden for all composed resource by setting the Composite `self.unknownsFatal` field
to False, or at the individual composed resource level by setting the
`Resource.unknownsFatal` field to False.

## Usage Dependencies

function-pythonic can be configured to automatically create
[Crossplane Usages](https://docs.crossplane.io/latest/managed-resources/usages/)
dependencies between resources. Modifying the above VPC example with:
```yaml
self.usages = True

vpc = self.resources.VPC('ec2.aws.crossplane.io/v1beta1', 'VPC')
vpc.spec.forProvider.region = 'us-east-1
vpc.spec.forProvider.cidrBlock = '10.0.0.0/16'

subnet = self.resources.SubnetA('ec2.aws.crossplane.io/v1beta1', 'Subnet')
subnet.spec.forProvider.region = 'us-east-1'
subnet.spec.forProvider.vpcId = vpc.status.atProvider.vpcId
subnet.spec.forProvider.availabilityZone = 'us-east-1a'
subnet.spec.forProvider.cidrBlock = '10.0.0.0/20'
```
Will generate the appropriate Crossplane Usage resource.

## Pythonic access of Protobuf Messages

All Protobuf messages are wrapped by a set of python classes which enable using
both object attribute names and dictionary key names to traverse the Protobuf
message contents. For example, the following examples obtain the same value
from the RunFunctionRequest message:
```python
region = request.observed.composite.resource.spec.region
region = request['observed']['composite']['resource']['spec']['region']
```
Getting values from free form map and list values will not throw
errors for keys that do not exist, but will return an unknown placeholder
which evaluates as False. For example, the following will evaluate as False
with a just created RunFunctionResponse message:
```python
vpcId = response.desired.resources.vpc.resource.status.atProvider.vpcId
if vpcId:
    # The vpcId is available
```
Note that maps or lists that do exist but do not have any members will evaluate
as True, contrary to Python dicts and lists. Use the `len` function to test
if the map or list exists and has members.

When setting fields, all intermediary unknown placeholders will automatically
be created. For example, this will create all items needed to set the
region on the desired resource:
```python
response.desired.resources.vpc.resource.spec.forProvider.region = 'us-east-1'
```
Calling a message or map will clear it and will set any provided key word
arguments. For example, this will either create or clear the resource
and then set its apiVersion and kind:
```python
response.desired.resources.vpc.resource(apiVersion='ec2.aws.crossplane.io/v1beta1', kind='VPC')
```
The following functions are provided to create Protobuf structures:
| Function | Description |
| ----- | ----------- |
| Map | Create a new Protobuf map |
| List | Create a new Protobuf list |
| Unknown | Create a new Protobuf unknown placeholder |
| Yaml | Create a new Protobuf structure from a yaml string |
| Json | Create a new Protobuf structure from a json string |
| B64Encode | Encode a string into base 64 |
| B64Decode | Decode a string from base 64 |

The following items are supported in all the Protobuf Message wrapper classes: `bool`,
`len`, `contains`, `iter`, `hash`, `==`, `str`, `format`

To convert a Protobuf message to a string value, use either `str` or `format`.
```python
yaml  = str(request)                # get the request as yaml
yaml  = format(request)             # also get the request as yaml
yaml  = format(request, 'yaml')     # yet another get the request as yaml
json  = format(request, 'json')     # get the request as json
json  = format(request, 'jsonc')    # get the request as json compact
proto = format(request, 'protobuf') # get the request as a protobuf string
```
## Composite Composition

Composite composition is performed from a Composite orientation. A `BaseComposite` class
is subclassed and the `compose` method is implemented.
```python
class MyComposite(BaseComposite):
    def compose(self):
        # Compose the Composite
```
The compose method can also declare itself as performing async io:
```python
class MyAsyncComposite(BaseComposite):
    async def compose(self):
        # Compose the Composite using async io when needed
```

### BaseComposite

The BaseComposite class provides the following fields for manipulating the Composite itself:

| Field | Type | Description |
| ----- | ---- | ----------- |
| self.observed | Map | Low level direct access to the observed composite |
| self.desired | Map | Low level direct access to the desired composite |
| self.apiVersion | String | The composite observed apiVersion |
| self.kind | String | The composite observed kind |
| self.metadata | Map | The composite observed metadata |
| self.spec | Map | The composite observed spec |
| self.status | Map | The composite desired and observed status, read from observed if not in desired |
| self.conditions | Conditions | The composite desired and observed conditions, read from observed if not in desired |
| self.results | Results | Returned results applied to the Composite and optionally on the Claim |
| self.connection | Map | The composite desired connection detials |
| self.ready | Boolean | The composite desired ready state |
| self.observed.connection | Map | The composite observed connection detials |

The BaseComposite also provides access to the following Crossplane Function level features:

| Field | Type | Description |
| ----- | ---- | ----------- |
| self.request | Message | Low level direct access to the RunFunctionRequest message |
| self.response | Message | Low level direct access to the RunFunctionResponse message |
| self.logger | Logger | Python logger to log messages to the running function stdout |
| self.parameters | Map | The configured step parameters |
| self.ttl | Integer | Get or set the response TTL, in seconds |
| self.credentials | Credentials | The request credentials |
| self.context | Map | The response context, initialized from the request context |
| self.environment | Map | The response environment, initialized from the request context environment |
| self.requireds | Requireds | Request and read additional local Kubernetes resources |
| self.resources | Resources | Define and process composed resources |
| self.unknownsFatal | Boolean | Terminate the composition if already created resources are assigned unknown values, default True |
| self.usages| Boolean | Generate Crossplane Usages for resource dependencies, default False |
| self.autoReady | Boolean | Perform auto ready processing on all composed resources, default True |

### Composed Resources

Creating and accessing composed resources is performed using the `BaseComposite.resources` field.
`BaseComposite.resources` is a dictionary of the composed resources whose key is the composition
resource name. The value returned when getting a resource from BaseComposite is the following
Resource class:

| Field | Type | Description |
| ----- | ---- | ----------- |
| Resource(apiVersion,kind,namespace,name) | Resource | Reset the resource and set the optional parameters |
| Resource.name | String | The composition composed resource name |
| Resource.observed | Map | Low level direct access to the observed composed resource |
| Resource.desired | Map | Low level direct access to the desired composed resource |
| Resource.apiVersion | String | The composed resource apiVersion |
| Resource.kind | String | The composed resource kind |
| Resource.externalName | String | The composed resource external name |
| Resource.metadata | Map | The composed resource desired metadata |
| Resource.spec | Map | The resource spec |
| Resource.data | Map | The resource data |
| Resource.status | Map | The resource status |
| Resource.conditions | Conditions | The resource conditions |
| Resource.connection | Map | The resource observed connection details |
| Resource.ready | Boolean | The resource ready state |
| Resource.unknownsFatal | Boolean | Terminate the composition if this resource has been created and is assigned unknown values, default is Composite.unknownsFatal |
| Resource.usages | Boolean | Generate Crossplane Usages for this resource, default is Composite.autoReady |
| Resource.autoReady | Boolean | Perform auto ready processing on this resource, default is Composite.autoReady |

### Required Resources (AKA Extra Resources)

Creating and accessing required resources is performed using the `BaseComposite.requireds` field.
`BaseComposite.requireds` is a dictionary of the required resources whose key is the required
resource name. The value returned when getting a required resource from BaseComposite is the
following RequiredResources class:

| Field | Type | Description |
| ----- | ---- | ----------- |
| RequiredResource(apiVersion,kind,namespace,name,labels) | RequiredResource | Reset the required resource and set the optional parameters |
| RequiredResources.name | String | The required resources name |
| RequiredResources.apiVersion | String | The required resources apiVersion |
| RequiredResources.kind | String | The required resources kind |
| RequiredResources.namespace | String | The namespace to match when returning the required resources, see note below |
| RequiredResources.matchName | String | The names to match when returning the required resources |
| RequiredResources.matchLabels | Map | The labels to match when returning the required resources |

The current version of crossplane-sdk-python used by function-pythonic does not support namespace
selection. For now, use matchLabels and filter the results if required.

RequiredResources acts like a Python list to provide access to the found required resources.
Each resource in the list is the following RequiredResource class:

| Field | Type | Description |
| ----- | ---- | ----------- |
| RequiredResource.name | String | The required resource name |
| RequiredResource.observed | Map | Low level direct access to the observed required resource |
| RequiredResource.apiVersion | String | The required resource apiVersion |
| RequiredResource.kind | String | The required resource kind |
| RequiredResource.metadata | Map | The required resource metadata |
| RequiredResource.spec | Map | The required resource spec |
| RequiredResource.data | Map | The required resource data |
| RequiredResource.status | Map | The required resource status |
| RequiredResource.conditions | Map | The required resource conditions |
| RequiredResource.connection | Map | The required resource connection details |

### Conditions

The `BaseComposite.conditions`, `Resource.conditions`, and `RequiredResource.conditions` fields
are maps of that entity's status conditions array, with the map key being the condition type.
The fields are read only for `Resource.conditions` and `RequiredResource.conditions`.

| Field | Type | Description |
| ----- | ---- | ----------- |
| Condition.type | String | The condtion type, or name |
| Condition.status | Boolean | The condition status |
| Condition.reason | String | PascalCase, machine-readable reason for this condition |
| Condition.message | String | Human-readable details about the condition |
| Condition.lastTransitionTime | Timestamp | Last transition time, read only |
| Condition.claim | Boolean | Also apply the condition the claim |

### Results

The `BaseComposite.results` field is a list of results to apply to the Composite and
optionally to the Claim.

| Field | Type | Description |
| ----- | ---- | ----------- |
| Result.info | Boolean | Normal informational result |
| Result.warning | Boolean | Warning level result |
| Result.fatal | Boolean | Fatal results also terminate composing the Composite |
| Result.reason | String | PascalCase, machine-readable reason for this result |
| Result.message | String | Human-readable details about the result |
| Result.claim | Boolean | Also apply the result to the claim |

## Single use Composites

Tired of creating a CompositeResourceDefinition, a Composition, and a Composite
just to run that Composition once in a single use or initialize task?

function-pythonic installs a `Composite` CompositeResourceDefinition that enables
creating such tasks using a single Composite resource:
```yaml
apiVersion: pythonic.fn.crossplane.io/v1alpha1
kind: Composite
metadata:
  name: composite-example
spec:
  composite: |
    class HelloComposite(BaseComposite):
      def compose(self):
        self.status.composite = 'Hello, World!'
```

## Quick Start Development

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
$ function-pythonic render -h
usage: Crossplane Function Pythonic render [-h] [--debug] [--log-name-width WIDTH] [--python-path DIRECTORY] [--render-unknowns]
                                           [--allow-oversize-protos] [--context-files KEY=PATH] [--context-values KEY=VALUE]
                                           [--observed-resources PATH] [--required-resources PATH] [--secret-store PATH] [--include-full-xr]
                                           [--include-connection-xr] [--include-function-results] [--include-context]
                                           PATH [PATH/CLASS]

positional arguments:
  PATH                  A YAML file containing the Composite resource to render.
  PATH/CLASS            A YAML file containing the Composition resource or the complete path of a function=-pythonic BaseComposite subclass.

options:
  -h, --help            show this help message and exit
  --debug, -d           Emit debug logs.
  --log-name-width WIDTH
                        Width of the logger name in the log output, default 40.
  --python-path DIRECTORY
                        Filing system directories to add to the python path.
  --render-unknowns, -u
                        Render resources with unknowns, useful during local development.
  --allow-oversize-protos
                        Allow oversized protobuf messages
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
                        Include informational and warning messages from Functions in the rendered output as resources of kind: Result..
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

## ConfigMap Packages

ConfigMap based python packages are enable using the `--packages` and
`--packages-namespace` command line options. ConfigMaps with the label
`function-pythonic.package` will be incorporated in the python path at
the location configured in the label value. For example, the following
ConfigMap will enable python to use `import example.pythonic.features`
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  namespace: crossplane-system
  name: example-pythonic
  labels:
    function-pythonic.package: example.pythonic
data:
  features.py: |
    def anything():
        return 'something'
```
Then, in your Composition:
```yaml
    ...
    - step: pythonic
    functionRef:
      name: function-pythonic
    input:
      apiVersion: pythonic.fn.crossplane.io/v1alpha1
      kind: Composite
      composite: |
        from example.pythonic import features
        class FetureComposite(BaseComposite):
            def compose(self):
                anything = features.anything()
    ...
```
The entire function-pythonic Composite class can be coded in the ConfigMap and
only the complete Composite class path is needed in the step configuration.
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  namespace: crossplane-system
  name: example-pythonic
  labels:
    function-pythonic.package: example.pythonic
data:
  features.py: |
    from crossplane.pythonic import BaseComposite
    class FeatureOneComposite(BaseComposite):
        def compose(self):
            # go at it!
```
```yaml
    ...
    - step: pythonic
    functionRef:
      name: function-pythonic
    input:
      apiVersion: pythonic.fn.crossplane.io/v1alpha1
      kind: Composite
      composite: example.pythonic.features.FeatureOneComposite
    ...
```
This requires enabling the the packages support using the `--packages` command
line option in the DeploymentRuntimeConfig and configuring the required
Kubernetes RBAC permissions. For example:
```yaml
apiVersion: pkg.crossplane.io/v1
kind: Function
metadata:
  name: function-pythonic
spec:
  package: xpkg.upbound.io/crossplane-contrib/function-pythonic:v0.2.1
  runtimeConfigRef:
    name: function-pythonic
---
apiVersion: pkg.crossplane.io/v1beta1
kind: DeploymentRuntimeConfig
metadata:
  name: function-pythonic
spec:
  deploymentTemplate:
    spec:
      selector: {}
      template:
        spec:
          containers:
          - name: package-runtime
            args:
            - --debug
            - --packages
          serviceAccountName: function-pythonic
  serviceAccountTemplate:
    metadata:
      name: function-pythonic
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: function-pythonic
rules:
- apiGroups:
  - ''
  resources:
  - configmaps
  verbs:
  - list
  - watch
  - patch
- apiGroups:
  - ''
  resources:
  - events
  verbs:
  - create
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: function-pythonic
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: function-pythonic
subjects:
- kind: ServiceAccount
  namespace: crossplane-system
  name: function-pythonic
```
When enabled, labeled ConfigMaps are obtained cluster wide, requiring the above
ClusterRole permissions. The `--packages-namespace` command line option will restrict
to only using the supplied namespace. This option can be invoked multiple times.
The above RBAC permission can then be per namespace RBAC Role permissions.

Secrets can also be used in an identical manner as ConfigMaps by enabling the
`--packages-secrets` command line option. Secrets permissions need to be
added to the above RBAC configuration.

## Step Parameters

Step specific parameters can be configured to be used by the composite
implementation. This is useful when setting the composite to the python class.
For example:
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  namespace: crossplane-system
  name: example-pythonic
  labels:
    function-pythonic.package: example.pythonic
data:
  features.py: |
    from crossplane.pythonic import BaseComposite
    class GreetingComposite(BaseComposite):
        def compose(self):
            cm = self.resources.ConfigMap('v1', 'ConfigMap')
            cm.data.greeting = f"Hello, {self.parameters.who}!"
```
```yaml
    ...
    - step: pythonic
    functionRef:
      name: function-pythonic
    input:
      apiVersion: pythonic.fn.crossplane.io/v1alpha1
      kind: Composite
      parameters:
        who: World
      composite: example.pythonic.features.GreetingComposite
    ...
```

## Filing System Packages

Composition Composite implementations can be coded in a stand alone python files
by configuring the function-pythonic deployment with the code mounted into
the package-runtime container, and then adding the mount point to the python
path using the --python-path command line option.
```yaml
apiVersion: pkg.crossplane.io/v1beta1
kind: DeploymentRuntimeConfig
metadata:
  name: function-pythonic
spec:
  deploymentTemplate:
    spec:
      template:
        spec:
          containers:
          - name: package-runtime
            args:
            - --debug
            - --python-path
            - /mnt/composites
            volumeMounts:
            - name: composites
              mountPath: /mnt/composites
          volumes:
          - name: composites
            configMap:
              name: pythonic-composites
```
See the [filing-system](examples/filing-system) example.

## Install Additional Python Packages

function-pythonic supports a `--pip-install` command line option which will run pip install
with the configured pip install command. For example:
```yaml
apiVersion: pkg.crossplane.io/v1beta1
kind: DeploymentRuntimeConfig
metadata:
  name: function-pythonic
spec:
  deploymentTemplate:
    spec:
      template:
        spec:
          containers:
          - name: package-runtime
            args:
            - --debug
            - --pip-install
            - --quiet aiobotocore==2.23.2
```

## Enable Oversize Protos

The Protobuf python package used by function-pythonic limits the depth of yaml
elements and the total size of yaml parsed. This results in a limit of approximately
30 levels of nested yaml fields. This check can be disabled using the `--allow-oversize-protos`
command line option. For example:

```yaml
apiVersion: pkg.crossplane.io/v1beta1
kind: DeploymentRuntimeConfig
metadata:
  name: function-pythonic
spec:
  deploymentTemplate:
    spec:
      template:
        spec:
          containers:
          - name: package-runtime
            args:
            - --debug
            - --allow-oversize-protos
```
