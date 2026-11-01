import pytest

from crossplane.pythonic import protobuf


def test_map():
    value = protobuf.Map(a=1, b=2)
    assert len(value) == 2
    assert value.a == 1
    assert value["a"] == 1
    assert value.b == 2
    value.c = 3
    assert len(value) == 3
    assert value.c == 3
    value = protobuf.Map()
    assert value
    assert len(value) == 0
    value["a"] = 1
    assert value
    assert len(value) == 1
    assert value.a == 1


def test_list():
    value = protobuf.List(1, 2)
    assert len(value) == 2
    assert value[0] == 1
    assert value[1] == 2
    value[2] = 3
    assert len(value) == 3
    assert value[2] == 3
    value = protobuf.List()
    assert value
    assert len(value) == 0
    value[0] = 1
    assert value
    assert len(value) == 1
    assert value[0] == 1
    value[protobuf.append] = 2
    assert len(value) == 2
    assert value[0] == 1
    assert value[1] == 2
    assert value[-2] == 1
    assert value[-1] == 2
    value[-1] = 3
    assert len(value) == 2
    assert value[1] == 3


def test_unkown():
    value = protobuf.Unknown()
    assert not value
    assert value._isUnknown
    value.a = 1
    assert value
    assert not value._isUnknown
    assert value._isMap
    value = protobuf.Unknown()
    assert not value
    assert value._isUnknown
    value[0] = 1
    assert value
    assert not value._isUnknown
    assert value._isList


def test_yaml():
    yaml = """\
a: 1
b: 2
"""
    value = protobuf.Yaml(yaml)
    assert isinstance(value, protobuf.Value)
    assert value._isMap
    assert len(value) == 2
    assert str(value) == yaml
    assert format(value) == yaml
    assert format(value, "yaml") == yaml
    yaml = """\
- 1
- 2
"""
    value = protobuf.Yaml(yaml)
    assert isinstance(value, protobuf.Value)
    assert value._isList
    assert len(value) == 2
    assert str(value) == yaml
    assert format(value) == yaml
    assert format(value, "yaml") == yaml
    value = protobuf.Yaml("test")
    assert isinstance(value, protobuf.Value)
    assert value == "test"
    value = protobuf.Yaml("1")
    assert isinstance(value, protobuf.Value)
    assert value == 1
    value = protobuf.Yaml("1.2")
    assert isinstance(value, protobuf.Value)
    assert value == 1.2


def test_json():
    json = """\
{
  "a": 1,
  "b": 2
}"""
    value = protobuf.Json(json)
    assert isinstance(value, protobuf.Value)
    assert value._isMap
    assert len(value) == 2
    assert format(value, "json") == json
    json = """\
[
  1,
  2
]"""
    value = protobuf.Json(json)
    assert isinstance(value, protobuf.Value)
    assert value._isList
    assert len(value) == 2
    assert format(value, "json") == json
    value = protobuf.Json('"test"')
    assert isinstance(value, protobuf.Value)
    assert value == "test"
    value = protobuf.Json("1")
    assert isinstance(value, protobuf.Value)
    assert value == 1
    value = protobuf.Json("1.2")
    assert isinstance(value, protobuf.Value)
    assert value == 1.2


def test_values_map():
    values = protobuf.Map(
        map=protobuf.Map(),
        map2={},
        list=protobuf.List(),
        list2=[],
        unknown=protobuf.Unknown(),
        none=None,
        str="test",
        int=1,
        float=1.1,
        bool=True,
    )
    assert isinstance(values.map, protobuf.Value)
    assert values.map._isMap
    assert isinstance(values.map2, protobuf.Value)
    assert values.map2._isMap
    assert isinstance(values.list, protobuf.Value)
    assert values.list._isList
    assert isinstance(values.list2, protobuf.Value)
    assert values.list2._isList
    assert isinstance(values.unknown, protobuf.Value)
    assert values.unknown._isUnknown
    assert values.none == None
    assert isinstance(values.str, protobuf.Value)
    assert values.str == "test"
    assert isinstance(values.int, protobuf.Value)
    assert values.int == 1
    assert isinstance(values.float, protobuf.Value)
    assert values.float == 1.1
    assert isinstance(values.bool, protobuf.Value)
    assert values.bool == True
    assert isinstance(values.placeholder, protobuf.Value)
    assert values.placeholder._isUnknown
    assert "map" in values
    assert "nope" not in values
    assert values == values  # noqa: PLR0124
    assert hash(values) == hash(values)
    assert values._getUnknowns
    assert values == values  # noqa: PLR0124


def test_dictionary_union_map():
    value = protobuf.Map(a=1)
    other = protobuf.Map(b=1.1)
    dictionary = {"c": 1.2}
    temp = other | value
    assert isinstance(temp, protobuf.Value)
    assert temp.a == 1
    assert temp.b == 1.1
    temp = temp | dictionary
    assert isinstance(temp, protobuf.Value)
    assert temp.a == 1
    assert temp.c == 1.2


def test_values_list():
    values = protobuf.List(
        protobuf.Map(),  # 0
        {},  # 1
        protobuf.List(),  # 2
        [],  # 3
        protobuf.Unknown(),  # 4
        None,  # 5
        "test",  # 6
        1,  # 7
        1.1,  # 8
        True,  # 9
    )
    assert isinstance(values[0], protobuf.Value)
    assert values[0]._isMap
    assert isinstance(values[1], protobuf.Value)
    assert values[1]._isMap
    assert isinstance(values[2], protobuf.Value)
    assert values[2]._isList
    assert isinstance(values[3], protobuf.Value)
    assert values[3]._isList
    assert isinstance(values[4], protobuf.Value)
    assert values[4]._isUnknown
    assert values[5] == None
    assert isinstance(values[6], protobuf.Value)
    assert values[6] == "test"
    assert isinstance(values[7], protobuf.Value)
    assert values[7] == 1
    assert isinstance(values[8], protobuf.Value)
    assert values[8] == 1.1
    assert isinstance(values[9], protobuf.Value)
    assert values[9] == True
    assert isinstance(values[10], protobuf.Value)
    assert values[10]._isUnknown
    assert "test" in values
    assert "nope" not in values
    assert protobuf.Unknown() in values
    assert values == values  # noqa: PLR0124
    assert hash(values) == hash(values)
    assert values._getUnknowns
    assert values == values  # noqa: PLR0124


def test_create_child():
    map = protobuf.Unknown()
    list = protobuf.Unknown()
    map.a.b = "c"
    assert "b" in map.a
    assert map.a.b == "c"
    del map.a.b
    assert "b" not in map.a
    assert not map._getUnknowns
    map.a.b = protobuf.Unknown()
    assert map._getUnknowns
    list[0][0] = "c"
    assert "c" in list[0]
    assert list[0][0] == "c"
    del list[0][0]
    assert "c" not in list[0]
    assert not list._getUnknowns
    list[0][0] = protobuf.Unknown()
    assert list._getUnknowns


def test_parsers_passthrough():
    unknown = protobuf.Unknown()
    for parser in (
        protobuf.Yaml,
        protobuf.YamlAll,
        protobuf.Json,
        protobuf.B64Encode,
        protobuf.B64Decode,
    ):
        assert parser(unknown) is unknown
    values = protobuf.Map(
        yaml="a: 1",
        all="a: 1\n---\nb: 2\n",
        json='{"a": 1}',
        plain="hello",
        encoded="aGVsbG8=",
    )
    assert protobuf.Yaml(values.yaml) == {"a": 1}
    assert protobuf.YamlAll(values.all) == [{"a": 1}, {"b": 2}]
    assert protobuf.YamlAll("a: 1") == [{"a": 1}]
    assert protobuf.Json(values.json) == {"a": 1}
    assert protobuf.B64Encode(values.plain) == "aGVsbG8="
    assert protobuf.B64Decode(values.encoded) == "hello"
    assert protobuf.B64Decode(protobuf.B64Encode("hello")) == "hello"
    with pytest.raises(ValueError):
        protobuf.Yaml("a: 1", "Read Only Test").b = 2


def test_scalars():
    values = protobuf.Map(
        str="12", int=12, float=1.5, true=True, false=False, none=None
    )
    assert str(values.str) == "12"
    assert str(values.int) == "12"
    assert str(values.float) == "1.5"
    assert str(values.true) == "true"
    assert str(values.false) == "false"
    assert str(values.none) == "null"
    assert str(values.unknown) == "<<UNKNOWN>>"
    assert int(values.str) == 12
    assert int(values.float) == 1
    assert int(values.true) == 1
    assert int(values.unknown) == 0
    assert float(values.str) == 12.0
    assert float(values.int) == 12.0
    assert float(values.false) == 0.0
    assert float(values.unknown) == 0.0
    with pytest.raises(TypeError):
        int(values)
    with pytest.raises(TypeError):
        float(values)
    assert len(values.str) == 2
    assert len(values.true) == 1
    assert len(values.false) == 0
    assert len(values.int) == 0
    assert len(values.unknown) == 0
    assert hash(values.str) == hash("12")
    assert hash(values.int) == hash(12.0)
    assert hash(values.true) == hash(True)
    assert hash(values.none) == hash(None)
    assert hash(values.unknown) == 0
    assert "x" not in values.str
    assert values.str._raw == "12"
    assert values.int._raw == 12
    assert values.true._raw is True
    assert values.none._raw == 0
    assert values.unknown._raw is protobuf._Unknown
    with pytest.raises(ValueError):
        protobuf.Value(None, None, object())


def test_scalar_equality():
    values = protobuf.Map(str="a", int=1, true=True, none=None, list=[1], map={"a": 1})
    assert values.str == protobuf.Map(x="a").x
    assert values.str != 1
    assert values.int == protobuf.Map(x=1).x
    assert values.int != "1"
    assert values.true == protobuf.Map(x=True).x
    assert values.true != 1
    assert values.none == protobuf.Map(x=None).x
    assert values.none == None
    assert values.none != 0
    assert values.str != values.int
    assert values.unknown == protobuf.Unknown()
    assert values.unknown != None
    assert values.list == [1]
    assert values.list != [1, 2]
    assert values.list != [2]
    assert values.list != {"a": 1}
    assert values.map == {"a": 1}
    assert values.map != {"a": 1, "b": 2}
    assert values.map != {"b": 1}
    assert values.map != {"a": 2}
    assert values.map != [1]


def test_format():
    values = protobuf.Map(a=1, b=[True, None, "x"], c=protobuf.Unknown(), d=1.5)
    assert (
        format(values, "jsonc")
        == '{"a":1,"b":[true,null,"x"],"c":"<<UNKNOWN>>","d":1.5}'
    )
    assert format(values, "protobuf") == str(values._value)
    assert format(values.a, "yaml") == "1\n...\n"
    assert format(values.d, "yaml") == "1.5\n...\n"
    assert format(values.b[1], "yaml") == "null\n...\n"
    assert format(values.b[0], "jsonc") == "true"
    assert format(protobuf.List(1), "protobuf") == str(protobuf.List(1)._value)


def test_union():
    value = protobuf.Map(a=1)
    assert ({"b": 2} | value) == {"a": 1, "b": 2}
    assert (value | {"a": 2}) == {"a": 2}
    with pytest.raises(TypeError):
        value | [1]
    with pytest.raises(TypeError):
        protobuf.List(1) | {"a": 1}
    with pytest.raises(TypeError):
        [1] | value
    with pytest.raises(TypeError):
        {"a": 1} | protobuf.List(1)


def test_context_manager():
    with protobuf.Map(a=1) as value:
        assert value.a == 1


def test_call():
    value = protobuf.Map(a=1)
    assert value(b=2) == {"b": 2}
    assert value(1, 2) == [1, 2]
    assert value() == {}
    with pytest.raises(ValueError):
        value(1, b=2)
    with pytest.raises(ValueError):
        protobuf.Value(None, None, {}, "Read Only Test")()


def test_invalid_keys():
    values = protobuf.Map(map={}, list=[], str="x")
    with pytest.raises(ValueError):
        values.list.a  # noqa: B018
    with pytest.raises(ValueError):
        values.map[0]
    with pytest.raises(ValueError):
        values.list.a = 1
    with pytest.raises(ValueError):
        values.map[0] = 1
    with pytest.raises(ValueError):
        del values.list.a
    with pytest.raises(ValueError):
        del values.map[0]
    with pytest.raises(TypeError):
        values[1.5]
    with pytest.raises(TypeError):
        values[None] = 1
    with pytest.raises(ValueError):
        values.a = object()
    values.unknown.x = 1
    del protobuf.Unknown().a
    assert values[protobuf.Map(k="str").k] == "x"
    assert "str" in values
    assert protobuf.Map(k="str").k in values


def test_value_list_key():
    values = protobuf.List("a", "b")
    assert values[protobuf.Map(k=1).k] == "b"


def test_readonly():
    values = protobuf.Value(None, None, {"a": {"b": 1}, "l": [1]}, "Read Only Test")
    assert values.a.b == 1
    with pytest.raises(ValueError):
        values.a = 2
    with pytest.raises(ValueError):
        del values.a
    with pytest.raises(ValueError):
        values.c.d = 1
    with pytest.raises(ValueError):
        values._create_child("c")


def test_readonly_nested():
    values = protobuf.Value(None, None, {"a": {"b": 1}}, "Read Only Test")
    with pytest.raises(ValueError):
        values.a.b = 2


def test_append_and_negative_keys():
    values = protobuf.List()
    assert values[protobuf.append]._isUnknown
    assert values[-1]._isUnknown
    values[protobuf.append] = 1
    values[protobuf.append].a = 2
    values[-1].b = 3
    assert values == [1, {"a": 2, "b": 3}]
    values[-2] = 0
    assert values[0] == 0
    unknown = protobuf.Unknown()
    unknown[protobuf.append].a = 1
    unknown[-1].b = 2
    unknown[3] = "x"
    assert unknown == [{"a": 1, "b": 2}, protobuf.Unknown(), protobuf.Unknown(), "x"]


def test_set_value_kinds():
    source = protobuf.Map(map={"a": 1}, list=[1], str="x", none=None, num=1, bool=True)
    target = protobuf.Map()
    for key, value in source:
        target[key] = value
    assert target == source
    target.unknown = source.missing
    assert target._getDependencies == {
        "bool": "bool",
        "list": "list",
        "list[0]": "list[0]",
        "map": "map",
        "map.a": "map.a",
        "none": "none",
        "num": "num",
        "str": "str",
        "unknown": "missing",
    }
    assert target._getUnknowns == {"unknown": "missing"}
    assert len(target) == 7
    assert "unknown" in target
    target.unknown = 1
    assert not target._getUnknowns


def test_set_bytes():
    values = protobuf.Map()
    values.a = b"bytes"
    assert values.a == "bytes"


def test_unknowns_in_list():
    source = protobuf.Map()
    values = protobuf.List(1, 2, 3)
    values[1] = source.a
    values[2] = source.b
    assert len(values) == 3
    assert values._getUnknowns == {"1": "a", "2": "b"}
    assert [value for value in values][1:] == [protobuf.Unknown(), protobuf.Unknown()]
    values[1] = 2
    assert values == [1, 2, protobuf.Unknown()]
    del values[1]
    assert values._getUnknowns == {"1": "b"}
    del values[5]
    del values[1]
    assert values == [1]
    assert not values._getUnknowns


def test_delete_shifts_dependencies():
    source = protobuf.Map(a="x")
    values = protobuf.List(1, source.a)
    del values[0]
    assert values._getDependencies == {"0": "a"}


def test_unknowns_in_map():
    source = protobuf.Map()
    values = protobuf.Map(a=1)
    values.a = source.missing
    assert "a" in values
    assert values._getUnknowns == {"a": "missing"}
    del values.a
    assert not values._getUnknowns


def test_full_name():
    values = protobuf.Value(None, "root", {"a": {"b-c": [{"d": 1}]}})
    assert values.a["b-c"][0].d._fullName() == "root.a['b-c'][0].d"
    assert values.a._fullName("x") == "root.a.x"
    assert values._fullName() == "root"
    assert protobuf.Map()._fullName() == ""
    assert protobuf.Map()._fullName("x") == "x"
    assert values.a.x._fullName("y") == "root.a.x.y"
    assert values.a.x._fullName("y.z") == "root.a.x[y.z]"
    assert values.a.x._fullName(0) == "root.a.x[0]"
    assert protobuf.Value(None, 0, 1)._fullName() == "0"


def test_patch_unknowns():
    source = protobuf.Map()
    desired = protobuf.Map(
        a=source.a,
        map={"b": source.b, "c": 1},
        list=[{"d": source.d}, 2],
        other={"e": 1},
    )
    observed = protobuf.Map(a=1, map={"b": 2, "c": 3}, list=[{"d": 4}, 5], other=[1])
    desired._patchUnknowns(observed)
    assert desired == {
        "a": 1,
        "map": {"b": 2, "c": 1},
        "list": [{"d": 4}, 2],
        "other": {"e": 1},
    }


def test_render_unknowns():
    source = protobuf.Value(None, "source", {})
    desired = protobuf.Map(a=source.a, map={"b": source.b}, list=[{"c": source.c}])
    desired._renderUnknowns(lambda name: name.upper())
    assert desired == {
        "a": "UNKNOWN:SOURCE.A",
        "map": {"b": "UNKNOWN:SOURCE.B"},
        "list": [{"c": "UNKNOWN:SOURCE.C"}],
    }
    assert desired._getDependencies == {
        "a": "source.a",
        "map.b": "source.b",
        "list[0].c": "source.c",
    }


def test_invalid_value_type():
    value = protobuf.Map()
    value.__dict__["_value"] = object()
    with pytest.raises(ValueError):
        value._kind  # noqa: B018
    with pytest.raises(ValueError):
        protobuf.Map(a=1).a._ensure_map()
    with pytest.raises(ValueError):
        protobuf.Map(a=1).a._ensure_list()
