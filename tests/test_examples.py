import argparse
import json
import logging
import os
import pathlib
import shlex
import sys
import typing

import pytest
import yaml

from crossplane.pythonic import protobuf, render


def find_xrs(directory, names=None):
    if names is None:
        names = []
    xr = directory / "xr.yaml"
    if xr.is_file():
        xrs.append(["/".join(names), xr])
    for entry in directory.iterdir():
        if entry.is_dir():
            find_xrs(entry, names + [entry.name])


xrs = []
find_xrs(pathlib.Path(__file__).parent.parent / "examples")
xrs.sort()

generate_expected = os.getenv("PYTEST_GENERATE_EXPECTED", "").lower() == "true"
expecteds = pathlib.Path(__file__).parent / "examples"


@pytest.mark.parametrize("id,xr", xrs, ids=[id for id, xr in xrs])
@pytest.mark.asyncio
async def test(id, xr):
    composite = typing.cast(protobuf.Value, protobuf.Yaml(xr.read_text()))
    directory = xr.parent
    observed = directory / "observed.yaml"
    if observed.is_file():
        observed: list[protobuf.Value] = [
            resource
            for resource in typing.cast(
                protobuf.Value, protobuf.YamlAll(observed.read_text())
            )
        ]
    else:
        observed = None
    composition = directory / "composition.yaml"
    if composition.is_file():
        composition = typing.cast(
            protobuf.Value, protobuf.Yaml(composition.read_text())
        )
    else:
        composition = None
    resources = directory / "resources.yaml"
    if resources.is_file():
        resources: list[protobuf.Value] = [
            resource
            for resource in typing.cast(
                protobuf.Value, protobuf.YamlAll(resources.read_text())
            )
        ]
    else:
        resources: None = None
    expected = (expecteds / id).with_suffix(".yaml")
    if not generate_expected:
        assert expected.is_file()
        expected_str = expected.read_text()
        expected_yaml = yaml.safe_load(expected_str)
    len_sys_path = len(sys.path)
    try:
        python_path = expected.with_suffix(".python-path")
        if python_path.is_file():
            for line in python_path.read_text().split():
                if line and line[0] != "#":
                    sys.path.append(str((directory / line).absolute()))
        response = await render.Command().render(
            composite, observed, composition, resources, render_unknowns=True
        )
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


# Exercise the render command line, using the commands in the examples' render scripts.

examples = pathlib.Path(__file__).parent.parent / "examples"
expecteds_cli = pathlib.Path(__file__).parent / "examples-cli"


def render_script_args(script):
    script = script.read_text().replace("\\\n", " ")
    for line in script.splitlines():
        line = line.strip()
        if line.startswith("#"):
            continue
        words = shlex.split(line)
        if words and words[0] == "exec":
            words = words[1:]
        if words[:2] == ["function-pythonic", "render"]:
            return words[2:]
    return None


scripts: list[tuple[str, pathlib.Path]] = sorted(
    (
        str(script.parent.relative_to(examples) / script.stem),
        script,
    )
    for script in examples.glob("**/render*.sh")
    if render_script_args(script) is not None
)


@pytest.fixture
def cli(monkeypatch, capsys):
    """Run the render command line, returning the rendered YAML documents."""
    root = logging.getLogger()
    handlers, level = root.handlers, root.level
    sys_path = list(sys.path)

    async def run(*args, cwd=None):
        if cwd:
            monkeypatch.chdir(cwd)
        parser = argparse.ArgumentParser()
        render.Command.create(parser.add_subparsers())
        parsed = parser.parse_args(["render", *args])
        await parsed.command(parsed).run()
        # Logging also goes to stdout, all of it before the first document.
        out = capsys.readouterr().out
        return out[out.find("---\n") :]

    yield run
    root.handlers, root.level = handlers, level
    sys.path[:] = sys_path


@pytest.mark.parametrize("id,script", scripts, ids=[id for id, script in scripts])
@pytest.mark.asyncio
async def test_render_script(id, script, cli):
    output = await cli(*render_script_args(script), cwd=script.parent)
    expected = (expecteds_cli / id).with_suffix(".yaml")
    if generate_expected:
        expected.parent.mkdir(parents=True, exist_ok=True)
        expected.write_text(output)
    else:
        assert expected.is_file()
        assert list(yaml.safe_load_all(output)) == list(
            yaml.safe_load_all(expected.read_text())
        )


COMPOSITE = """\
apiVersion: example.crossplane.io/v1
kind: XR
metadata:
  name: cli
  namespace: default
spec:
  value: hello
"""

COMPOSER = """\
from crossplane.pythonic import BaseComposite

class Composer(BaseComposite):
    def compose(self):
        self.status.value = self.spec.value
        self.status.context = self.context.cli
        cm = self.resources.cm('ConfigMap', 'v1')
        cm.data.value = self.spec.value
        self.results.info('Composed', 'Composed the ConfigMap')
"""

NOT_COMPOSER = """\
NotAClass = 'nope'

class NotComposite:
    pass
"""


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    (tmp_path / "xr.yaml").write_text(COMPOSITE)
    (tmp_path / "composer.py").write_text(COMPOSER)
    (tmp_path / "not_composer.py").write_text(NOT_COMPOSER)
    monkeypatch.chdir(tmp_path)
    yield tmp_path
    for module in ("composer", "not_composer"):
        sys.modules.pop(module, None)


@pytest.mark.asyncio
async def test_render_python_file_composition(workdir, cli):
    (workdir / "context.yaml").write_text("from: file\n")
    (workdir / "required").mkdir()
    (workdir / "required" / "extra.yaml").write_text(
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: extra\ndata:\n  value: required\n"
    )
    (workdir / "required" / "ignored.txt").write_text("not yaml")
    output = await cli(
        "--context-files=cli=context.yaml",
        "--context-values=other={from: value}",
        "--required-resources=required",
        "--include-full-xr",
        "--include-connection-xr",
        "--include-function-results",
        "--include-context",
        "xr.yaml",
        "composer.py",
    )
    documents = list(yaml.safe_load_all(output))
    composite = documents[0]
    assert composite["spec"] == {"value": "hello"}
    assert composite["status"]["value"] == "hello"
    assert composite["status"]["context"] == {"from": "file"}
    kinds = [document["kind"] for document in documents]
    assert kinds == ["XR", "Connection", "ConfigMap", "Result", "Context"]
    assert documents[2]["data"] == {"value": "hello"}
    assert documents[4]["values"]["other"] == {"from": "value"}


@pytest.mark.asyncio
async def test_render_class_composition(workdir, cli):
    output = await cli("--python-path=.", "xr.yaml", "composer.Composer")
    documents = list(yaml.safe_load_all(output))
    assert documents[0]["metadata"] == {"name": "cli", "namespace": "default"}
    assert documents[0]["status"]["value"] == "hello"
    assert documents[1]["data"] == {"value": "hello"}


def test_render_required_schemas(workdir):
    schema = {"openAPIV3Schema": {"type": "object"}}
    (workdir / "schema.json").write_text(json.dumps(schema))
    (workdir / "schemas").mkdir()
    (workdir / "schemas" / "other.json").write_text(json.dumps(schema))
    (workdir / "schemas" / "ignored.yaml").write_text("{}")
    command = render.Command(argparse.Namespace())
    schemas = command.collect_schemas([workdir / "schema.json", workdir / "schemas"])
    assert len(schemas) == 2


@pytest.mark.parametrize(
    "args,error",
    [
        (["missing.yaml"], 'Composite "missing.yaml" is not a file'),
        (["xr.yaml", "composer"], "Composition class name does not include module"),
        (["xr.yaml", "no_such_module.Composer"], "Unable to import composition module"),
        (["xr.yaml", "composer.Missing"], "does not define: Missing"),
        (["xr.yaml", "not_composer.NotAClass"], "is not a class"),
        (
            ["xr.yaml", "not_composer.NotComposite"],
            "is not a subclass of BaseComposite",
        ),
        (["xr.yaml", "empty.yaml"], "does not contain any pipeline steps"),
        (["--observed-resources=missing", "xr.yaml"], "is not a file or a directory"),
        (
            ["--required-schemas=missing", "xr.yaml", "composer.py"],
            "is not a file or a directory",
        ),
        (
            ["--context-files=nokey", "xr.yaml", "composer.py"],
            "Invalid --context-files: nokey",
        ),
        (
            ["--context-files=key=missing.yaml", "xr.yaml", "composer.py"],
            "is not a file",
        ),
        (
            ["--context-values=nokey", "xr.yaml", "composer.py"],
            "Invalid --context-values: nokey",
        ),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
@pytest.mark.asyncio
async def test_render_errors(workdir, cli, capsys, args, error):
    (workdir / "empty.yaml").write_text(
        "apiVersion: apiextensions.crossplane.io/v1\nkind: Composition\nspec:\n  pipeline: []\n"
    )
    with pytest.raises(SystemExit) as exit:
        await cli("--python-path=.", *args)
    assert exit.value.code == 1
    assert error in capsys.readouterr().err
