# Introduction


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
            vpc = self.resources.vpc('VPC', 'ec2.aws.crossplane.io/v1beta1')
            vpc.spec.forProvider.region = self.spec.region
            vpc.spec.forProvider.cidrBlock = self.spec.cidr
            self.status.vpcId = vpc.status.atProvider.vpcId
```

In addtion to an inline script, the python implementation can be specified
as the complete path to a python class. Python packages can be deployed using
ConfigMaps, enabling using your IDE of choice for writting the code. See
[ConfigMap Packages](#configmap-packages) and
[Filing System Packages](#filing-system-packages).
