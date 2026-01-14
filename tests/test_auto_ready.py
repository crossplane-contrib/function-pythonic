
import logging
import pathlib
import pytest
from crossplane.function.proto.v1 import run_function_pb2 as fnv1

from crossplane.pythonic import (
    auto_ready,
    composite,
)
from tests import utils

logger = logging.getLogger(__name__)


tests = sorted(utils.yaml_load((pathlib.Path(__file__).parent / 'test_auto_ready.yaml').read_text()).items())
@pytest.mark.parametrize('id,test', tests, ids=[test[0] for test in tests])
def test(id, test):
    resource = test['resource']
    request = fnv1.RunFunctionRequest(
        observed=fnv1.State(
            resources={
                id: fnv1.Resource(
                    resource=resource,
                ),
            },
        ),
        desired=fnv1.State(
            resources={
                id: fnv1.Resource(
                    resource={
                        'apiVersion': resource['apiVersion'],
                        'kind': resource['kind'],
                    },
                ),
            },
        ),
    )
    composite_test = composite.BaseComposite(False, request, False, logger)
    auto_ready.process(composite_test)
    assert test['ready'] == composite_test.resources[id].ready


def test_abstract():
    with pytest.raises(NotImplementedError):
        auto_ready.Check().ready(None)
