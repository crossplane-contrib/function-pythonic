# Composite Composition


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
| self.connectionSecret | Map | The name, namespace, and resourceName to use when generating the connection secret in Crossplane v2 |
| self.connection | Map | The composite desired connection details |
| self.connection.observed | Map | The composite observed connection details |
| self.ready | Boolean | The composite desired ready state |

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
| self.usages| Boolean | Generate Crossplane Usages for resource dependencies, default False |
| self.autoReady | Boolean | Perform auto ready processing on all composed resources, default True |
| self.unknownsFatal | Boolean | Terminate the composition if already created resources are assigned unknown values, default False |

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
| Resource.addDependency | Method | Add another composed resource as a dependency |
| Resource.setReadyCondition | Method | Set Resource.ready to the Ready Condition status |
| Resource.usages | Boolean | Generate Crossplane Usages for this resource, default is Composite.autoReady |
| Resource.autoReady | Boolean | Perform auto ready processing on this resource, default is Composite.autoReady |
| Resource.unknownsFatal | Boolean | Terminate the composition if this resource has been created and is assigned unknown values, default is Composite.unknownsFatal |

### Required Resources

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
