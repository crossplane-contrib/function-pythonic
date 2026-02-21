# Explicit Dependencies


At times, the above implicit dependency handling does not account for all cases.
Explicit dependencies can be configured using the resource `addDependency` method.
The dependency's "ready" is used to determine when that dependency is available
for use. The dependency's ready state can either be explictly set, or will be
defaulted to it's auto-ready calculation.

Here is an example of specifying an explicit dependency:
```yaml
crd = self.resources.KarpenterCrdRelease('Release', 'helm.crossplane.io/v1beta1')
crd.spec.deletionPolicy = 'Orphan'
crd.spec.forProvider.chart.repository = 'oci://public.ecr.aws/karpenter'
crd.spec.forProvider.chart.name = 'karpenter-crd'
crd.spec.forProvider.chart.version = '1.8.6'
crd.spec.forProvider.namespace = 'karpenter'
crd.externalName = 'karpenter-crd'
karpenter = self.resources.KarpenterRelease('Release', 'helm.crossplane.io/v1beta1')
karpenter.addDependency(crd)
karpenter.spec.deletionPolicy = 'Orphan'
karpenter.spec.forProvider.chart.repository = 'oci://public.ecr.aws/karpenter'
karpenter.spec.forProvider.chart.name = 'karpenter'
karpenter.spec.forProvider.chart.version = '1.8.6'
karpenter.spec.forProvider.namespace = 'karpenter'
karpenter.externalName = 'karpenter'
```
