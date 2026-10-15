import crossplane.pythonic


class TestComposite(crossplane.pythonic.BaseComposite):
    def compose(self):
        self.resources.bucket.apiVersion = "s3.aws.upbound.io/v1beta2"
        self.resources.bucket.kind = "Bucket"
        self.resources.bucket.spec.forProvider.region = "us-east-1"


NotClazz = object()


class NotComposite:
    pass
