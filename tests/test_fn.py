
import pathlib
import pytest
from crossplane.function.proto.v1 import run_function_pb2 as fnv1
from google.protobuf import json_format

from crossplane.pythonic import function
from tests import utils


fn_cases = sorted([
    path
    for path in (pathlib.Path(__file__).parent / 'fn_cases').iterdir()
    if path.is_file() and path.suffix == '.yaml'
])

@pytest.mark.parametrize('fn_case', fn_cases, ids=[path.stem for path in fn_cases])
@pytest.mark.asyncio
async def test_run_function(fn_case):
    test = utils.yaml_load(fn_case.read_text())

    request = fnv1.RunFunctionRequest(
        observed=fnv1.State(
            composite=fnv1.Resource(
                resource={
                    'apiVersion': 'pythonic.crossplane.io/v1alpha1',
                    'kind': 'PyTest',
                    'metadata': {
                        'name': fn_case.stem,
                    },
                },
            ),
        ),
    )
    utils.message_merge(request, test['request'])

    response = {
        'meta': {
            'ttl': {
                'seconds': 60,
            },
        },
        'context': {
            '_pythonic': {
                'pytest': {
                    'iteration': 1,
                },
            },
            'iteration': 1,
        },
        'desired': {},
        'conditions': [
            {
                'type': 'ResourcesComposed',
                'status': 2,
                'reason': 'AllComposed',
                'message': 'All resources are composed',
            }
        ],
    }
    utils.map_merge(response, test.get('response', {}))

    result = utils.message_dict(
        await function.FunctionRunner(True).RunFunction(request, None)
    )

    assert result == response
