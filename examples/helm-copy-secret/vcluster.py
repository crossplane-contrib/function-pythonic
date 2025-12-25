from crossplane.pythonic import BaseComposite, Map, B64Encode

class VClusterComposite(BaseComposite):

    def compose(self):
        name = self.metadata.name
        namespace = name
        secret_name = f'vc-{name}'

        release = self.resources.release('helm.crossplane.io/v1beta1', 'Release', name=name)
        release.spec.rollbackLimit = 1
        release.spec.forProvider.chart.repository = 'https://charts.loft.sh'
        release.spec.forProvider.chart.name = 'vcluster'
        release.spec.forProvider.chart.version = '0.26.0'
        release.spec.forProvider.namespace = namespace
        release.spec.forProvider.values.controlPlane.proxy.extraSANs[0] = f'{name}.{namespace}'
        vcluster_secret = self.requireds.vcluster_secret('v1', 'Secret', namespace, secret_name)[0]
        argocd_secret = self.resources.argocd_secret('v1', 'Secret', 'argocd', secret_name)
        argocd_secret.metadata.labels['argocd.argoproj.io/secret-type'] = 'cluster'
        argocd_secret.type = 'Opaque'
        argocd_secret.data.name = B64Encode(name)
        argocd_secret.data.server = B64Encode(f'https://{name}.{namespace}:443')
        argocd_secret.data.config = self.argocd_cluster_config(vcluster_secret)
        argocd_secret.ready = argocd_secret.observed

    def argocd_cluster_config(self, vcluster_secret):
        if not vcluster_secret.data:
            return vcluster_secret.data
        config = Map()
        config.tlsClientConfig.insecure = True
        # ArgoCD wants these fields to be B64 encoded, so don't decode them
        config.tlsClientConfig.caData = vcluster_secret.data['certificate-authority']
        config.tlsClientConfig.certData = vcluster_secret.data['client-certificate']
        config.tlsClientConfig.keyData = vcluster_secret.data['client-key']
        return B64Encode(format(config, 'json'))


class VClusterStatusComposite(VClusterComposite):
    def compose(self):
        super(VClusterStatusComposite, self).compose()
        status = False
        state = self.resources.release.status.atProvider.state
        if not state:
            reason = 'VClusterCreated'
            message = 'VCluster Helm release created'
        elif state != 'deployed':
            reason = 'VClusterDeploying'
            message = f"VCluster is deploying: {state}"
        elif not self.requireds.vcluster_secret[0]:
            reason = 'VClusterSecretMissing'
            message = 'Waiting for VCluster Secret'
        elif not self.resources.argocd_secret.ready:
            reason = 'ArgoCDSecretCreated'
            message = 'ArgoCD Secret created'
        else:
            reason = 'AllReady'
            message = 'VCluster and ArgoCD Secret ready'
            status = True

        self.conditions.VClusterReady(reason, message, status)
        if not status:
            self.results.info(reason, message)
            self.ready = False
