import grpc_tools.protoc
import pytest
import yaml

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


@pytest.fixture
def Scalars(Message):
    import tests.protobuf.pytest_pb2

    return tests.protobuf.pytest_pb2.Scalars


def wrap(message_type, readOnly=False):
    return protobuf.Message(
        None, "pytest", message_type.DESCRIPTOR, message_type(), readOnly
    )


def test_scalar_fields(Scalars):
    s = wrap(Scalars)
    s.bytes = "abc"
    s.int = 5
    s.float = 1.5
    assert s.bytes == b"abc"
    assert s.bytes == "abc"
    assert s.bytes == s.bytes
    assert bytes(s.bytes) == b"abc"
    assert str(s.bytes) == "abc"
    assert len(s.bytes) == 3
    assert b"b" in s.bytes
    assert hash(s.bytes) == hash(b"abc")
    assert int(s.int) == 5
    assert float(s.int) == 5.0
    assert format(s.int, "03d") == "005"
    assert str(s.int) == "5"
    assert float(s.float) == 1.5
    s.message.string = "abc"
    assert s.message.string == s.bytes
    assert s.bytes == s.message.string
    assert bytes(s.message.string) == b"abc"
    output = str(s)
    assert "bytes: !!binary |\n  YWJj\n" in output
    assert "\nfloat: 1.5\n" in output
    assert "\nint: 5\n" in output
    del s.int
    assert s.int == 0


def test_bool_field_yaml(Scalars):
    s = wrap(Scalars)
    s.bool = True
    assert "\nbool: true\n" in f"\n{s}\n"


def test_bool_field_to_value(Scalars):
    s = wrap(Scalars)
    s.bool = True
    values = protobuf.Map(bool=s.bool)
    assert str(values.bool) == "true"


def test_number_value_to_int_field(Scalars):
    s = wrap(Scalars)
    s.int = protobuf.Map(v=2).v
    assert s.int == 2


def test_bytes_field_json(Scalars):
    s = wrap(Scalars)
    s.map_bytes.a = "abc"
    assert format(s.map_bytes, "jsonc") == '{"a":"abc"}'


def test_fields_to_value(Scalars):
    s = wrap(Scalars)
    s.bytes = "abc"
    s.int = 5
    s.float = 1.5
    values = protobuf.Map(bytes=s.bytes, int=s.int, float=s.float)
    assert values == {"bytes": "abc", "int": 5, "float": 1.5}
    assert values._getDependencies == {
        "bytes": "pytest.bytes",
        "int": "pytest.int",
        "float": "pytest.float",
    }


def test_unknown_message(Scalars):
    u = protobuf.Message(None, "pytest", Scalars.DESCRIPTOR)
    assert not u
    assert hash(u) == 0
    assert u == protobuf.Message(None, "other", Scalars.DESCRIPTOR)
    assert u != wrap(Scalars)
    assert wrap(Scalars) != u
    assert u != wrap(Scalars).message
    assert u != "pytest"
    assert format(u, "jsonc") == "null"
    assert format(u.messages, "jsonc") == "null"
    assert format(u.map_bytes, "jsonc") == "null"
    assert yaml.safe_load(str(u))["int"] == "<<UNKNOWN>>"
    with pytest.raises(ValueError):
        u.int = 1
    field = u.int
    assert not field
    assert len(field) == 0
    assert 1 not in field
    assert hash(field) == 0
    assert field != 0
    assert not u.messages
    assert len(u.messages) == 0
    assert hash(u.messages) == 0
    assert 1 not in u.messages
    assert list(u.messages) == []
    assert u.messages[-1]._key == 0
    assert u.messages[protobuf.append]._key == 0
    assert not u.map_bytes
    assert len(u.map_bytes) == 0
    assert "a" not in u.map_bytes
    assert list(u.map_bytes) == []
    del u.int
    del u.map_bytes.a
    del u.messages[0]


def test_unknown_map_hash(Scalars):
    u = protobuf.Message(None, "pytest", Scalars.DESCRIPTOR)
    assert hash(u.map_bytes) == 0


def test_field_protobuf_base(Scalars):
    field = wrap(Scalars).int
    with pytest.raises(AttributeError):
        field.nope  # noqa: B018
    with pytest.raises(ValueError):
        field["nope"]
    with pytest.raises(ValueError):
        iter(field)
    with pytest.raises(ValueError):
        field()
    with pytest.raises(ValueError):
        field["nope"] = 1
    with pytest.raises(ValueError):
        del field.nope
    with pytest.raises(ValueError):
        del field["nope"]
    with pytest.raises(ValueError):
        field.append(1)
    field.extra = 1
    assert field.extra == 1
    with pytest.raises(ValueError):
        int(wrap(Scalars))
    with pytest.raises(ValueError):
        float(wrap(Scalars))


def test_message_keys(Scalars):
    s = wrap(Scalars)
    key = protobuf.Map(field="int", key="a", index=0)
    s[key.field] = 1
    assert s[key.field] == 1
    s.map_bytes[key.key] = "x"
    assert s.map_bytes[key.key] == "x"
    assert key.key in s.map_bytes
    s.list_int.append(1)
    with pytest.raises(TypeError):
        s[1]
    with pytest.raises(TypeError):
        s.map_bytes[1]
    with pytest.raises(TypeError):
        s.list_int["a"]
    s.int = s.int
    assert s.int == 1


def test_message_equality(Scalars):
    a = wrap(Scalars)
    b = wrap(Scalars)
    a.int = 1
    assert a != b
    b.int = 1
    assert a == b
    a.map_bytes.x = "1"
    b.map_bytes.x = "2"
    assert a.map_bytes != b.map_bytes
    b.map_bytes.y = "2"
    assert a.map_bytes != b.map_bytes
    assert a.map_bytes != a.map_message
    assert a.map_bytes != a.list_bytes
    assert a.map_message != a.message.map_map
    assert a.map_bytes != protobuf.Message(None, "u", Scalars.DESCRIPTOR).map_bytes
    assert protobuf.Message(None, "u", Scalars.DESCRIPTOR).map_bytes != a.map_bytes
    a.list_int(1, 2)
    b.list_int(1, 3)
    assert a.list_int != b.list_int
    b.list_int(1)
    assert a.list_int != b.list_int
    assert a.list_int != a.list_bytes
    assert a.list_int != a.map_bytes
    assert a.messages != a.message.list_map
    assert a.list_int != protobuf.Message(None, "u", Scalars.DESCRIPTOR).list_int
    assert protobuf.Message(None, "u", Scalars.DESCRIPTOR).list_int != a.list_int
    assert hash(a.list_int) == hash(a.list_int)
    assert 2 in a.list_int


def test_map_messages(Scalars):
    s = wrap(Scalars)
    s.map_message.a.string = "x"
    s.map_list.b[0] = 1
    s.map_bytes["c.d"] = protobuf.Map(v="y").v
    assert s.map_message.a.string == "x"
    assert s.map_list.b == [1]
    assert s.map_bytes["c.d"] == b"y"
    assert s.map_message.a.string._fullName() == "pytest.map_message.a.string"
    assert s.map_bytes["c.d"]._fullName() == "pytest.map_bytes[c.d]"
    assert s.map_message._fullName("e.f") == "pytest.map_message[e.f]"
    assert s.int._fullName("x") == "pytest.int.x"
    assert s.int._fullName("x.y") == "pytest.int[x.y]"
    assert s._fullName("x.y") == "pytest[x.y]"
    s.map_bytes.c = protobuf.Unknown()
    assert "c" not in s.map_bytes
    s.map_bytes.e = "z"
    s.map_bytes.e = protobuf.Unknown()
    assert "e" not in s.map_bytes
    del s.map_bytes.missing
    s.map_bytes(a="1")
    assert len(s.map_bytes) == 1
    s.map_message.u.map_string(a="b")
    assert s.map_message.u.map_string.a == "b"
    s.map_message.v.map_string.c = "d"
    assert s.map_message.v.map_string.c == "d"


def test_repeated_messages(Scalars):
    s = wrap(Scalars)
    s.messages[1].string = "b"
    assert len(s.messages) == 2
    s.messages[-1].string = "c"
    assert s.messages[1].string == "c"
    s.messages[protobuf.append].string = "d"
    assert len(s.messages) == 3
    s.list_list[0][0] = 1
    assert s.list_list[0] == [1]
    assert s.messages[0].string._fullName() == "pytest.messages[0].string"
    assert s.messages._fullName() == "pytest.messages"
    s.list_bytes[0] = "a"
    s.list_bytes[0] = s.bytes
    s.list_int[0] = 1
    s.list_int[1] = 2
    s.list_int[-1] = 3
    assert s.list_int == s.list_int
    assert list(s.list_int) == [1, 3]
    s.list_int[0] = protobuf.Unknown()
    assert list(s.list_int) == [3]
    s.list_int[5] = protobuf.Unknown()
    assert s.messages.append()._key == 3
    assert s.list_int.append(4) == 4
    s.map_message.a.list_string.append("a")
    assert list(s.map_message.a.list_string) == ["a"]
    s.map_message.b.list_string[0] = "b"
    assert s.map_message.b.list_string[0] == "b"
    s.map_message.c.list_map[1].d = "e"
    assert len(s.map_message.c.list_map) == 2
    s.map_message.d.list_string("f", "g")
    assert list(s.map_message.d.list_string) == ["f", "g"]
    s.map_message.e.list_map.append()
    assert len(s.map_message.e.list_map) == 1


def test_repeated_bytes_append(Scalars):
    s = wrap(Scalars)
    s.list_bytes.append("a")
    assert s.list_bytes[0] == "a"


def test_repeated_append_field(Message):
    m = wrap(Message)
    m.string = "x"
    m.list_string.append(m.string)
    assert m.list_string[0] == "x"


def test_assign_message_field(Scalars):
    s = wrap(Scalars)
    other = wrap(Scalars)
    other.message.string = "x"
    s.message = other.message
    assert s.message.string == "x"


def test_assign_repeated_field(Scalars):
    s = wrap(Scalars)
    other = wrap(Scalars)
    other.list_int(1, 2)
    s.list_int = other.list_int
    assert s.list_int[1] == 2


def test_assign_struct_fields(Message):
    m = wrap(Message)
    m.struct = protobuf.Map(a=1)
    m.list = protobuf.List(1)
    assert m.struct == {"a": 1}
    assert m.list == [1]
    other = wrap(Message)
    other.list_string("x")
    other.list_map[0] = m.struct
    assert other.list_map[0] == {"a": 1}


def test_message_wrapper_errors(Scalars):
    with pytest.raises(ValueError):
        protobuf.Message(None, "pytest", Scalars.DESCRIPTOR)._ensure_message()
    m = protobuf.Message(None, None, Scalars.DESCRIPTOR, Scalars())
    assert m._fullName() == ""
    assert m._fullName("x") == "x"
    repeated = protobuf.RepeatedMessage(None, None, None)
    assert repeated._fullName() == ""
    assert repeated._fullName(0) == "0"
    repeated = protobuf.RepeatedMessage(None, "key", None)
    assert repeated._fullName(0) == "key[0]"
    ro = wrap(Scalars, "Read Only Test")
    with pytest.raises(ValueError):
        ro.message.string = "x"
    with pytest.raises(ValueError):
        ro.messages[0].string = "x"
    with pytest.raises(ValueError):
        ro.map_message.a.string = "x"
    with pytest.raises(ValueError):
        ro.list_int[0] = 1
    with pytest.raises(ValueError):
        ro.list_int.append(1)
    with pytest.raises(ValueError):
        ro.list_int()


def test_value_list_kind(Message):
    m = wrap(Message)
    m.list[0] = 1
    m.list[protobuf.append] = 2
    m.list[-1] = 3
    m.list[3].a = 1
    assert m.list == [1, 3, protobuf.Unknown(), {"a": 1}]
    assert m.list[-4] == 1
    assert m.list[protobuf.append]._key == 4
    m.list[1] = protobuf.Map().missing
    assert m.list._getUnknowns == {"pytest.list[1]": "missing"}
    assert list(m.list)[1] == protobuf.Unknown()
    m.list[3] = protobuf.Map().missing
    assert len(m.list._value.values) == 3
    assert len(m.list) == 5
    m.list[1] = 2
    del m.list[3]
    assert m.list == [1, 2, protobuf.Unknown()]
    m.struct.a = 1
    m.struct.a = protobuf.Map().missing
    assert "a" in m.struct
    assert m.struct._getUnknowns == {"pytest.struct.a": "missing"}
