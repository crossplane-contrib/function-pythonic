import argparse
import contextlib
import logging
import pathlib
import typing

import kr8s
import pytest
import yaml

from crossplane.pythonic import protobuf, render

# A fake cluster, accessed through Command.kr8s_class and Api.call_api.


class FakeObject:
    def __init__(self, raw):
        self.raw = raw


class FakeCluster:
    def __init__(self):
        self.objects = []
        self.openapi = {}
        self.urls = []

    def add(self, apiVersion, kind, name, namespace=None, labels=None, **fields):
        metadata = {"name": name}
        if namespace:
            metadata["namespace"] = namespace
        if labels:
            metadata["labels"] = labels
        raw = {"apiVersion": apiVersion, "kind": kind, "metadata": metadata, **fields}
        self.objects.append(raw)
        return raw

    def kr8s_class(self, kind, apiVersion, namespaced):
        cluster = self
        kind, apiVersion = str(kind), str(apiVersion)

        def matches(raw, namespace):
            return (
                raw["apiVersion"] == apiVersion
                and raw["kind"] == kind
                and raw["metadata"].get("namespace") == namespace
            )

        class FakeClass:
            @staticmethod
            async def get(name, namespace=None, api=None):
                assert api is cluster
                for raw in cluster.objects:
                    if matches(raw, namespace) and raw["metadata"]["name"] == name:
                        return FakeObject(raw)
                raise kr8s.NotFoundError(name)

            @staticmethod
            async def list(namespace=None, label_selector=None, api=None):
                assert api is cluster
                for raw in cluster.objects:
                    labels = raw["metadata"].get("labels", {})
                    if matches(raw, namespace) and all(
                        labels.get(key) == value
                        for key, value in typing.cast(dict, label_selector).items()
                    ):
                        yield FakeObject(raw)

        return FakeClass

    @contextlib.asynccontextmanager
    async def call_api(self, base, version, url):
        assert base == "/openapi/v3"
        self.urls.append(url)
        if url not in self.openapi:
            raise kr8s.NotFoundError(url)

        class Response:
            def json(_):
                return self.openapi[url]

        yield Response()


@pytest.fixture
def cluster(monkeypatch):
    cluster = FakeCluster()
    monkeypatch.setattr(
        render.Command,
        "kr8s_class",
        lambda self, kind, apiVersion, namespaced: cluster.kr8s_class(
            kind, apiVersion, namespaced
        ),
    )
    return cluster


@pytest.fixture
def command():
    return render.Command(argparse.Namespace())


def Value(**values):
    return protobuf.Value(None, None, values)


def composition(*steps):
    return Value(
        apiVersion="apiextensions.crossplane.io/v1",
        kind="Composition",
        spec={
            "pipeline": [
                {
                    "step": f"step-{ix}",
                    "functionRef": {"name": "function-pythonic"},
                    "input": {
                        "apiVersion": "pythonic.fn.crossplane.io/v1alpha1",
                        "kind": "Composite",
                        "composite": step,
                    },
                    **extra,
                }
                for ix, (step, extra) in enumerate(
                    (step, {}) if isinstance(step, str) else step for step in steps
                )
            ]
        },
    )


def xr(**spec):
    return Value(
        apiVersion="example.org/v1",
        kind="XR",
        metadata={"name": "test", "namespace": "default"},
        spec=spec,
    )


COMPOSE_CM = """\
class Composite(BaseComposite):
    def compose(self):
        self.resources.cm('ConfigMap', 'v1').data.value = 'hello'
"""


# Command.kr8s_class (unpatched)


def test_kr8s_class(command):
    assert command.kr8s_class("ConfigMap", "v1", True) is kr8s.asyncio.objects.ConfigMap
    clazz = command.kr8s_class("Widget", "render.example.org/v1", True)
    assert clazz.kind == "Widget"
    assert clazz.endpoint == "widgets"
    assert clazz.namespaced


# Command.kr8s_get and Command.kr8s_list


@pytest.mark.asyncio
async def test_kr8s_get_and_list(command, cluster, caplog):
    cluster.add("v1", "ConfigMap", "a", "ns", labels={"app": "x"})
    cluster.add("v1", "ConfigMap", "b", "ns", labels={"app": "x"})
    cluster.add("v1", "Namespace", "ns")
    labels = protobuf.Map(app="x")
    with caplog.at_level(logging.DEBUG, logger=render.__name__):
        get = command.kr8s_get
        assert (await get(cluster, "ConfigMap", "v1", "ns", "a")).metadata.name == "a"
        assert (await get(cluster, "Namespace", "v1", None, "ns")).kind == "Namespace"
        assert (await get(cluster, "Namespace", "v1", "", "ns")).kind == "Namespace"
        assert await get(cluster, "ConfigMap", "v1", "ns", "missing") is None
        found = await command.kr8s_list(cluster, "ConfigMap", "v1", "ns", labels)
        missing = await command.kr8s_list(cluster, "Namespace", "v1", None, labels)
    assert [str(resource.metadata.name) for resource in found] == ["a", "b"]
    assert missing == []
    assert "Resource found: ConfigMap:v1:ns:a" in caplog.text
    assert "Resource missing: ConfigMap:v1:ns:missing" in caplog.text
    assert "Resources found two: ConfigMap:v1:ns:app=x" in caplog.text
    assert "Resources missing: Namespace:v1:app=x" in caplog.text


# Command.setup_composite


@pytest.mark.parametrize(
    "spec,namespace",
    [
        ("XR:example.org/v1:default:test", "default"),
        ("XR:example.org/v1::cluster", None),
        ("XR:example.org/v1:cluster", None),
    ],
)
@pytest.mark.asyncio
async def test_setup_composite_from_cluster(command, cluster, spec, namespace):
    cluster.add("example.org/v1", "XR", "test", "default")
    cluster.add("example.org/v1", "XR", "cluster")
    command.args.composite = pathlib.Path(spec)
    composite = await command.setup_composite(cluster)
    assert composite.metadata.namespace == (namespace or protobuf.Unknown())


@pytest.mark.parametrize(
    "spec,error",
    [
        ("XR:test", "is not kind:apiVersion:namespace:name"),
        ("XR:example.org/v1:default:missing", "not found"),
    ],
)
@pytest.mark.asyncio
async def test_setup_composite_errors(command, cluster, capsys, spec, error):
    command.args.composite = pathlib.Path(spec)
    with pytest.raises(SystemExit):
        await command.setup_composite(cluster)
    assert error in capsys.readouterr().err


# Command.render composition lookup


@pytest.mark.parametrize(
    "spec",
    [
        {"crossplane": {"compositionRevisionRef": {"name": "revision"}}},
        {"compositionRevisionRef": {"name": "revision"}},
    ],
    ids=["v2", "v1"],
)
@pytest.mark.asyncio
async def test_render_composition_revision(command, cluster, spec):
    revision = composition(COMPOSE_CM)
    cluster.add(
        "apiextensions.crossplane.io/v1",
        "CompositionRevision",
        "revision",
        spec=yaml.safe_load(str(revision.spec)),
    )
    response = await command.render(xr(**spec), api=cluster)
    assert response.resources[0].data.value == "hello"


@pytest.mark.parametrize(
    "spec,api,error",
    [
        ({}, False, '"composition" required'),
        ({}, True, "Composite does not contain a CompositionRevision name"),
        (
            {"crossplane": {"compositionRevisionRef": {"name": "missing"}}},
            True,
            '"missing" not found',
        ),
    ],
)
@pytest.mark.asyncio
async def test_render_composition_errors(command, cluster, capsys, spec, api, error):
    response = await command.render(xr(**spec), api=cluster if api else None)
    assert response is None
    assert error in capsys.readouterr().err


@pytest.mark.asyncio
async def test_render_pythonic_composite(command):
    composite = Value(
        apiVersion="pythonic.crossplane.io/v1alpha1",
        kind="Composite",
        metadata={"name": "test"},
    )
    response = await command.render(composite)
    assert response.composite.kind == "Composite"
    assert response.results[0].severity == "SEVERITY_FATAL"


@pytest.mark.asyncio
async def test_render_other_function(command, capsys):
    pipeline = composition(COMPOSE_CM)
    pipeline.spec.pipeline[0].functionRef.name = "function-other"
    assert await command.render(xr(), composition=pipeline) is None
    assert "Only function-pythonic functions can be run" in capsys.readouterr().err


# Command.render credentials

COMPOSE_CREDENTIALS = """\
class Composite(BaseComposite):
    def compose(self):
        self.status.password = self.credentials.aws.password
"""


def secret(name, namespace="default", **data):
    return Value(
        apiVersion="v1",
        kind="Secret",
        metadata={"name": name, "namespace": namespace},
        data={key: protobuf.B64Encode(value) for key, value in data.items()},
    )


def credentials_step(namespace="default", name="aws"):
    return (
        COMPOSE_CREDENTIALS,
        {
            "credentials": [
                {
                    "name": "aws",
                    "source": "Secret",
                    "secretRef": {"namespace": namespace, "name": name},
                },
                {"name": "none", "source": "None"},
            ]
        },
    )


@pytest.mark.asyncio
async def test_render_credentials(command):
    response = await command.render(
        xr(),
        composition=composition(credentials_step()),
        resources=[secret("other"), secret("aws", password="secret")],
    )
    assert response.composite.status.password == "secret"


@pytest.mark.asyncio
async def test_render_credentials_missing(command, capsys):
    response = await command.render(
        xr(), composition=composition(credentials_step(name="missing"))
    )
    assert response is None
    assert "secret not found: default/missing" in capsys.readouterr().err


# Command.render required resources

COMPOSE_REQUIRED = """\
class Composite(BaseComposite):
    def compose(self):
        named = self.requireds.named('ConfigMap', 'v1', 'default', 'named')
        self.status.named = named[0].data.value
        labeled = self.requireds.labeled('ConfigMap', 'v1', 'default', labels={'app': 'x'})
        self.status.labeled = [str(item.metadata.name) for item in labeled]
        cluster = self.requireds.cluster('Namespace', 'v1', name='cluster')
        self.status.cluster = cluster[0].metadata.name
        listed = self.requireds.listed('Namespace', 'v1', labels={'app': 'x'})
        self.status.listed = [str(item.metadata.name) for item in listed]
        self.requireds.empty('ConfigMap', 'v1', 'default', 'missing')
"""


def required_step():
    return (
        COMPOSE_REQUIRED,
        {
            "requirements": {
                # Requirements without a name are ignored.
                "requiredResources": [{"apiVersion": "v1", "kind": "ConfigMap"}]
            }
        },
    )


def configmap(name, namespace="default", labels=None, value=None):
    metadata = {"name": name, "namespace": namespace}
    if labels:
        metadata["labels"] = labels
    return Value(
        apiVersion="v1",
        kind="ConfigMap",
        metadata=metadata,
        data={"value": value or name},
    )


@pytest.mark.asyncio
async def test_render_required_local(command):
    response = await command.render(
        xr(),
        composition=composition(required_step()),
        resources=[
            configmap("named"),
            configmap("a", labels={"app": "x"}),
            configmap("b", labels={"app": "y"}),
            configmap("c", labels={"app": "x"}),
            Value(apiVersion="v1", kind="Namespace", metadata={"name": "cluster"}),
        ],
    )
    status = response.composite.status
    assert status.named == "named"
    assert status.labeled == ["a", "c"]
    assert status.cluster == "cluster"
    assert status.listed == []


@pytest.mark.asyncio
async def test_render_required_cluster(command, cluster):
    cluster.add("v1", "ConfigMap", "named", "default", data={"value": "named"})
    cluster.add("v1", "ConfigMap", "a", "default", labels={"app": "x"})
    cluster.add("v1", "Namespace", "cluster")
    cluster.add("v1", "Namespace", "listed", labels={"app": "x"})
    response = await command.render(
        xr(), composition=composition(required_step()), api=cluster
    )
    status = response.composite.status
    assert status.named == "named"
    assert status.labeled == ["a"]
    assert status.cluster == "cluster"
    assert status.listed == ["listed"]


COMPOSE_BOOTSTRAP = """\
class Composite(BaseComposite):
    def compose(self):
        self.status.named = self.requireds.named[0].data.value
        self.status.labeled = [str(item.metadata.name) for item in self.requireds.labeled]
"""


@pytest.mark.asyncio
async def test_render_bootstrap_required(command):
    step = {
        "requirements": {
            "requiredResources": [
                {
                    "requirementName": "named",
                    "apiVersion": "v1",
                    "kind": "ConfigMap",
                    "namespace": "default",
                    "name": "named",
                },
                {
                    "requirementName": "labeled",
                    "apiVersion": "v1",
                    "kind": "ConfigMap",
                    "namespace": "default",
                    "matchLabels": {"app": "x"},
                },
            ]
        }
    }
    response = await command.render(
        xr(),
        composition=composition((COMPOSE_BOOTSTRAP, step)),
        resources=[configmap("named"), configmap("a", labels={"app": "x"})],
    )
    status = response.composite.status
    assert status.named == "named"
    assert status.labeled == ["a"]


COMPOSE_EXTRA = """\
class Composite(BaseComposite):
    def compose(self):
        self.status.extra = self.requireds.extra('ConfigMap', 'v1', 'default', 'named')[0].data.value
"""


@pytest.mark.asyncio
async def test_render_extra_resources(command):
    response = await command.render(
        xr(),
        composition=composition(COMPOSE_EXTRA),
        resources=[configmap("named")],
        crossplane_v1=True,
    )
    assert response.composite.status.extra == "named"


# Command.render required schemas

COMPOSE_SCHEMAS = """\
class Composite(BaseComposite):
    def compose(self):
        self.status.core = self.schemas.core('v1', 'ConfigMap').properties.data.type
        self.status.group = self.schemas.group('example.org/v1', 'Widget').properties.spec.properties.size.type
        self.status.missing = len(self.schemas.missing('missing.org/v1', 'Missing'))
"""


def openapi(group, version, kind, schema, **schemas):
    return {
        "components": {
            "schemas": {
                f"{group}.{version}.{kind}": {
                    "x-kubernetes-group-version-kind": [
                        {"group": group, "version": version, "kind": kind}
                    ],
                    **schema,
                },
                **schemas,
            }
        }
    }


WIDGET = openapi(
    "example.org",
    "v1",
    "Widget",
    {
        "type": "object",
        "properties": {"spec": {"allOf": [{"$ref": "#/components/schemas/Spec"}]}},
        "required": ["spec"],
    },
    Spec={
        "type": "object",
        "properties": {
            "size": {"type": "integer"},
            "self": {"$ref": "#/components/schemas/Spec"},
        },
    },
)
CONFIGMAP = openapi("", "v1", "ConfigMap", {"properties": {"data": {"type": "object"}}})


@pytest.mark.asyncio
async def test_render_required_schemas_local(command):
    response = await command.render(
        xr(),
        composition=composition(COMPOSE_SCHEMAS),
        schemas=[
            protobuf.Value(None, None, CONFIGMAP),
            protobuf.Value(None, None, WIDGET),
        ],
    )
    status = response.composite.status
    assert status.core == "object"
    assert status.group == "integer"
    assert status.missing == 0


@pytest.mark.asyncio
async def test_render_required_schemas_cluster(command, cluster):
    cluster.openapi["api/v1"] = CONFIGMAP
    cluster.openapi["apis/example.org/v1"] = WIDGET
    response = await command.render(
        xr(), composition=composition(COMPOSE_SCHEMAS), api=cluster
    )
    status = response.composite.status
    assert status.core == "object"
    assert status.group == "integer"
    assert status.missing == 0
    assert sorted(set(cluster.urls)) == [
        "api/v1",
        "apis/example.org/v1",
        "apis/missing.org/v1",
    ]


def test_resolve_ref_guards(command):
    schema = protobuf.Map()
    document = protobuf.Value(None, None, WIDGET)
    command.resolve_ref(document, set(), protobuf.Unknown(), schema)
    command.resolve_ref(document, set(), "http://elsewhere#/Spec", schema)
    command.resolve_ref(
        document, {"#/components/schemas/Spec"}, "#/components/schemas/Spec", schema
    )
    command.copy_schema(document, set(), "allOf", protobuf.List({}, {}), schema)
    assert schema == {}


# Command.render observed resources and connection secrets

COMPOSE_OBSERVED = """\
class Composite(BaseComposite):
    def compose(self):
        bucket = self.resources.bucket('Bucket', 'example.org/v1')
        bucket.spec.size = 1
        self.status.observed = bucket.observed.status.id
        self.status.secret = bucket.connection.password
        self.status.manual = self.resources.manual.observed.status.id
"""


def bucket(name, id, secret=None):
    resource = {
        "apiVersion": "example.org/v1",
        "kind": "Bucket",
        "metadata": {
            "name": name,
            "namespace": "default",
            "annotations": {"crossplane.io/composition-resource-name": name},
        },
        "status": {"id": id},
    }
    if secret:
        resource["spec"] = {"writeConnectionSecretToRef": {"name": secret}}
    return resource


@pytest.mark.asyncio
async def test_render_composite_observeds(command, cluster):
    cluster.objects.append(bucket("bucket", "cluster", secret="bucket-secret"))
    cluster.objects.append(bucket("manual", "cluster"))
    cluster.objects.append(
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": "bucket-secret", "namespace": "default"},
            "data": {"password": protobuf.B64Encode("secret")},
        }
    )
    cluster.add("example.org/v1", "Bucket", "unnamed", "default")
    refs = [
        {"apiVersion": "example.org/v1", "kind": "Bucket", "name": name}
        for name in ("bucket", "manual", "unnamed", "missing")
    ]
    composite = xr(crossplane={"resourceRefs": refs})
    response = await command.render(
        composite,
        observed=[
            protobuf.Value(None, None, bucket("manual", "manual")),
            Value(kind="NoName"),
        ],
        composition=composition(COMPOSE_OBSERVED),
        api=cluster,
        composite_observeds=True,
    )
    status = response.composite.status
    assert status.observed == "cluster"
    assert status.secret == "secret"
    assert status.manual == "manual"
    assert sorted(name for name, _ in response.observed) == ["bucket", "manual"]


@pytest.mark.asyncio
async def test_render_composite_observeds_v1(command, cluster):
    cluster.objects.append(bucket("bucket", "cluster"))
    composite = xr(
        resourceRefs=[
            {
                "apiVersion": "example.org/v1",
                "kind": "Bucket",
                "name": "bucket",
                "namespace": "default",
            }
        ]
    )
    del composite.metadata.namespace
    response = await command.render(
        composite,
        composition=composition(COMPOSE_OBSERVED),
        api=cluster,
        composite_observeds=True,
    )
    assert response.composite.status.observed == "cluster"


# Command.render composed resource metadata


@pytest.mark.parametrize(
    "composite,namespace,name",
    [
        (
            {
                "metadata": {
                    "labels": {
                        "crossplane.io/claim-namespace": "claims",
                        "crossplane.io/claim-name": "claim",
                    }
                }
            },
            "claims",
            "claim",
        ),
        ({"spec": {"claimRef": {"namespace": "refs", "name": "ref"}}}, "refs", "ref"),
    ],
    ids=["labels", "claimRef"],
)
@pytest.mark.asyncio
async def test_render_claim_labels(command, composite, namespace, name):
    composite = protobuf.Value(
        None,
        None,
        {
            "apiVersion": "example.org/v1",
            "kind": "XR",
            "metadata": {"name": "test", **composite.get("metadata", {})},
            **({"spec": composite["spec"]} if "spec" in composite else {}),
        },
    )
    response = await command.render(composite, composition=composition(COMPOSE_CM))
    labels = response.resources[0].metadata.labels
    assert labels["crossplane.io/claim-namespace"] == namespace
    assert labels["crossplane.io/claim-name"] == name


# Command.create_condition


def test_create_condition(command):
    status = protobuf.Message(
        None,
        "condition",
        render.fnv1.Condition.DESCRIPTOR,
        render.fnv1.Condition(),
    ).status
    assert command.create_condition("A", status, "R")["status"] == "Unknown"
    assert command.create_condition("A", None, "R")["status"] == "Unknown"
    assert command.create_condition("A", False, "R", "M") == {
        "type": "A",
        "status": "False",
        "reason": "R",
        "message": "M",
        "lastTransitionTime": "2026-01-01T00:00:00Z",
    }


# Command.run against a cluster


@pytest.mark.asyncio
async def test_run_kube_context(cluster, monkeypatch, capsys):
    async def api(context):
        assert context == "test"
        return cluster

    monkeypatch.setattr(kr8s.asyncio, "api", api)
    cluster.add("example.org/v1", "XR", "test", "default", spec={"value": "x"})
    parser = argparse.ArgumentParser()
    render.Command.create(parser.add_subparsers())
    args = parser.parse_args(
        ["render", "--kube-context=test", "XR:example.org/v1:default:test"]
    )
    with pytest.raises(SystemExit):
        await args.command(args).run()
    assert (
        "Composite does not contain a CompositionRevision name"
        in capsys.readouterr().err
    )
