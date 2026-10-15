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
