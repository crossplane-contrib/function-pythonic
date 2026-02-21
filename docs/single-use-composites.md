# Single use Composites


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
