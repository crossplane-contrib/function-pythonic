# Install Additional Python Packages


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
