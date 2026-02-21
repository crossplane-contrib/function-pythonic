# Pythonic access of Protobuf Messages


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
response.desired.resources.vpc.resource(kind='VPC', apiVersion='ec2.aws.crossplane.io/v1beta1')
```
The following functions are provided to create Protobuf structures:
| Function | Description |
| ----- | ----------- |
| Map | Create a new Protobuf map |
| List | Create a new Protobuf list |
| Unknown | Create a new Protobuf unknown placeholder |
| Yaml | Create a new Protobuf structure from a yaml string |
| YamlAll | Create a new Protobuf list from a yaml string |
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
