# protobuf.py Reference

This module provides Python wrappers around protobuf messages so Crossplane function
code can read and write deeply nested fields with concise, Pythonic syntax.

## Purpose

- Traverse protobuf messages with attribute or key access.
- Write nested fields without manually creating intermediate nodes.
- Represent missing values as `Unknown` placeholders instead of raising errors.
- Track value dependencies and unknown paths for composition orchestration.
- Render structures as YAML, JSON, compact JSON, or protobuf text.

## Top-Level Helpers

- `Map(**kwargs) -> Value`
- `List(*args) -> Value`
- `Unknown() -> Value`
- `Yaml(string, readOnly=None) -> Value`
- `YamlAll(string, readOnly=None) -> Value`
- `Json(string, readOnly=None) -> Value`
- `B64Encode(string) -> str`
- `B64Decode(string) -> str`

Notes:
- `Yaml`, `YamlAll`, `Json`, `B64Encode`, and `B64Decode` accept `FieldMessage` and
  `Value` inputs and convert them via `str(...)`.
- `append` is defined as `sys.maxsize` and is used as a sentinel index for appending
  list/repeated values.

## Wrapper Types

## `Message`

Wraps a protobuf message descriptor + instance.

Core behavior:
- Field access: `obj.field` and `obj['field']`.
- Missing branch reads return wrappers containing unknown values.
- Writes auto-create parents as needed.
- `obj()` clears the message and optionally sets fields via kwargs.
- Iteration yields `(field_name, wrapped_value)` over descriptor fields.
- Supports `bool`, `len`, `contains`, `iter`, `hash`, `==`, `str`, `format`.

Formatting:
- `format(obj, 'yaml')` (default), `format(obj, 'json')`, `format(obj, 'jsonc')`,
  `format(obj, 'protobuf')`.

## `MapMessage`

Wraps protobuf map fields.

Core behavior:
- Access with `obj[key]` / `obj.key` (string keys).
- `obj()` clears map and can repopulate via kwargs.
- Unknown assignments remove entries.
- Iteration yields sorted `(key, wrapped_value)`.

## `RepeatedMessage`

Wraps repeated protobuf fields.

Core behavior:
- Index access with `obj[ix]` (supports negative indices).
- Append by index sentinel: `obj[append]`.
- `obj()` clears list and repopulates from args.
- `append(message)` appends and returns wrapped element.
- Iteration yields wrapped values in index order.

## `FieldMessage`

Wraps scalar protobuf fields.

Core behavior:
- Unknown scalar values remain non-throwing placeholders.
- Supports conversions: `bytes`, `str`, `int`, `float`, `format`.
- Unknown converts to `None` for string/bytes and to `None` for int/float conversion
  calls from this wrapper (caller should guard with truthiness where appropriate).

## `Value`

Wraps protobuf `struct_pb2.Value`, `Struct`, and `ListValue`.

Supported kinds:
- `struct_value`, `Struct`
- `list_value`, `ListValue`
- `string_value`
- `number_value`
- `bool_value`
- `null_value`
- `Unknown`

Core behavior:
- Dynamic map/list access and mutation with unknown-safe traversal.
- Attribute access maps to key access.
- `obj()` resets to empty and repopulates from args/kwargs.
- Tracks:
  - `_getUnknowns`: map from destination path to unknown source path.
  - `_getDependencies`: map from destination path to dependency source path.
- Unknown management:
  - `_patchUnknowns(patches)` applies observed values into previously unknown slots.
  - `_renderUnknowns(trimFullName)` materializes unknowns as
    `UNKNOWN:<trimmed-path>` strings and records dependencies.

Kind helpers:
- `_kind`, `_isUnknown`, `_isMap`, `_isList`, `_raw`.

## Read-Only Mode

Most wrappers accept or propagate `readOnly`. Mutating methods (`__setitem__`,
`__delitem__`, `__call__`, append/create helpers) raise `ValueError` when read-only.

## Unknown Semantics

- Reading missing paths yields `Unknown` wrappers instead of errors.
- Unknown evaluates falsey in boolean contexts.
- Unknown values can be assigned into structures and tracked as dependencies.
- YAML/JSON rendering uses `<<UNKNOWN>>` markers for unknown values unless patched.

## Formatting and Serialization

`_formatObject` supports:
- `yaml` (default)
- `json` (pretty)
- `jsonc` (compact)
- `protobuf` (protobuf text format when wrapping protobuf-backed objects)

Custom encoders:
- `_JSONEncoder` serializes wrappers and `datetime` values.
- `_Dumper` preserves multiline string style and serializes wrapper types cleanly.

## Typical Usage

```python
from crossplane.pythonic.protobuf import Map, append

# read
region = request.observed.composite.resource.spec.region

# write with implicit creation of intermediate nodes
response.desired.resources.vpc.resource.spec.forProvider.region = "us-east-1"

# map/list handling
response = Map()
response.context.example.name = "demo"
response.context.example.enabled = True
response.context.items[0] = "a"
response.context.items[1] = "b"
response.context.items[append] = "c"
```

## Implementation Notes

- Wrapper caches are used to preserve object identity for repeated accesses.
- Paths are tracked with `_fullName(...)` helpers to produce stable dependency keys.
- Bytes assignment to scalar protobuf fields is normalized from UTF-8 strings where
  applicable.
