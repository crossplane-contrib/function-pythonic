# Step Parameters


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
            cm = self.resources.ConfigMap('ConfigMap', 'v1')
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
