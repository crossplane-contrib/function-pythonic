# Installing function-pythonic


```yaml
apiVersion: pkg.crossplane.io/v1
kind: Function
metadata:
  name: function-pythonic
spec:
  package: xpkg.upbound.io/crossplane-contrib/function-pythonic:v0.4.2
```

### Crossplane V1
When running function-pythonic in Crossplane V1, the `--crossplane-v1` command line
option should be specified. This requires using a Crossplane DeploymentRuntimeConfig.
```yaml
apiVersion: pkg.crossplane.io/v1
kind: Function
metadata:
  name: function-pythonic
spec:
  package: xpkg.upbound.io/crossplane-contrib/function-pythonic:v0.4.2
  runtimeConfigRef:
    name: function-pythonic
--
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
            - --crossplane-v1
```
