# Composed Resource Dependencies


function-pythonic automatically handles dependencies between composed resources.

Just compose everything as if it is immediately created and the framework will delay
the creation of any resources which depend on other resources which do not exist yet.
In other words, it accomplishes what [function-sequencer](https://github.com/crossplane-contrib/function-sequencer)
provides, but it automatically detects the dependencies.

If a resource has been created and a dependency no longer exists due to some unexpected
condition, the composition will be terminated or the observed value for that field will
be used, depending on the `unknownsFatal` settings.

Take the following example:
```python
vpc = self.resources.VPC('VPC', 'ec2.aws.crossplane.io/v1beta1')
vpc.spec.forProvider.region = 'us-east-1
vpc.spec.forProvider.cidrBlock = '10.0.0.0/16'

subnet = self.resources.SubnetA('Subnet', 'ec2.aws.crossplane.io/v1beta1')
subnet.spec.forProvider.region = 'us-east-1'
subnet.spec.forProvider.vpcId = vpc.status.atProvider.vpcId
subnet.spec.forProvider.availabilityZone = 'us-east-1a'
subnet.spec.forProvider.cidrBlock = '10.0.0.0/20'
```
If the Subnet does not yet exist, the framework will detect if the vpcId set
in the Subnet is unknown, and will delay the creation of the subnet.

Once the Subnet has been created, if for some unexpected reason the vpcId passed
to the Subnet is unknown, the framework will detect it and either terminate
the Composite composition or use the vpcId in the observed Subnet. The default
action taken is to fast fail by terminating the composition. This can be
overridden for all composed resource by setting the Composite `self.unknownsFatal` field
to False, or at the individual composed resource level by setting the
`Resource.unknownsFatal` field to False.
