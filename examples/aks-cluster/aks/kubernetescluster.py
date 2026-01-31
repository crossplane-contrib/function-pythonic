from crossplane.pythonic import BaseComposite

class KubernetesClusterComposite(BaseComposite):
    def compose(self):
        labels = {'example.crossplane.io/AzureKubernetesCluster': self.metadata.name}
        self.logger.info(f"Composing AKS cluster {self.metadata.name}")
        
        aks = self.resources.KubernetesCluster(
            'KubernetesCluster', 'containerservice.azure.upbound.io/v1beta2'
        )
        aks.metadata.name = self.metadata.name
        aks.metadata.labels = labels
        
        aks.spec.forProvider.location = self.spec.location
        aks.spec.forProvider.resourceGroupNameRef.name = self.spec.resourceGroupName
        aks.spec.forProvider.identity.type = 'SystemAssigned'

        if self.spec.defaultNodePool.autoScaling.enabled:
            aks.spec.forProvider.defaultNodePool.autoScalingEnabled = True
            aks.spec.forProvider.defaultNodePool.minCount = self.spec.defaultNodePool.autoScaling.minCount
            aks.spec.forProvider.defaultNodePool.maxCount = self.spec.defaultNodePool.autoScaling.maxCount
        else:
            aks.spec.forProvider.defaultNodePool.nodeCount = self.spec.nodeCount

        aks.spec.forProvider.defaultNodePool.name = self.spec.defaultNodePool.name
        aks.spec.forProvider.defaultNodePool.vmSize = self.spec.vmSize
        aks.spec.forProvider.dnsPrefix = self.metadata.name

        self.status.aks = aks.status.endpoint
