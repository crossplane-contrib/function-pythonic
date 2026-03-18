import base64
import importlib
import logging
import sys
import types
from types import SimpleNamespace

import pytest


class DummyRunner:
    def __init__(self):
        self.invalidated = []

    def invalidate_module(self, name):
        self.invalidated.append(name)


def resource(plural):
    return SimpleNamespace(plural=plural)


class FakeKopfOn:
    def __init__(self):
        self.registrations = {
            'cleanup': [],
            'create': [],
            'delete': [],
            'resume': [],
            'startup': [],
            'update': [],
        }

    def _register(self, event, *args, **kwargs):
        def decorator(fn):
            self.registrations[event].append((args, kwargs, fn))
            return fn

        return decorator

    def cleanup(self, *args, **kwargs):
        return self._register('cleanup', *args, **kwargs)

    def create(self, *args, **kwargs):
        return self._register('create', *args, **kwargs)

    def delete(self, *args, **kwargs):
        return self._register('delete', *args, **kwargs)

    def resume(self, *args, **kwargs):
        return self._register('resume', *args, **kwargs)

    def startup(self, *args, **kwargs):
        return self._register('startup', *args, **kwargs)

    def update(self, *args, **kwargs):
        return self._register('update', *args, **kwargs)


class FakeKopf(types.ModuleType):
    def __init__(self):
        super().__init__('kopf')
        self.PRESENT = object()
        self.on = FakeKopfOn()
        self.operator_calls = []

    def operator(self, *args, **kwargs):
        self.operator_calls.append((args, kwargs))
        return {'args': args, 'kwargs': kwargs}


@pytest.fixture
def packages_module(monkeypatch, tmp_path):
    fake_kopf = FakeKopf()
    monkeypatch.setitem(sys.modules, 'kopf', fake_kopf)
    sys.modules.pop('crossplane.pythonic.packages', None)
    packages = importlib.import_module('crossplane.pythonic.packages')

    monkeypatch.setattr(packages, 'PACKAGES_DIR', tmp_path.resolve())
    monkeypatch.setattr(packages, 'GRPC_RUNNER', DummyRunner())
    monkeypatch.setattr(packages, 'GRPC_SERVER', None)
    monkeypatch.setattr(sys, 'path', sys.path.copy())

    yield packages, fake_kopf

    sys.modules.pop('crossplane.pythonic.packages', None)


def test_operator_registers_resources_and_sets_global_state(
    packages_module,
    tmp_path,
    monkeypatch,
):
    packages, fake_kopf = packages_module
    on_resource_calls = []
    server = object()
    runner = DummyRunner()

    monkeypatch.setattr(
        packages,
        'on_resource',
        lambda *args: on_resource_calls.append(args),
    )

    result = packages.operator(
        server,
        runner,
        True,
        True,
        None,
        True,
        True,
        str(tmp_path),
    )

    assert packages.GRPC_SERVER is server
    assert packages.GRPC_RUNNER is runner
    assert packages.PACKAGES_DIR == tmp_path.resolve()
    assert sys.path[0] == str(tmp_path.resolve())
    assert on_resource_calls == [
        ('', 'v1', 'configmaps'),
        ('', 'v1', 'secrets'),
        ('apiextensions.crossplane.io', 'v1beta1', 'environmentconfigs'),
        ('apiextensions.crossplane.io', 'v1', 'compositions'),
    ]
    assert fake_kopf.operator_calls == [
        (
            (),
            {
                'standalone': True,
                'clusterwide': True,
                'namespaces': None,
            },
        )
    ]
    assert result['kwargs']['clusterwide'] is True


def test_operator_uses_namespaces_and_skips_cluster_resources(
    packages_module,
    tmp_path,
    monkeypatch,
):
    packages, fake_kopf = packages_module
    on_resource_calls = []

    monkeypatch.setattr(
        packages,
        'on_resource',
        lambda *args: on_resource_calls.append(args),
    )

    packages.operator(
        object(),
        DummyRunner(),
        True,
        False,
        ['team-a'],
        True,
        True,
        str(tmp_path),
    )

    assert on_resource_calls == [('', 'v1', 'configmaps')]
    assert fake_kopf.operator_calls == [
        (
            (),
            {
                'standalone': True,
                'clusterwide': False,
                'namespaces': ['team-a'],
            },
        )
    ]


def test_on_resource_registers_handlers(packages_module):
    packages, fake_kopf = packages_module

    packages.on_resource('group.example.io', 'v1alpha1', 'widgets')

    for event, handler in (
        ('create', packages.create),
        ('resume', packages.create),
        ('update', packages.update),
        ('delete', packages.delete),
    ):
        args, kwargs, fn = fake_kopf.on.registrations[event][-1]
        assert args == ('group.example.io', 'v1alpha1', 'widgets')
        assert kwargs == {'labels': packages.PACKAGE_LABELS}
        assert fn is handler


@pytest.mark.asyncio
async def test_startup_and_cleanup(packages_module, monkeypatch):
    packages, _ = packages_module
    settings = SimpleNamespace(scanning=SimpleNamespace(disabled=False))
    server = SimpleNamespace(stop=None, stop_calls=[])

    async def stop(grace):
        server.stop_calls.append(grace)

    monkeypatch.setattr(server, 'stop', stop)
    monkeypatch.setattr(packages, 'GRPC_SERVER', server)

    await packages.startup(settings)
    await packages.cleanup()

    assert settings.scanning.disabled is True
    assert server.stop_calls == [5]


@pytest.mark.parametrize(
    ('name', 'value', 'expected'),
    [
        ('module.py', 'print(1)\n', True),
        ('data', 'payload', True),
        ('package', {}, True),
        ('bad-name.py', 'print(1)\n', False),
        ('bad.name', 'payload', False),
        ('bad/name', 'payload', False),
        ('package', 1, False),
    ],
)
def test_validate_entry(packages_module, caplog, name, value, expected):
    packages, _ = packages_module
    logger = logging.getLogger(__name__)

    with caplog.at_level(logging.ERROR):
        assert packages.validate_entry(name, value, logger) is expected

    if expected:
        assert not caplog.messages
    else:
        assert caplog.messages


def test_resource_package_dir_uses_label_for_configmaps_and_secrets(
    packages_module,
    tmp_path,
):
    packages, _ = packages_module
    logger = logging.getLogger(__name__)
    labels = {
        'function-pythonic.package': 'pkg.subpackage',
    }

    package_dir = packages.resource_package_dir(
        resource('configmaps'),
        labels,
        logger,
    )

    assert package_dir == tmp_path / 'pkg' / 'subpackage'


def test_resource_package_dir_validates_labels(packages_module, caplog, tmp_path):
    packages, _ = packages_module
    logger = logging.getLogger(__name__)

    with caplog.at_level(logging.ERROR):
        assert packages.resource_package_dir(resource('configmaps'), {}, logger) is None
        assert (
            packages.resource_package_dir(
                resource('secrets'),
                {
                    'function-pythonic.package': 'not-valid.segment',
                },
                logger,
            )
            is None
        )

    assert caplog.messages == [
        'function-pythonic.package label is missing',
        'Package has invalid package name: not-valid.segment',
    ]
    assert packages.resource_package_dir(
        resource('compositions'),
        {
            'function-pythonic.package': 'ignored.for.compositions',
        },
        logger,
    ) == tmp_path


def test_package_file_name_maps_python_modules(packages_module, tmp_path):
    packages, _ = packages_module

    assert packages.package_file_name(tmp_path / 'pkg' / 'mod.py') == (
        True,
        'pkg.mod',
    )
    assert packages.package_file_name(tmp_path / 'pkg' / 'data.txt') == (
        False,
        'pkg/data.txt',
    )


def test_package_create_writes_files_and_invalidates_modules(
    packages_module,
    tmp_path,
):
    packages, _ = packages_module
    logger = logging.getLogger(__name__)
    runner = DummyRunner()

    packages.GRPC_RUNNER = runner

    packages.package_create(
        resource('configmaps'),
        'Created',
        tmp_path,
        {
            'pkg': {
                '__init__.py': '',
                'module.py': 'value = 1\n',
                'data': 'payload',
            },
            'bad-name.py': 'ignore me',
        },
        logger,
    )

    assert (tmp_path / 'pkg' / '__init__.py').read_text() == ''
    assert (tmp_path / 'pkg' / 'module.py').read_text() == 'value = 1\n'
    assert (tmp_path / 'pkg' / 'data').read_text() == 'payload'
    assert not (tmp_path / 'bad-name.py').exists()
    assert runner.invalidated == ['pkg.__init__', 'pkg.module']


def test_package_create_decodes_secrets(packages_module, tmp_path):
    packages, _ = packages_module
    logger = logging.getLogger(__name__)
    runner = DummyRunner()

    packages.GRPC_RUNNER = runner

    packages.package_create(
        resource('secrets'),
        'Created',
        tmp_path,
        {
            'secret_module.py': base64.b64encode(b'print("secret")\n').decode(
                'utf-8'
            ),
        },
        logger,
    )

    assert (tmp_path / 'secret_module.py').read_bytes() == b'print("secret")\n'
    assert runner.invalidated == ['secret_module']


def test_package_delete_removes_files_and_empty_directories(
    packages_module,
    tmp_path,
):
    packages, _ = packages_module
    logger = logging.getLogger(__name__)
    runner = DummyRunner()

    packages.GRPC_RUNNER = runner
    package_dir = tmp_path / 'pkg' / 'sub'
    package_dir.mkdir(parents=True)
    (package_dir / 'module.py').write_text('value = 1\n')
    (package_dir / 'data').write_text('payload')

    packages.package_delete(
        'Deleted',
        tmp_path,
        {
            'pkg': {
                'sub': {
                    'module.py': 'value = 1\n',
                    'data': 'payload',
                },
            },
        },
        logger,
    )

    assert not (package_dir / 'module.py').exists()
    assert not (package_dir / 'data').exists()
    assert not package_dir.exists()
    assert not (tmp_path / 'pkg').exists()
    assert runner.invalidated == ['pkg.sub.module', 'pkg.sub', 'pkg']


@pytest.mark.asyncio
async def test_create_and_delete_handle_composition_pipeline(
    packages_module,
    tmp_path,
    monkeypatch,
):
    packages, _ = packages_module
    create_calls = []
    delete_calls = []
    logger = logging.getLogger(__name__)
    composition_resource = resource('compositions')
    labels = {'function-pythonic.package': 'pkg'}
    body = {
        'kind': 'Composition',
        'spec': {
            'pipeline': [
                {
                    'input': {
                        'apiVersion': 'pythonic.fn.crossplane.io/v1alpha1',
                        'packages': {
                            'module.py': 'value = 1\n',
                        },
                    },
                },
                {
                    'input': {
                        'apiVersion': 'other.example.io/v1alpha1',
                        'packages': {
                            'ignored.py': 'value = 2\n',
                        },
                    },
                },
            ],
        },
    }

    monkeypatch.setattr(
        packages,
        'resource_package_dir',
        lambda resource, labels, logger: tmp_path,
    )
    monkeypatch.setattr(
        packages,
        'package_create',
        lambda *args: create_calls.append(args),
    )
    monkeypatch.setattr(
        packages,
        'package_delete',
        lambda *args: delete_calls.append(args),
    )

    await packages.create(composition_resource, labels, body, logger)
    await packages.delete(composition_resource, labels, body, logger)

    assert create_calls == [
        (
            composition_resource,
            'Created',
            tmp_path,
            {'module.py': 'value = 1\n'},
            logger,
        ),
    ]
    assert delete_calls == [
        ('Deleted', tmp_path, {'module.py': 'value = 1\n'}, logger),
    ]


@pytest.mark.asyncio
async def test_update_deletes_old_before_creating_new(packages_module, monkeypatch):
    packages, _ = packages_module
    calls = []
    logger = logging.getLogger(__name__)
    configmaps_resource = resource('configmaps')
    labels = {'function-pythonic.package': 'pkg'}
    body = {'kind': 'ConfigMap'}
    old = {'kind': 'ConfigMap'}

    def resource_delete(resource, labels, action, value, logger):
        calls.append(('delete', resource, labels, value, action, logger))

    def resource_create(resource, labels, action, value, logger):
        calls.append(('create', resource, labels, value, action, logger))

    monkeypatch.setattr(packages, 'resource_delete', resource_delete)
    monkeypatch.setattr(packages, 'resource_create', resource_create)

    await packages.update(
        resource=configmaps_resource,
        labels=labels,
        body=body,
        old=old,
        logger=logger,
    )

    assert calls == [
        ('delete', configmaps_resource, labels, old, 'Removed', logger),
        ('create', configmaps_resource, labels, body, 'Added', logger),
    ]
