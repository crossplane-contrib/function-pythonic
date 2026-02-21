# Enable Oversize Protos


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
