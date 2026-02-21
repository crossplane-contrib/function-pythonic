# Usage Dependencies


function-pythonic can be configured to automatically create
[Crossplane Usages](https://docs.crossplane.io/latest/managed-resources/usages/)
dependencies between resources. Modifying the above VPC example with:
```python
self.usages = True

vpc = self.resources.VPC('VPC', 'ec2.aws.crossplane.io/v1beta1')
vpc.spec.forProvider.region = 'us-east-1
vpc.spec.forProvider.cidrBlock = '10.0.0.0/16'

subnet = self.resources.SubnetA('Subnet', 'ec2.aws.crossplane.io/v1beta1')
subnet.spec.forProvider.region = 'us-east-1'
subnet.spec.forProvider.vpcId = vpc.status.atProvider.vpcId
subnet.spec.forProvider.availabilityZone = 'us-east-1a'
subnet.spec.forProvider.cidrBlock = '10.0.0.0/20'
```
Will generate the appropriate Crossplane Usage resource.
