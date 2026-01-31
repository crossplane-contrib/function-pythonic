from crossplane.pythonic import BaseComposite

class ResourceGroupComposite(BaseComposite):
    def compose(self):
        labels = {'example.crossplane.io/AzureKubernetesCluster': self.metadata.name}
        self.logger.info(f"Composing Azure ResourceGroup {self.spec.resourceGroupName}")
        
        rg = self.resources.ResourceGroup('ResourceGroup', 'azure.upbound.io/v1beta1')
        rg.metadata.name = self.spec.resourceGroupName
        rg.metadata.labels = labels
        
        rg.spec.forProvider.location = self.spec.location
