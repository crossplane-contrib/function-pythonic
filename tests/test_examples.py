
import os
import pathlib
import pytest
import sys
import yaml

from crossplane.pythonic import protobuf, render


def find_xrs(directory, names=[]):
    xr = directory / 'xr.yaml'
    if xr.is_file():
        xrs.append(['/'.join(names), xr])
    for entry in directory.iterdir():
        if entry.is_dir():
            find_xrs(entry, names + [entry.name])
xrs = []
find_xrs(pathlib.Path(__file__).parent.parent / 'examples')
xrs.sort()

generate_expected = os.getenv('PYTEST_GENERATE_EXPECTED', '').lower() == 'true'
expecteds = pathlib.Path(__file__).parent / 'examples'


@pytest.mark.parametrize('id,xr', xrs, ids=[id for id,xr in xrs])
@pytest.mark.asyncio
async def test(id, xr):
    composite = protobuf.Yaml(xr.read_text())
    directory = xr.parent
    observed = directory / 'observed.yaml'
    if observed.is_file():
        observed = protobuf.YamlAll(observed.read_text())
    else:
        observed = []
    composition = directory / 'composition.yaml'
    if composition.is_file():
        composition = protobuf.Yaml(composition.read_text())
    else:
        composition = None
    resources = directory / 'resources.yaml'
    if resources.is_file():
        resources = protobuf.YamlAll(resources.read_text())
    else:
        resources = []
    expected = (expecteds / id).with_suffix('.yaml')
    if not generate_expected:
        assert expected.is_file()
        expected_str = expected.read_text()
        expected_yaml = yaml.safe_load(expected_str)
    len_sys_path = len(sys.path)
    try:
        python_path = expected.with_suffix('.python-path')
        if python_path.is_file():
            for line in python_path.read_text().split():
                if line and line[0] != '#':
                    sys.path.append(str((directory / line).absolute()))
        response = await render.Command().render(composite, observed, composition, resources, render_unknowns=True)
    finally:
        if len(sys.path) > len_sys_path:
            del sys.path[len_sys_path:]

    assert response
    response_str = str(response)
    response_yaml = yaml.safe_load(response_str)
    if generate_expected:
        expected.parent.mkdir(parents=True, exist_ok=True)
        expected.write_text(response_str)
    else:
        assert response_yaml == expected_yaml
