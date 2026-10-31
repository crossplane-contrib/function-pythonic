"""Tests of composite.py, using BaseComposite directly without the function runner."""

import datetime
import logging

import pytest

from crossplane.pythonic import BaseComposite, protobuf
from crossplane.pythonic.proto.v1 import run_function_pb2 as fnv1
from tests import utils

XR = {
    "apiVersion": "example.crossplane.io/v1",
    "kind": "XR",
    "metadata": {"name": "xr", "namespace": "default"},
    "spec": {"region": "us-east-1"},
}


def composite(request=None, crossplane_v1=False, xr=True) -> BaseComposite:
    message = fnv1.RunFunctionRequest()
    if xr:
        utils.message_merge(message, {"observed": {"composite": {"resource": XR}}})
    if request:
        utils.message_merge(message, request)
    return BaseComposite(crossplane_v1, message, logging.getLogger("test"))


def response(composite):
    return utils.message_dict(composite.response._message)


# BaseComposite


def test_base_composite_fields():
    xr = composite(
        {
            "meta": {"tag": "tag"},
            "input": {"parameters": {"size": 3}},
            "context": {"apiextensions.crossplane.io/environment": {"env": "dev"}},
        }
    )
    assert xr.apiVersion == "example.crossplane.io/v1"
    assert xr.kind == "XR"
    assert xr.metadata.name == "xr"
    assert xr.spec.region == "us-east-1"
    assert xr.parameters.size == 3
    assert xr.environment.env == "dev"
    assert xr.response.meta.tag == "tag"
    assert xr.ttl == 60
    assert xr.autoReady is True
    assert xr.usages is False
    assert xr.unknownsFatal is False
    assert not xr.watched


def test_status_writes_desired():
    xr = composite()
    xr.status.vpcId = "vpc-1"
    assert response(xr)["desired"]["composite"]["resource"] == {
        "status": {"vpcId": "vpc-1"}
    }


@pytest.mark.asyncio
async def test_compose_not_implemented():
    with pytest.raises(NotImplementedError):
        await composite().compose()


# TTL


def test_ttl_int():
    xr = composite()
    xr.ttl = 30
    assert xr.ttl == 30
    assert response(xr)["meta"]["ttl"] == {"seconds": 30}


def test_ttl_int_type():
    xr = composite()
    xr.ttl = 30
    assert isinstance(xr.ttl, int)


def test_ttl_float():
    xr = composite()
    xr.ttl = 1.5
    assert xr.ttl == 1.5
    xr.ttl = 2.0
    assert xr.ttl == 2
    assert response(xr)["meta"]["ttl"] == {"seconds": 2}


def test_ttl_type_error():
    with pytest.raises(TypeError):
        composite().ttl = "60"  #  ty: ignore[invalid-assignment]


# Ready


@pytest.mark.parametrize(
    "ready,expected,enum",
    [
        (True, True, fnv1.Ready.READY_TRUE),
        (False, False, fnv1.Ready.READY_FALSE),
        (None, None, fnv1.Ready.READY_UNSPECIFIED),
    ],
)
def test_composite_ready(ready, expected, enum):
    xr = composite()
    xr.ready = ready
    assert xr.ready is expected
    assert xr.response.desired.composite._message.ready == enum  #  ty: ignore[unresolved-attribute]


def test_composite_ready_from_desired():
    assert composite({"desired": {"composite": {"ready": 1}}}).ready is True
    assert composite({"desired": {"composite": {"ready": 2}}}).ready is False
    assert composite().ready is None


# Capabilities


def test_capabilities_absent():
    caps = composite().capabilities
    assert not caps
    assert caps.requireds is None
    assert caps.credentials is None
    assert caps.conditions is None
    assert caps.schemas is None


def test_capabilities_present():
    xr = composite()
    xr.request._message.meta.capabilities.extend(  #  ty: ignore[unresolved-attribute]
        [
            fnv1.CAPABILITY_CAPABILITIES,
            fnv1.CAPABILITY_REQUIRED_RESOURCES,
            fnv1.CAPABILITY_CONDITIONS,
        ]
    )
    caps = xr.capabilities
    assert caps
    assert caps.requireds is True
    assert caps.conditions is True
    assert caps.credentials is False
    assert caps.schemas is False


# Credentials


def test_credentials():
    xr = composite(
        {
            "credentials": {
                "aws": {"credential_data": {"data": {"key": b"secret", "id": b"me"}}}
            }
        }
    )
    assert xr.credentials
    assert len(xr.credentials) == 1
    assert "aws" in xr.credentials
    assert "gcp" not in xr.credentials
    aws = xr.credentials.aws
    assert aws
    assert len(aws) == 2
    assert "key" in aws
    assert aws.key == "secret"
    assert sorted(aws) == [("id", "me"), ("key", "secret")]
    assert [name for name, credential in xr.credentials] == ["aws"]


def test_credentials_empty():
    xr = composite()
    assert len(xr.credentials) == 0
    assert "missing" not in xr.credentials
    assert not xr.credentials["missing"]


# Resources


def test_resources_create():
    xr = composite()
    assert len(xr.resources) == 0
    vpc = xr.resources.vpc("VPC", "ec2.aws.crossplane.io/v1beta1", "ns", "name")
    vpc.spec.forProvider.region = xr.spec.region
    assert xr.resources.vpc is vpc
    assert xr.resources
    assert len(xr.resources) == 1
    assert "vpc" in xr.resources
    assert [name for name, resource in xr.resources] == ["vpc"]
    assert response(xr)["desired"]["resources"]["vpc"]["resource"] == {
        "apiVersion": "ec2.aws.crossplane.io/v1beta1",
        "kind": "VPC",
        "metadata": {"namespace": "ns", "name": "name"},
        "spec": {"forProvider": {"region": "us-east-1"}},
    }


@pytest.mark.parametrize(
    "args,apiVersion,kind",
    [
        (("v1", "ConfigMap"), "v1", "ConfigMap"),
        (("apps/v1", "Deployment"), "apps/v1", "Deployment"),
        (("ConfigMap", "v1"), "v1", "ConfigMap"),
        (("apps/v1",), "apps/v1", None),
    ],
)
def test_resource_call_argument_order(args, apiVersion, kind):
    resource = composite().resources.r(*args)
    assert resource.apiVersion == apiVersion
    if kind:
        assert resource.kind == kind
    else:
        assert not resource.kind


def test_resources_set_and_delete():
    xr = composite()
    xr.resources.cm = {"apiVersion": "v1", "kind": "ConfigMap"}
    xr.resources["secret"] = {"apiVersion": "v1", "kind": "Secret"}
    assert len(xr.resources) == 2
    assert xr.resources.cm.kind == "ConfigMap"
    del xr.resources.cm
    del xr.resources["secret"]
    del xr.resources["never-existed"]
    assert len(xr.resources) == 0


def test_resource_fields():
    xr = composite(
        {
            "observed": {
                "resources": {
                    "secret": {
                        "resource": {
                            "metadata": {"name": "observed-secret"},
                            "status": {"phase": "Bound"},
                        },
                        "connection_details": {"password": b"pw"},
                    }
                }
            }
        }
    )
    secret = xr.resources.secret("v1", "Secret")
    secret.metadata = {"name": "secret"}
    secret.spec = {"unused": True}
    secret.type = "Opaque"
    secret.data = {"key": "dmFsdWU="}
    assert secret.metadata.name == "secret"
    assert secret.spec.unused == True
    assert secret.type == "Opaque"
    assert secret.data.key == "dmFsdWU="
    assert secret.status.phase == "Bound"
    assert secret.observed.metadata.name == "observed-secret"
    assert secret.connection.password == "pw"


def test_resource_external_name():
    xr = composite(
        {
            "observed": {
                "resources": {
                    "vpc": {
                        "resource": {
                            "metadata": {
                                "annotations": {"crossplane.io/external-name": "vpc-1"}
                            }
                        }
                    }
                }
            }
        }
    )
    vpc = xr.resources.vpc
    assert vpc.externalName == "vpc-1"
    # Reading an observed external name copies it to desired.
    assert vpc.metadata.annotations["crossplane.io/external-name"] == "vpc-1"
    vpc.externalName = "vpc-2"
    assert vpc.externalName == "vpc-2"
    assert not xr.resources.other.externalName


@pytest.mark.parametrize(
    "ready,enum",
    [
        (True, fnv1.Ready.READY_TRUE),
        (False, fnv1.Ready.READY_FALSE),
        (None, fnv1.Ready.READY_UNSPECIFIED),
    ],
)
def test_resource_ready_setter(ready, enum):
    resource = composite().resources.r("v1", "ConfigMap")
    resource.ready = ready
    assert resource.ready is ready
    assert resource.desired._parent._message.ready == enum  #  ty: ignore[unresolved-attribute]


@pytest.mark.parametrize("ready,expected", [(1, True), (2, False)])
def test_resource_ready_from_desired(ready, expected):
    xr = composite({"desired": {"resources": {"r": {"ready": ready}}}})
    assert xr.resources.r.ready is expected


def test_resource_ready_auto_ready():
    xr = composite(
        {
            "observed": {
                "resources": {
                    "cm": {
                        "resource": {
                            "apiVersion": "v1",
                            "kind": "ConfigMap",
                            "metadata": {"name": "cm"},
                        }
                    }
                }
            }
        }
    )
    cm = xr.resources.cm("v1", "ConfigMap")
    assert cm.ready
    assert cm.desired._parent._message.ready == fnv1.Ready.READY_TRUE  #  ty: ignore[unresolved-attribute]


@pytest.mark.parametrize("composite_auto,resource_auto", [(False, None), (True, False)])
def test_resource_ready_auto_ready_disabled(composite_auto, resource_auto):
    xr = composite(
        {
            "observed": {
                "resources": {
                    "cm": {
                        "resource": {
                            "apiVersion": "v1",
                            "kind": "ConfigMap",
                            "metadata": {"name": "cm"},
                        }
                    }
                }
            }
        }
    )
    xr.autoReady = composite_auto
    cm = xr.resources.cm("v1", "ConfigMap")
    cm.autoReady = resource_auto
    assert cm.ready is None


def observed_condition(status, reason=None):
    condition = {"type": "Ready", "status": status}
    if reason:
        condition["reason"] = reason
    return composite(
        {
            "observed": {
                "resources": {
                    "r": {
                        "resource": {
                            "metadata": {"name": "r"},
                            "status": {"conditions": [condition]},
                        }
                    }
                }
            }
        }
    ).resources.r


def test_set_ready_condition_true():
    resource = observed_condition("True")
    resource.setReadyCondition()
    assert resource.ready == "r"


def test_set_ready_condition_false_with_reason():
    resource = observed_condition("False", "Creating")
    resource.setReadyCondition()
    assert not resource.ready
    assert resource.ready._isUnknown


def test_set_ready_condition_false_without_reason():
    resource = observed_condition("False")
    resource.setReadyCondition()
    assert not resource.ready


def test_add_dependency_ready():
    xr = composite(
        {"observed": {"resources": {"a": {"resource": {"metadata": {"name": "a"}}}}}}
    )
    a = xr.resources.a("v1", "ConfigMap")
    a.ready = True
    b = xr.resources.b("v1", "ConfigMap")
    b.addDependency(a)
    assert b.metadata.annotations["pythonic.dependency/a"] == "a"


def test_add_dependency_not_ready():
    xr = composite()
    a = xr.resources.a("example.org/v1", "Thing")
    b = xr.resources.b("v1", "ConfigMap")
    b.addDependency(a)
    assert a.ready is False
    assert not b.metadata.annotations["pythonic.dependency/a"]


def test_add_dependency_none_field():
    xr = composite(
        {"observed": {"resources": {"a": {"resource": {"metadata": {"name": "a"}}}}}}
    )
    b = xr.resources.b("v1", "ConfigMap")
    b.addDependency(xr.resources.a, None)
    assert b.metadata.annotations["pythonic.dependency/a"] == "a"


def test_add_dependency_field():
    xr = composite(
        {
            "observed": {
                "resources": {
                    "a": {"resource": {"status": {"atProvider": {"id": "id-1"}}}}
                }
            }
        }
    )
    a = xr.resources.a
    b = xr.resources.b("v1", "ConfigMap")
    b.addDependency(a, a.status.atProvider.id)
    assert b.metadata.annotations["pythonic.dependency/a"] == "id-1"


# Requireds


@pytest.mark.parametrize("crossplane_v1", [False, True])
def test_requireds(crossplane_v1):
    field = "extra_resources" if crossplane_v1 else "required_resources"
    xr = composite(
        {
            field: {
                "cms": {
                    "items": [
                        {
                            "resource": {
                                "apiVersion": "v1",
                                "kind": "ConfigMap",
                                "metadata": {"name": "one"},
                                "data": {"key": "value"},
                            }
                        }
                    ]
                }
            }
        },
        crossplane_v1,
    )
    assert xr.requireds
    assert len(xr.requireds) == 1
    assert "cms" in xr.requireds
    assert "other" not in xr.requireds
    cms = xr.requireds.cms
    assert xr.requireds["cms"] is cms
    assert cms
    assert len(cms) == 1
    one = cms[0]
    assert cms[0] is one
    assert one
    assert one.name == "cms"
    assert one.ix == 0
    assert one.metadata.name == "one"
    assert one.data.key == "value"
    assert [resource.metadata.name for resource in cms] == ["one"]
    # Requesting another required resource adds it to the requirements.
    xr.requireds.secrets("v1", "Secret", "ns", "name")
    assert len(xr.requireds) == 2
    assert "secrets" in xr.requireds
    assert [name for name, required in xr.requireds] == ["cms", "secrets"]
    assert not xr.requireds.secrets
    requirements = response(xr)["requirements"][
        "extra_resources" if crossplane_v1 else "resources"
    ]
    assert requirements == {
        "secrets": {
            "api_version": "v1",
            "kind": "Secret",
            "namespace": "ns",
            "match_name": "name",
        }
    }


def test_requireds_empty():
    xr = composite()
    assert not xr.requireds
    assert len(xr.requireds) == 0
    assert list(xr.requireds) == []
    assert not xr.requireds.missing[0]


@pytest.mark.parametrize(
    "labels",
    [
        {"app": "web"},
        protobuf.Map(app="web"),
    ],
    ids=["dict", "map"],
)
def test_required_match_labels(labels):
    xr = composite()
    required = xr.requireds.web("apps/v1", "Deployment", labels=labels)
    assert required.apiVersion == "apps/v1"
    assert required.kind == "Deployment"
    assert required.matchLabels.app == "web"
    required.matchLabels = None
    assert len(required.matchLabels) == 0


def test_required_argument_order():
    required = composite().requireds.cm("ConfigMap", "v1")
    assert required.apiVersion == "v1"
    assert required.kind == "ConfigMap"
    assert required.namespace == ""
    assert required.matchName == ""


# Schemas


def test_schemas():
    xr = composite(
        {
            "required_schemas": {
                "xr": {
                    "openapi_v3": {
                        "type": "object",
                        "properties": {"spec": {"type": "object"}},
                    }
                }
            }
        }
    )
    assert xr.schemas
    assert len(xr.schemas) == 1
    assert "xr" in xr.schemas
    assert "other" not in xr.schemas
    schema = xr.schemas.xr
    assert xr.schemas["xr"] is schema
    assert schema
    assert len(schema) == 2
    assert "properties" in schema
    assert schema.type == "object"
    assert schema["properties"].spec.type == "object"
    assert sorted(key for key, value in schema) == ["properties", "type"]
    assert schema == xr.schemas.xr
    assert schema == {"type": "object", "properties": {"spec": {"type": "object"}}}
    assert hash(schema) == hash(schema._schema)
    assert "type: object" in str(schema)
    assert "type: object" in format(schema, "yaml")
    with schema as entered:
        assert entered is schema
    # Requesting another schema adds it to the requirements.
    other = xr.schemas.other("example.org/v1", "Thing")
    assert not other
    assert other.apiVersion == "example.org/v1"
    assert other.kind == "Thing"
    assert len(xr.schemas) == 2
    assert [name for name, schema in xr.schemas] == ["other", "xr"]
    assert response(xr)["requirements"]["schemas"] == {
        "other": {"api_version": "example.org/v1", "kind": "Thing"}
    }


def test_schema_argument_order():
    schema = composite().schemas.cm("ConfigMap", "v1")
    assert schema.apiVersion == "v1"
    assert schema.kind == "ConfigMap"


def test_schemas_empty():
    xr = composite()
    assert not xr.schemas
    assert list(xr.schemas) == []


# Conditions


def conditions_composite():
    return composite(
        {
            "observed": {
                "composite": {
                    "resource": {
                        "status": {
                            "conditions": [
                                {
                                    "type": "Synced",
                                    "status": "True",
                                    "reason": "ReconcileSuccess",
                                    "lastTransitionTime": "2026-01-01T00:00:00Z",
                                },
                                {"type": "Ready", "status": "False"},
                            ]
                        }
                    }
                }
            }
        }
    )


def test_conditions_observed():
    xr = conditions_composite()
    assert xr.conditions
    assert len(xr.conditions) == 2
    assert [condition.type for condition in xr.conditions] == ["Ready", "Synced"]
    synced = xr.conditions.Synced
    assert synced.status is True
    assert synced.reason == "ReconcileSuccess"
    assert not synced.message
    assert synced.lastTransitionTime == datetime.datetime(
        2026, 1, 1, tzinfo=datetime.UTC
    )
    assert synced.claim is False
    assert synced._protobuf_value == {
        "type": "Synced",
        "status": "True",
        "reason": "ReconcileSuccess",
        "message": "",
        "lastTransitionTime": "2026-01-01T00:00:00Z",
    }
    assert xr.conditions.Ready.status is False
    missing = xr.conditions.Missing
    assert missing.status is None
    assert missing.reason is None
    assert missing.message is None
    assert missing.lastTransitionTime is None
    assert missing._protobuf_value["status"] == "Unknown"


def test_conditions_set():
    xr = composite()
    assert len(xr.conditions) == 0
    xr.conditions.Ready("Available", "All good", True, True)
    ready = xr.conditions.Ready
    assert len(xr.conditions) == 1
    assert ready.status is True
    assert ready.reason == "Available"
    assert ready.message == "All good"
    assert ready.claim is True
    assert response(xr)["conditions"] == [
        {
            "type": "Ready",
            "status": fnv1.Status.STATUS_CONDITION_TRUE,
            "reason": "Available",
            "message": "All good",
            "target": fnv1.Target.TARGET_COMPOSITE_AND_CLAIM,
        }
    ]


@pytest.mark.parametrize(
    "status,enum",
    [
        (True, fnv1.Status.STATUS_CONDITION_TRUE),
        (False, fnv1.Status.STATUS_CONDITION_FALSE),
        (None, fnv1.Status.STATUS_CONDITION_UNKNOWN),
        (protobuf.Unknown(), fnv1.Status.STATUS_CONDITION_UNSPECIFIED),
    ],
    ids=["true", "false", "none", "unknown"],
)
def test_condition_status_setter(status, enum):
    xr = composite()
    xr.conditions.Ready.status = status
    assert xr.response.conditions[0]._message.status == enum  #  ty: ignore[unresolved-attribute]


@pytest.mark.parametrize(
    "claim,enum",
    [
        (True, fnv1.Target.TARGET_COMPOSITE_AND_CLAIM),
        (False, fnv1.Target.TARGET_COMPOSITE),
        (None, fnv1.Target.TARGET_UNSPECIFIED),
        (protobuf.Unknown(), fnv1.Target.TARGET_UNSPECIFIED),
    ],
    ids=["true", "false", "none", "unknown"],
)
def test_condition_claim_setter(claim, enum):
    xr = composite()
    xr.conditions.Ready.claim = claim
    assert xr.response.conditions[0]._message.target == enum  #  ty: ignore[unresolved-attribute]


def test_condition_response_overrides_observed():
    xr = conditions_composite()
    xr.conditions.Synced(status=False)
    assert xr.conditions.Synced.status is False
    assert len(xr.conditions) == 2


def test_resource_conditions_read_only():
    resource = observed_condition("True").conditions.Ready
    assert resource.status is True
    with pytest.raises(ValueError, match="read only"):
        resource.status = False


# Results


@pytest.mark.parametrize(
    "method,severity",
    [
        ("info", fnv1.Severity.SEVERITY_NORMAL),
        ("warning", fnv1.Severity.SEVERITY_WARNING),
        ("fatal", fnv1.Severity.SEVERITY_FATAL),
    ],
)
def test_results(method, severity):
    xr = composite()
    assert not xr.results
    result = getattr(xr.results, method)("Reason", "Message", True)
    assert result
    assert getattr(result, method) is True
    assert result.reason == "Reason"
    assert result.message == "Message"
    assert result.claim is True
    assert len(xr.results) == 1
    assert xr.results[0].reason == "Reason"
    assert [result.message for result in xr.results] == ["Message"]
    assert response(xr)["results"] == [
        {
            "severity": severity,
            "reason": "Reason",
            "message": "Message",
            "target": fnv1.Target.TARGET_COMPOSITE_AND_CLAIM,
        }
    ]


def test_result_severity_setters():
    result = composite().results.info()
    result.warning = True
    assert result.warning and not result.info
    result.warning = False
    assert result.info
    result.fatal = True
    assert result.fatal
    result.fatal = False
    assert result.info
    result.info = False
    assert not result.info
    assert not result.warning
    assert not result.fatal


@pytest.mark.parametrize(
    "claim,enum",
    [
        (False, fnv1.Target.TARGET_COMPOSITE),
        (None, fnv1.Target.TARGET_UNSPECIFIED),
        (protobuf.Unknown(), fnv1.Target.TARGET_UNSPECIFIED),
    ],
    ids=["false", "none", "unknown"],
)
def test_result_claim_setter(claim, enum):
    xr = composite()
    result = xr.results.warning(claim=claim)
    assert result.claim is False
    assert xr.response.results[0]._message.target == enum  #  ty: ignore[unresolved-attribute]


def test_result_missing():
    result = composite().results[5]
    assert not result
    assert not result.info
    assert not result.warning
    assert not result.fatal
    assert not result.claim
    assert result.reason is None
    assert result.message is None
    # Setters on a missing result are ignored.
    result.info = True
    result.warning = True
    result.fatal = True
    result.reason = "Reason"
    result.message = "Message"
    result.claim = True
    assert not result


# Connection secret and connection details


def test_connection_secret_v2():
    xr = composite(
        {"input": {"writeConnectionSecretToRef": {"name": "secret", "namespace": "ns"}}}
    )
    assert xr.connectionSecret.name == "secret"
    assert xr.connectionSecret.namespace == "ns"
    xr.connectionSecret = protobuf.Map(name="other")
    assert xr.connectionSecret.name == "other"
    assert not xr.connectionSecret.namespace


def test_connection_secret_set_dict():
    composite().connectionSecret = {"name": "other"}


def test_connection_set_dict():
    composite().connection = {"user": "admin"}


def test_connection_secret_v1():
    xr = composite(
        {
            "observed": {
                "composite": {
                    "resource": {
                        "spec": {"writeConnectionSecretToRef": {"name": "secret"}}
                    }
                }
            }
        },
        crossplane_v1=True,
    )
    assert xr.connectionSecret.name == "secret"
    xr.connectionSecret = xr.spec.writeConnectionSecretToRef
    with pytest.raises(NotImplementedError):
        xr.connectionSecret = {"name": "other"}


def test_connection_v1():
    xr = composite(crossplane_v1=True)
    assert len(xr.connection) == 0
    xr.connection.user = "admin"
    xr.connection["password"] = protobuf.Value(None, None, "secret")
    xr.connection.port = 5432  # ty: ignore[invalid-assignment]
    xr.connection.skipped = None  # ty: ignore[invalid-assignment]
    xr.connection.unknown = protobuf.Unknown()
    assert xr.connection
    assert len(xr.connection) == 3
    assert "user" in xr.connection
    assert xr.connection.user == "admin"
    assert sorted(key for key, value in xr.connection) == ["password", "port", "user"]
    assert "user:" in str(xr.connection)
    # Crossplane V1 does not create a connection secret resource.
    assert len(xr.resources) == 0
    xr.connection(reset="yes")
    assert len(xr.connection) == 1
    assert xr.connection.reset == "yes"


def test_connection_observed():
    xr = composite(
        {
            "observed": {
                "composite": {"connection_details": {"user": b"observed"}},
            }
        }
    )
    assert xr.connection.observed.user == "observed"


def test_connection_v2_secret():
    xr = composite(
        {"input": {"writeConnectionSecretToRef": {"name": "secret", "namespace": "ns"}}}
    )
    xr.connection = protobuf.Map(user="admin", password="pw")
    assert len(xr.connection) == 2
    secret = xr.resources["connection-secret"]
    assert secret.kind == "Secret"
    assert secret.metadata.name == "secret"
    assert not secret.metadata.namespace
    assert secret.type == "connection.crossplane.io/v1alpha1"
    assert secret.data.user == protobuf.B64Encode("admin")


def test_connection_v2_delete():
    xr = composite(
        {"input": {"writeConnectionSecretToRef": {"name": "secret", "namespace": "ns"}}}
    )
    xr.connection = protobuf.Map(user="admin", password="pw")
    secret = xr.resources["connection-secret"]
    del xr.connection.user
    assert "user" not in secret.data
    del xr.connection["password"]
    assert "connection-secret" not in xr.resources


def test_schema_format_jsonc():
    xr = composite({"required_schemas": {"xr": {"openapi_v3": {"type": "object"}}}})
    assert format(xr.schemas.xr, "jsonc") == '{"type":"object"}'


def test_connection_v2_resource_name():
    xr = composite(
        {
            "input": {
                "writeConnectionSecretToRef": {
                    "name": "secret",
                    "resourceName": "creds",
                }
            }
        }
    )
    xr.connection.user = "admin"
    assert "creds" in xr.resources
    xr.connection()
    assert "creds" not in xr.resources
    assert len(xr.connection) == 0


def test_connection_v2_cluster_scoped():
    cluster_xr = dict(XR, metadata={"name": "xr"})
    xr = composite(
        {
            "observed": {"composite": {"resource": cluster_xr}},
            "input": {
                "writeConnectionSecretToRef": {"name": "secret", "namespace": "ns"}
            },
        },
        xr=False,
    )
    xr.connection.user = "admin"
    assert xr.resources["connection-secret"].metadata.namespace == "ns"


def test_connection_v2_cluster_scoped_no_namespace():
    xr = composite(
        {
            "observed": {"composite": {"resource": dict(XR, metadata={"name": "xr"})}},
            "input": {"writeConnectionSecretToRef": {"name": "secret"}},
        },
        xr=False,
    )
    xr.connection.user = "admin"
    assert xr.results[0].fatal
    assert xr.results[0].reason == "ConnectionNoNamespace"


def test_connection_v2_no_secret():
    xr = composite()
    xr.connection.user = "admin"
    assert xr.connection.user == "admin"
    assert len(xr.resources) == 0


@pytest.mark.parametrize(
    "collection", ["resources", "credentials", "conditions", "connection"]
)
def test_empty_collections_falsy(collection):
    assert not getattr(composite(), collection)
