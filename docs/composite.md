# composite.py Reference

`composite.py` defines the primary authoring model for function-pythonic. It provides:

- `BaseComposite`: the base class your composition classes subclass.
- Resource wrappers for composed and required resources.
- Condition and result helpers.
- Connection secret and connection-detail handling.
- Convenience descriptors for TTL and ready state.

## High-Level Model

At runtime, function-pythonic instantiates your `BaseComposite` subclass with a
`RunFunctionRequest`, then your `compose()` implementation mutates desired state via
wrapper objects.

Key object graph:
- `self.request`: wrapped incoming request (read-oriented).
- `self.response`: wrapped outgoing response (write-oriented).
- `self.resources`: composed resource collection (`desired.resources`).
- `self.requireds`: required/extra resource selectors and resolved items.
- `self.conditions`: composite condition helpers.
- `self.results`: function result helpers.

## Core Descriptors

## `TTL`

Exposed as `BaseComposite.ttl`.

- Getter reads `response.meta.ttl` and returns `int` or fractional `float`.
- Setter accepts `int` or `float` and maps into `seconds`/`nanos`.
- Invalid type raises `ValueError`.

## `Ready`

Exposed as `BaseComposite.ready`.

- Getter maps protobuf ready enum to `True`, `False`, or `None`.
- Setter writes protobuf ready enum:
  - `True` -> `READY_TRUE`
  - `False` -> `READY_FALSE`
  - `None` -> `READY_UNSPECIFIED`

## `ConnectionSecret`

Exposed as `BaseComposite.connectionSecret`.

- Crossplane v1:
  - Reads from `spec.writeConnectionSecretToRef`.
  - Setting to a different value raises `NotImplementedError`.
- Crossplane v2:
  - Reads/writes `input.writeConnectionSecretToRef` as a protobuf `Map` wrapper.

## `Connection`

Exposed as `BaseComposite.connection`; returns `_Connection`.

- Manages `desired.composite.connection_details`.
- In Crossplane v2, mirrors connection details into a composed `v1/Secret`.
- Ignores non-string/unknown/`None` values when appropriate.

## `BaseComposite`

Subclass this class and implement:

```python
class MyComposite(BaseComposite):
    def compose(self):
        ...
```

or async:

```python
class MyComposite(BaseComposite):
    async def compose(self):
        ...
```

Initialization behavior:
- Creates `self.request` (`protobuf.Message`) from input request.
- Creates `self.response` with:
  - copied `meta.tag`
  - default TTL of 60s
  - cloned `desired` and `context` from request
- Selects `self.parameters` from:
  - `observed.composite.resource.spec.parameters` for single-use composites
  - otherwise `input.parameters`
- Initializes:
  - `self.credentials`
  - `self.context`
  - `self.environment` (`apiextensions.crossplane.io/environment`)
  - `self.requireds`
  - `self.resources`
  - defaults: `autoReady=True`, `usages=False`, `unknownsFatal=False`
- Binds composite-focused shortcuts:
  - `self.observed`, `self.desired`, `self.apiVersion`, `self.kind`,
    `self.metadata`, `self.spec`, `self.status`
  - `self.conditions`, `self.results`, `self.events` (`events` is deprecated alias)

`compose()` in `BaseComposite` is abstract and raises `NotImplementedError`.

## Credentials API

## `Credentials`

Collection wrapper around `request.credentials`.

- Access: `self.credentials['name']` or `self.credentials.name`
- Supports `bool`, `len`, `contains`, and iteration of `(name, Credential)`

## `Credential`

Wrapper around a single credential’s `credential_data.data`.

- Access: `credential['key']` or `credential.key`
- Supports `bool`, `len`, `contains`, and iteration of `(key, value)`

## Composed Resource API

## `Resources`

Collection wrapper for `response.desired.resources`.

- Access/create by name: `self.resources.vpc` or `self.resources['vpc']`
- Assign raw resource object: `self.resources['x'] = resource`
- Delete by name.
- Iteration yields `(name, Resource)`

Instances are cached by composition resource name.

## `Resource`

Represents one composed resource entry.

Construction binds:
- `observed` = `request.observed.resources[name].resource`
- `desired` = `response.desired.resources[name].resource`
- `conditions`, `connection`
- toggles: `autoReady`, `usages`, `unknownsFatal` (default `None`, inherit from composite)

### `Resource(...)` call semantics

`resource(kind?, apiVersion?, namespace?, name?)`:
- Clears desired resource (`self.desired()`).
- Supports swapped first two args when first arg looks like `apiVersion`.
- Optionally sets `metadata.namespace` and `metadata.name`.
- Returns `self`.

### Key properties

- `apiVersion`, `kind`, `metadata`, `spec`, `type`, `data` map to desired resource.
- `status` is read from observed resource status.
- `externalName` reads desired annotation, falls back to observed annotation, and
  writes back into desired.

### Ready behavior

- `ready` getter:
  - returns cached explicit value if set
  - otherwise maps desired ready enum
  - if unspecified and auto-ready is enabled, computes via `auto_ready.resource_ready()`
    and sets desired ready true when determined.
- `ready` setter writes ready enum similarly to composite-level setter.

### Methods

- `setReadyCondition(type='Ready')`:
  - reads `conditions[type]`
  - if condition true -> `ready` set to observed name
  - else sets `ready` to a `status.not<type>Condition...` path
- `addDependency(resource, field=_notset)`:
  - Adds explicit dependency annotation:
    `metadata.annotations["pythonic.dependency/<resource.name>"] = <field>`
  - If field omitted, derives from dependent resource readiness.
  - Converts non-wrapper truthy/falsey values into observed-name or status-based tokens.

## Required Resource API

## `Requireds`

Collection wrapper for required resources.

- Crossplane v1 uses `extra_resources`.
- Crossplane v2 uses `required_resources`.
- Supports `bool`, `len`, `contains`, iteration of `(name, RequiredResources)`.

## `RequiredResources`

Selector + resolved-items wrapper for a named required resource request.

- Callable reset/update:
  - `required(kind?, apiVersion?, namespace?, name?, labels?)`
- Selector properties:
  - `apiVersion`, `kind`, `namespace`, `matchName`, `matchLabels`
- Resolved results:
  - index access `required[ix] -> RequiredResource`
  - `bool`, `len`, iteration

`matchLabels` setter accepts mapping-like iteration or `(key, value)` pairs.

## `RequiredResource`

Read-only wrapper for one returned required resource item.

Fields:
- `name`, `ix`
- `observed`, `apiVersion`, `kind`, `metadata`, `spec`, `type`, `data`, `status`
- `conditions`, `connection`

Truthiness reflects existence of `observed`.

## Conditions API

## `Conditions`

Wrapper for condition access on composite/resource/required resource.

- Access by type: `conditions['Ready']` or `conditions.Ready`
- Supports `bool`, `len`, iteration
- Merges condition types from observed and response (when response exists)

## `Condition`

Represents one condition type. Subclasses `protobuf.ProtobufValue`.

`_protobuf_value` serialization includes:
- `type`, `status`, `reason`, `message`, optional RFC3339 `lastTransitionTime`.

Mutation:
- `condition(reason=?, message=?, status=?, claim=?)` updates in one call.
- `status` maps between bool/unknown and protobuf status enums.
- `reason`, `message` read/write strings.
- `lastTransitionTime` reads from observed condition timestamp (read-only).
- `claim` toggles target:
  - composite only
  - composite + claim
  - unspecified

Creation rules:
- If response exists, setting fields creates condition entry when missing.
- Without response, creation is disallowed (`ValueError: Condition is read only`).

## Results API

## `Results`

Wrapper for `response.results`.

Factory methods:
- `info(reason?, message?, claim?)`
- `warning(reason?, message?, claim?)`
- `fatal(reason?, message?, claim?)`

Also supports `bool`, `len`, index, and iteration.

## `Result`

Wrapper around one result entry.

Properties:
- severity flags: `info`, `warning`, `fatal`
- `reason`
- `message`
- `claim` target (composite vs composite+claim vs unspecified)

A `Result()` without backing entry is falsey and ignores setters.

## `_Connection`

Internal helper returned by `BaseComposite.connection`.

Behavior:
- Reads/writes composite connection details map.
- `observed` exposes observed connection details.
- `__call__(**kwargs)` clears and resets connection details.
- On v2, keeps a composed secret resource synchronized:
  - secret name defaults to `connection-secret` or `connectionSecret.resourceName`
  - sets type `connection.crossplane.io/v1alpha1`
  - base64-encodes values into `secret.data`
  - removes secret when last key removed
- For cluster-scoped XR without secret namespace, emits fatal result:
  - reason: `ConnectionNoNamespace`
  - message: `Cluster scoped XR must specify connection secret namespace`

## Minimal Example

```python
from crossplane.pythonic import BaseComposite

class ExampleComposite(BaseComposite):
    def compose(self):
        bucket = self.resources.bucket("Bucket", "s3.aws.crossplane.io/v1beta1")
        bucket.spec.forProvider.region = self.spec.region

        # propagate observed id when available
        self.status.bucketId = bucket.status.atProvider.id

        # optional condition/result
        self.conditions.BucketReady("Available", "Bucket is ready", True)
        self.results.info("Composed", "Bucket desired state generated")
```

## Crossplane v1 vs v2 Differences in This Module

- Required resources:
  - v1: `extra_resources`
  - v2: `required_resources`
- Connection secret handling:
  - v1: relies on XR `writeConnectionSecretToRef`, no write-through override
  - v2: allows `connectionSecret` overrides and manages composed secret mirror
