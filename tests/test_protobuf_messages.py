import grpc_tools.protoc
import pytest

from crossplane.pythonic import protobuf


@pytest.fixture(scope="module", autouse=True)
def Message():
    status = grpc_tools.protoc.main(
        [
            "grpc_tools.protoc",
            f"--proto_path={grpc_tools.protoc._get_resource_file_name('grpc_tools', '_proto')}",
            "--proto_path=.",
            "--python_out=.",
            "--pyi_out=.",
            "--grpc_python_out=.",
            "tests/protobuf/pytest.proto",
        ]
    )
    assert status == 0
    import tests.protobuf.pytest_pb2

    return tests.protobuf.pytest_pb2.Message


def test_message(Message):
    message = Message()
    m = protobuf.Message(None, "pytest", message.DESCRIPTOR, message)
    assert m
    assert len(m)
    assert (
        str(m)
        == """\
list: []
list_map: []
list_string: []
map_list: {}
map_map: {}
map_string: {}
string: ''
struct: {}
"""
    )
    m.string = "pytest"
    assert m["string"] == "pytest"
    m.struct.a = "pytest"
    assert m["struct"]["a"] == "pytest"
    m.list[0] = "a"
    m.map_string.a = "b"
    m.map_map.a.b = "c"
    m.map_list.a[0] = "b"
    m.list_string[0] = "a"
    m.list_map[0].c = "d"
    assert m == m  # noqa: PLR0124
    assert hash(m) == hash(m)
    assert m.map_string
    assert "a" in m.map_string
    assert "b" not in m.map_string
    assert (
        str(m.map_string)
        == """\
a: b
"""
    )
    assert m.list_string
    assert (
        str(m.list_string)
        == """\
- a
"""
    )
    assert "a" in m.list_string
    assert "b" not in m.list_string
    assert (
        str(m)
        == """\
list:
- a
list_map:
- c: d
list_string:
- a
map_list:
  a:
  - b
map_map:
  a:
    b: c
map_string:
  a: b
string: pytest
struct:
  a: pytest
"""
    )
    assert str(m) == format(m)
    assert format(m, "yaml") == str(m)
    assert format(m, "json")
    assert format(m, "jsonc")
    assert format(m, "protobuf")
    assert format(m.map_string, "protobuf")
    assert format(m.list_string, "protobuf")
    assert format(m.struct, "protobuf")
    assert format(m.list, "protobuf")
    del m.string
    del m.struct.a
    del m.list[0]
    assert (
        str(m)
        == """\
list: []
list_map:
- c: d
list_string:
- a
map_list:
  a:
  - b
map_map:
  a:
    b: c
map_string:
  a: b
string: ''
struct: {}
"""
    )
    m(string="called")
    assert (
        str(m)
        == """\
list: []
list_map: []
list_string: []
map_list: {}
map_map: {}
map_string: {}
string: called
struct: {}
"""
    )
    m.list_string("a")
    del m.list_string[0]


def test_exceptions(Message):
    message = Message()
    m = protobuf.Message(None, "pytest", message.DESCRIPTOR, message)
    with pytest.raises(AttributeError):
        m.nope  # noqa: B018
    with pytest.raises(AttributeError):
        m.nope = "string"
    with pytest.raises(AttributeError):
        delattr(m, "nope")
    ro = protobuf.Message(None, "pytest", message.DESCRIPTOR, message, "Read Only Test")
    assert ro.string == ""
    with pytest.raises(ValueError):
        ro.string = "nope"
    with pytest.raises(ValueError):
        ro.struct.string = "nope"
    with pytest.raises(ValueError):
        ro(string="nope")
    with pytest.raises(ValueError):
        ro.struct(string="nope")
    with pytest.raises(ValueError):
        delattr(ro, "string")
    with pytest.raises(ValueError):
        ro.map_map.nope = "string"
    with pytest.raises(ValueError):
        ro.map_map(nope="string")
    with pytest.raises(ValueError):
        delattr(ro.map_map, "nope")
    with pytest.raises(ValueError):
        ro.list_string("a")
    with pytest.raises(ValueError):
        del ro.list_string[0]
