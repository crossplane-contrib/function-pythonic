import logging
import pathlib

import pytest

from crossplane.pythonic import (
    auto_ready,
    composite,
    protobuf,
)
from crossplane.pythonic.proto.v1 import run_function_pb2 as fnv1
from tests import utils

logger: logging.Logger = logging.getLogger(__name__)


tests = sorted(
    utils.yaml_load(
        (pathlib.Path(__file__).parent / "test_auto_ready.yaml").read_text()
    ).items()
)


@pytest.mark.parametrize("id,test", tests, ids=[test[0] for test in tests])
def test(id, test):
    resource: dict = test["resource"]
    if "metadata" not in resource:
        resource["metadata"] = {}
    resource["metadata"]["name"] = id
    request = fnv1.RunFunctionRequest(
        observed=fnv1.State(
            resources=utils.mapping(
                test=fnv1.Resource(resource=utils.struct(**resource))
            ),
        ),
        desired=fnv1.State(
            resources=utils.mapping(
                test=fnv1.Resource(
                    resource=utils.struct(
                        apiVersion=resource["apiVersion"], kind=resource["kind"]
                    ),
                )
            )
        ),
    )
    composite_test = composite.BaseComposite(False, request, logger)
    ready: protobuf.Value | bool | None = composite_test.resources.test.ready
    if ready is None:
        message = "Ready is not set"
    else:
        if isinstance(ready, protobuf.Value):
            message = f"Ready is {ready._fullName()}"
            ready = bool(ready)
        else:
            message = f'Ready is "{ready}"'
    assert test["ready"] == ready, message


def test_abstract():
    composite_test = composite.BaseComposite(False, fnv1.RunFunctionRequest(), logger)
    with pytest.raises(NotImplementedError):
        auto_ready.Check().ready(composite_test.resources.test)
