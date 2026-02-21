# ConfigMap Packages


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
  package: xpkg.upbound.io/crossplane-contrib/function-pythonic:v0.4.2
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
