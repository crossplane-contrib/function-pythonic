import datetime
import logging
import types
import typing
from typing import cast

from google.protobuf.duration_pb2 import Duration

from . import (
    auto_ready,
    protobuf,
)
from .proto.v1 import run_function_pb2 as fnv1

_notset = sentinel("_notset")


class ConnectionSecret:
    def __get__(self, composite: BaseComposite, objtype=None) -> protobuf.Value:
        if composite.crossplane_v1:
            return composite.spec.writeConnectionSecretToRef
        if not composite._connectionSecret:
            composite._connectionSecret = protobuf.Map()
            for key, value in composite.request.input.writeConnectionSecretToRef:
                composite._connectionSecret[key] = value
        return composite._connectionSecret

    def __set__(
        self, composite: BaseComposite, values: typing.Mapping | protobuf.Value
    ) -> None:
        if composite.crossplane_v1:
            if values != composite.spec.writeConnectionSecretToRef:
                raise NotImplementedError(
                    "Connection Secret cannot be set in Crossplane V1"
                )
            return
        composite._connectionSecret = protobuf.Map()
        for entry in values:
            if isinstance(entry, str):
                composite._connectionSecret[entry] = values[entry]
            elif isinstance(entry, (tuple, list)):
                composite._connectionSecret[entry[0]] = entry[1]


class Connection:
    def __get__(self, composite: BaseComposite, objtype=None) -> _Connection:
        if not composite._connection:
            composite._connection = _Connection(composite)
        return composite._connection

    def __set__(
        self, composite: BaseComposite, values: typing.Mapping | protobuf.Value
    ) -> None:
        connection = self.__get__(composite)
        connection()
        for entry in values:
            if isinstance(entry, str):
                connection[entry] = values[entry]
            elif isinstance(entry, (tuple, list)):
                connection[entry[0]] = entry[1]


class TTL:
    def __get__(self, composite: BaseComposite, objtype=None) -> int | float:
        if composite.response.meta.ttl.nanos == 0:
            return int(composite.response.meta.ttl.seconds)
        return float(composite.response.meta.ttl.seconds) + (
            float(composite.response.meta.ttl.nanos) / 1000000000.0
        )

    def __set__(self, composite: BaseComposite, ttl: float) -> None:
        if isinstance(ttl, int):
            composite.response.meta.ttl.seconds = ttl
            composite.response.meta.ttl.nanos = 0
        elif isinstance(ttl, float):
            composite.response.meta.ttl.seconds = int(ttl)
            if ttl.is_integer():
                composite.response.meta.ttl.nanos = 0
            else:
                composite.response.meta.ttl.nanos = int(
                    (ttl - int(composite.response.meta.ttl.seconds)) * 1000000000
                )
        else:
            raise TypeError("ttl must be an int or float")


class Ready:
    def __get__(
        self, composite: BaseComposite, objtype=None
    ) -> bool | protobuf.Value | None:
        if composite._ready is not None:
            return composite._ready
        if (
            cast(protobuf.Message, composite.desired._parent).ready
            == fnv1.Ready.READY_TRUE
        ):
            return True
        if (
            cast(protobuf.Message, composite.desired._parent).ready
            == fnv1.Ready.READY_FALSE
        ):
            return False
        return None

    def __set__(self, composite: BaseComposite, ready: protobuf.Value | bool | None):
        composite._ready = ready
        if ready:
            cast(
                protobuf.Message, composite.desired._parent
            ).ready = fnv1.Ready.READY_TRUE
        elif ready is None:
            cast(
                protobuf.Message, composite.desired._parent
            ).ready = fnv1.Ready.READY_UNSPECIFIED
        else:
            cast(
                protobuf.Message, composite.desired._parent
            ).ready = fnv1.Ready.READY_FALSE


class BaseComposite:
    def __init__(
        self,
        crossplane_v1: bool,
        request: fnv1.RunFunctionRequest,
        logger: logging.Logger,
    ) -> None:
        self.crossplane_v1 = crossplane_v1
        self.request = protobuf.Message(
            None, "request", request.DESCRIPTOR, request, "Function Request"
        )
        response = fnv1.RunFunctionResponse(
            meta=fnv1.ResponseMeta(
                tag=request.meta.tag,
                ttl=Duration(
                    seconds=60,
                ),
            ),
            desired=request.desired,
            context=request.context,
        )
        self.response = protobuf.Message(
            None, "response", response.DESCRIPTOR, response
        )
        self.logger: logging.Logger = logger
        self.capabilities: Capabilities = Capabilities(
            cast(protobuf.RepeatedMessage, self.request.meta.capabilities)
        )
        self.parameters: protobuf.Value = cast(
            protobuf.Value, self.request.input.parameters
        )
        self.credentials: Credentials = Credentials(self.request)
        self.context: protobuf.Value = cast(protobuf.Value, self.response.context)
        self.environment: protobuf.Value = self.context[
            "apiextensions.crossplane.io/environment"
        ]
        self.requireds: Requireds = Requireds(self)
        self.watched: RequiredResource = self.requireds[
            "ops.crossplane.io/watched-resource"
        ][0]
        self.schemas: Schemas = Schemas(self)
        self.resources: Resources = Resources(self)
        self.autoReady: bool = True
        self.usages: bool = False
        self.unknownsFatal: bool = False

        observed: protobuf.Message = cast(
            protobuf.Message, self.request.observed.composite
        )
        desired: protobuf.Message = cast(
            protobuf.Message, self.response.desired.composite
        )
        self.observed: protobuf.Value = cast(protobuf.Value, observed.resource)
        self.desired: protobuf.Value = cast(protobuf.Value, desired.resource)
        self.apiVersion: protobuf.Value = cast(protobuf.Value, self.observed.apiVersion)
        self.kind: protobuf.Value = self.observed.kind
        self.metadata: protobuf.Value = self.observed.metadata
        self.spec: protobuf.Value = self.observed.spec
        self.status: protobuf.Value = self.desired.status
        self.output: protobuf.Value = cast(protobuf.Value, self.response.output)
        self.conditions: Conditions = Conditions(observed, self.response)
        self.results: Results = Results(self.response)

        self._connectionSecret: protobuf.Value | None = None
        self._connection: _Connection | None = None
        self._ready: protobuf.Value | bool | None = None

    ttl: TTL = TTL()
    connectionSecret: ConnectionSecret = ConnectionSecret()
    connection: Connection = Connection()
    ready: Ready = Ready()

    async def compose(self) -> None:
        raise NotImplementedError()


class Capabilities:
    def __init__(self, capabilities: protobuf.RepeatedMessage):
        self._capabilities: protobuf.RepeatedMessage = capabilities

    def __bool__(self):
        return fnv1.CAPABILITY_CAPABILITIES in self._capabilities

    @property
    def requireds(self) -> bool | None:
        return (
            fnv1.CAPABILITY_REQUIRED_RESOURCES in self._capabilities if self else None
        )

    @property
    def credentials(self) -> bool | None:
        return fnv1.CAPABILITY_CREDENTIALS in self._capabilities if self else None

    @property
    def conditions(self) -> bool | None:
        return fnv1.CAPABILITY_CONDITIONS in self._capabilities if self else None

    @property
    def schemas(self) -> bool | None:
        return fnv1.CAPABILITY_REQUIRED_SCHEMAS in self._capabilities if self else None


class Credentials:
    _request: protobuf.Message

    def __init__(self, request: protobuf.Message):
        self._request: protobuf.Message = request

    def __getattr__(self, key: protobuf.TypeString) -> Credential:
        return self[key]

    def __getitem__(self, key: protobuf.TypeString) -> Credential:
        return Credential(cast(protobuf.Message, self._request.credentials[key]))

    def __bool__(self) -> bool:
        return bool(len(self))

    def __len__(self) -> int:
        return len(self._request.credentials)

    def __contains__(self, key: protobuf.TypeString) -> bool:
        return key in self._request.credentials

    def __iter__(self) -> typing.Generator[tuple[str, Credential]]:
        for key, resource in self._request.credentials:
            yield key, self[key]


class Credential:
    def __init__(self, credential: protobuf.Message):
        self._credential: protobuf.Message = credential

    def __getattr__(self, key: protobuf.TypeString) -> str:
        return self[key]

    def __getitem__(self, key: protobuf.TypeString) -> str:
        return str(self._credential.credential_data.data[key])

    def __bool__(self) -> bool:
        return bool(len(self))

    def __len__(self) -> int:
        return len(self._credential.credential_data.data)

    def __contains__(self, key: protobuf.TypeString) -> bool:
        return key in self._credential.credential_data.data

    def __iter__(self) -> typing.Generator[tuple[str, str]]:
        for key, resource in self._credential.credential_data.data:
            yield key, self[key]


class Resources:
    def __init__(self, composite: BaseComposite):
        self._composite: BaseComposite = composite
        self._cache: dict[protobuf.TypeString, Resource] = {}

    def __getattr__(self, key: protobuf.TypeString) -> Resource:
        return self[key]

    def __getitem__(self, key: protobuf.TypeString) -> Resource:
        resource = self._cache.get(key)
        if not resource:
            resource = Resource(self._composite, key)
            self._cache[key] = resource
        return resource

    def __bool__(self) -> bool:
        return bool(len(self))

    def __len__(self) -> int:
        return len(self._composite.response.desired.resources)

    def __contains__(self, key: protobuf.TypeString) -> bool:
        return key in self._composite.response.desired.resources

    def __iter__(self) -> typing.Generator[tuple[str, Resource]]:
        for name, resource in self._composite.response.desired.resources:
            yield name, self[name]

    def __setattr__(
        self,
        key: protobuf.TypeString,
        resource: typing.Mapping | protobuf.Value,
    ) -> None:
        if key in ("_composite", "_cache"):
            self.__dict__[str(key)] = resource
        else:
            self[key] = resource

    def __setitem__(
        self,
        key: protobuf.TypeString,
        resource: typing.Mapping | protobuf.Value,
    ) -> None:
        self._composite.response.desired.resources[key].resource = resource
        self._cache.pop(key, None)

    def __delattr__(self, key: protobuf.TypeString) -> None:
        del self[key]

    def __delitem__(self, key: protobuf.TypeString) -> None:
        if key in self._composite.response.desired.resources:
            del self._composite.response.desired.resources[key]
        self._cache.pop(key, None)


class Resource:
    def __init__(
        self,
        composite: BaseComposite,
        name: protobuf.TypeString,
    ):
        self._composite: BaseComposite = composite
        self.name: protobuf.TypeString = name
        observed: protobuf.Message = cast(
            protobuf.Message, composite.request.observed.resources[name]
        )
        desired: protobuf.Message = cast(
            protobuf.Message, composite.response.desired.resources[name]
        )
        self.observed: protobuf.Value = cast(protobuf.Value, observed.resource)
        self.desired: protobuf.Value = cast(protobuf.Value, desired.resource)
        self.conditions: Conditions = Conditions(observed)
        self.connection: protobuf.MapMessage = cast(
            protobuf.MapMessage, observed.connection_details
        )
        self.autoReady: bool | None = None
        self.usages: bool | None = None
        self.unknownsFatal: bool | None = None

    def __call__(
        self,
        kind: str | _notset = _notset,
        apiVersion: str | _notset = _notset,
        namespace: str | _notset = _notset,
        name: str | _notset = _notset,
    ) -> typing.Self:
        self.desired()
        if kind is not _notset:
            # Allow for apiVersion in the first arg and kind in the second arg
            if "/" in kind or kind == "v1":
                if apiVersion is not _notset:
                    self.kind = apiVersion
                apiVersion = kind
            else:
                self.kind = kind
        if apiVersion is not _notset:
            self.apiVersion = apiVersion
        if namespace is not _notset:
            self.metadata.namespace = namespace
        if name is not _notset:
            self.metadata.name = name
        return self

    @property
    def apiVersion(self) -> protobuf.Value:
        return self.desired.apiVersion

    @apiVersion.setter
    def apiVersion(self, apiVersion: protobuf.TypeString) -> None:
        self.desired.apiVersion = apiVersion

    @property
    def kind(self) -> protobuf.Value:
        return self.desired.kind

    @kind.setter
    def kind(self, kind: protobuf.TypeString) -> None:
        self.desired.kind = kind

    @property
    def externalName(self) -> protobuf.Value:
        name = self.metadata.annotations["crossplane.io/external-name"]
        if not name:
            name = self.observed.metadata.annotations["crossplane.io/external-name"]
            if name:
                self.externalName = name
        return name

    @externalName.setter
    def externalName(self, name: protobuf.TypeString) -> None:
        self.metadata.annotations["crossplane.io/external-name"] = name

    @property
    def metadata(self) -> protobuf.Value:
        return self.desired.metadata

    @metadata.setter
    def metadata(self, metadata: typing.Mapping | protobuf.Value) -> None:
        self.desired.metadata = metadata

    @property
    def spec(self) -> protobuf.Value:
        return self.desired.spec

    @spec.setter
    def spec(self, spec: typing.Mapping | protobuf.Value) -> None:
        self.desired.spec = spec

    # Used by Secret:v1
    @property
    def type(self) -> protobuf.Value:
        return self.desired.type

    @type.setter
    def type(self, type: str | protobuf.Value) -> None:
        self.desired.type = type

    @property
    def data(self) -> protobuf.Value:
        return self.desired.data

    @data.setter
    def data(self, data: typing.Mapping | protobuf.Value) -> None:
        self.desired.data = data

    @property
    def status(self) -> protobuf.Value:
        return self.observed.status

    @property
    def ready(self) -> protobuf.Value | bool | None:
        if not hasattr(self, "_ready"):
            if (
                cast(protobuf.Message, self.desired._parent).ready
                == fnv1.Ready.READY_TRUE
            ):
                self._ready = True
            elif (
                cast(protobuf.Message, self.desired._parent).ready
                == fnv1.Ready.READY_FALSE
            ):
                self._ready = False
            else:
                self._ready = None
                if self.autoReady or (
                    self.autoReady is None and self._composite.autoReady
                ):
                    ready = auto_ready.resource_ready(self)
                    if ready:
                        self._ready = ready
                        cast(
                            protobuf.Message, self.desired._parent
                        ).ready = fnv1.Ready.READY_TRUE
        return self._ready

    @ready.setter
    def ready(self, ready: protobuf.Value | bool | None) -> None:
        self._ready = ready
        if ready:
            cast(protobuf.Message, self.desired._parent).ready = fnv1.Ready.READY_TRUE
        elif ready is None:
            cast(
                protobuf.Message, self.desired._parent
            ).ready = fnv1.Ready.READY_UNSPECIFIED
        else:
            cast(protobuf.Message, self.desired._parent).ready = fnv1.Ready.READY_FALSE

    def setReadyCondition(self, type: str = "Ready"):
        condition: Condition = self.conditions[type]
        if condition.status:
            self.ready = self.observed.metadata.name
        else:
            error = f"not{type}Condition"
            if condition.reason:
                self.ready = self.status[error][condition.reason]
            else:
                self.ready = self.status[error]

    def addDependency(
        self,
        resource: Resource,
        field: protobuf.FieldMessage | protobuf.Value | None | _notset = _notset,
    ):
        dependency: protobuf.FieldMessage | protobuf.Value | bool | None = None
        if field is _notset:
            dependency = resource.ready
            if dependency is None:
                dependency = auto_ready.resource_ready(resource)
                if dependency is None:
                    dependency = False
                resource.ready = dependency
        elif field is None:
            field = _notset
        else:
            dependency = field
        if not isinstance(dependency, (protobuf.FieldMessage, protobuf.Value)):
            if field:
                dependency = resource.observed.metadata.name
            else:
                if not resource.observed.metadata.name:
                    dependency = resource.observed.metadata.name
                else:
                    dependency = resource.status.notReady
        self.metadata.annotations[f"pythonic.dependency/{resource.name}"] = dependency


class Requireds:
    def __init__(self, composite: BaseComposite):
        self._composite: BaseComposite = composite
        self._cache: dict[protobuf.TypeString, RequiredResources] = {}

    def __getattr__(self, key: protobuf.TypeString) -> RequiredResources:
        return self[key]

    def __getitem__(self, key: protobuf.TypeString) -> RequiredResources:
        required = self._cache.get(key)
        if not required:
            required = RequiredResources(self._composite, key)
            self._cache[key] = required
        return required

    def __bool__(self) -> bool:
        return bool(len(self))

    def __len__(self) -> int:
        names = set()
        if self._composite.crossplane_v1:
            for name, resource in self._composite.request.extra_resources:
                names.add(name)
            for name, resource in self._composite.response.requirements.extra_resources:
                names.add(name)
        else:
            for name, resource in self._composite.request.required_resources:
                names.add(name)
            for name, resource in self._composite.response.requirements.resources:
                names.add(name)
        return len(names)

    def __contains__(self, key: protobuf.TypeString) -> bool:
        if self._composite.crossplane_v1:
            if key in self._composite.request.extra_resources:
                return True
            if key in self._composite.response.requirements.extra_resources:
                return True
        else:
            if key in self._composite.request.required_resources:
                return True
            if key in self._composite.response.requirements.resources:
                return True
        return False

    def __iter__(self) -> typing.Generator[tuple[str, RequiredResources]]:
        names: set[str] = set()
        if self._composite.crossplane_v1:
            for name, resource in self._composite.request.extra_resources:
                names.add(name)
            for name, resource in self._composite.response.requirements.extra_resources:
                names.add(name)
        else:
            for name, resource in self._composite.request.required_resources:
                names.add(name)
            for name, resource in self._composite.response.requirements.resources:
                names.add(name)
        for name in sorted(names):
            yield name, self[name]


class RequiredResources:
    def __init__(
        self,
        composite: BaseComposite,
        name: protobuf.TypeString,
    ):
        self.name = name
        if composite.crossplane_v1:
            self._selector: protobuf.MapMessage = cast(
                protobuf.MapMessage,
                composite.response.requirements.extra_resources[name],
            )
            self._resources: protobuf.MapMessage = cast(
                protobuf.MapMessage, composite.request.extra_resources[name]
            )
        else:
            self._selector: protobuf.MapMessage = cast(
                protobuf.MapMessage, composite.response.requirements.resources[name]
            )
            self._resources: protobuf.MapMessage = cast(
                protobuf.MapMessage, composite.request.required_resources[name]
            )
        self._cache: dict[int, RequiredResource] = {}

    def __call__(
        self,
        kind: str | _notset = _notset,
        apiVersion: str | _notset = _notset,
        namespace: str | _notset = _notset,
        name: str | _notset = _notset,
        labels: typing.Mapping[str, str] | _notset = _notset,
    ) -> typing.Self:
        self._selector()
        if kind is not _notset:
            # Allow for apiVersion in the first arg and kind in the second arg
            if "/" in kind or kind == "v1":
                if apiVersion is not _notset:
                    self.kind = apiVersion
                apiVersion = kind
            else:
                self.kind = kind
        if apiVersion is not _notset:
            self.apiVersion = apiVersion
        if namespace is not _notset:
            self.namespace = namespace
        if name is not _notset:
            self.matchName = name
        if labels is not _notset:
            self.matchLabels = labels
        return self

    @property
    def apiVersion(self) -> protobuf.FieldMessage:
        return self._selector.api_version

    @apiVersion.setter
    def apiVersion(self, apiVersion: protobuf.TypeString):
        self._selector.api_version = apiVersion

    @property
    def kind(self) -> protobuf.FieldMessage:
        return self._selector.kind

    @kind.setter
    def kind(self, kind: protobuf.TypeString):
        self._selector.kind = kind

    @property
    def namespace(self) -> protobuf.FieldMessage:
        return self._selector.namespace

    @namespace.setter
    def namespace(self, namespace: protobuf.TypeString):
        self._selector.namespace = namespace

    @property
    def matchName(self) -> protobuf.FieldMessage:
        return self._selector.match_name

    @matchName.setter
    def matchName(self, name: protobuf.TypeString):
        self._selector.match_name = name

    @property
    def matchLabels(self) -> protobuf.MapMessage:
        return self._selector.match_labels.labels

    @matchLabels.setter
    def matchLabels(
        self,
        labels: typing.Mapping[str, str] | protobuf.Value | None,
    ):
        self._selector.match_labels.labels()
        if labels:
            for entry in labels:
                if isinstance(entry, str):
                    self._selector.match_labels.labels[entry] = labels[entry]
                elif isinstance(entry, (list, tuple)):
                    self._selector.match_labels.labels[entry[0]] = entry[1]

    def __getitem__(self, ix: int) -> RequiredResource:
        resource = self._cache.get(ix)
        if not resource:
            resource = RequiredResource(self.name, ix, self._resources.items[ix])
            self._cache[ix] = resource
        return resource

    def __bool__(self) -> bool:
        return bool(len(self))

    def __len__(self) -> int:
        return len(self._resources.items)

    def __iter__(self) -> typing.Generator[RequiredResource]:
        for ix in range(len(self)):
            yield self[ix]


class RequiredResource:
    def __init__(
        self,
        name: protobuf.TypeString,
        ix: int,
        resource: protobuf.Message,
    ):
        self.name: protobuf.TypeString = name
        self.ix: int = ix
        self.observed: protobuf.Value = cast(protobuf.Value, resource.resource)
        self.apiVersion: protobuf.Value = self.observed.apiVersion
        self.kind: protobuf.Value = self.observed.kind
        self.metadata: protobuf.Value = self.observed.metadata
        self.spec: protobuf.Value = self.observed.spec
        self.type: protobuf.Value = self.observed.type
        self.data: protobuf.Value = self.observed.data
        self.status: protobuf.Value = self.observed.status
        self.conditions: Conditions = Conditions(resource)
        self.connection: protobuf.MapMessage = self.observed.connection_details

    def __bool__(self) -> bool:
        return bool(self.observed)


class Schemas:
    def __init__(self, composite: BaseComposite):
        self._composite: BaseComposite = composite
        self._cache: dict[protobuf.TypeString, Schema] = {}

    def __getattr__(self, key: protobuf.TypeString) -> Schema:
        return self[key]

    def __getitem__(self, key: protobuf.TypeString) -> Schema:
        schema: Schema | None = self._cache.get(key)
        if not schema:
            schema = Schema(self._composite, key)
            self._cache[key] = schema
        return schema

    def __bool__(self) -> bool:
        return bool(len(self))

    def __len__(self) -> int:
        names = set()
        for name, schema in self._composite.request.required_schemas:
            names.add(name)
        for name, selector in self._composite.response.requirements.schemas:
            names.add(name)
        return len(names)

    def __contains__(self, key: protobuf.TypeString) -> bool:
        if key in self._composite.request.required_schemas:
            return True
        return key in self._composite.response.requirements.schemas

    def __iter__(self) -> typing.Generator[tuple[str, Schema]]:
        names: set[str] = set()
        for name, schema in self._composite.request.required_schemas:
            names.add(name)
        for name, selector in self._composite.response.requirements.schemas:
            names.add(name)
        for name in sorted(names):
            yield name, self[name]


class Schema:
    def __init__(
        self,
        composite: BaseComposite,
        name: protobuf.TypeString,
    ):
        self.name: protobuf.TypeString = name
        self._selector: protobuf.Message = cast(
            protobuf.Message, composite.response.requirements.schemas[name]
        )
        self._schema: protobuf.Value = cast(
            protobuf.Value, composite.request.required_schemas[name].openapi_v3
        )

    def __call__(
        self, kind: str | _notset = _notset, apiVersion: str | _notset = _notset
    ) -> typing.Self:
        self._selector()
        if kind is not _notset:
            # Allow for apiVersion in the first arg and kind in the second arg
            if "/" in kind or kind == "v1":
                if apiVersion is not _notset:
                    self.kind = apiVersion
                apiVersion = kind
            else:
                self.kind = kind
        if apiVersion is not _notset:
            self.apiVersion = apiVersion
        return self

    @property
    def apiVersion(self) -> protobuf.FieldMessage:
        return cast(protobuf.FieldMessage, self._selector.api_version)

    @apiVersion.setter
    def apiVersion(self, apiVersion: protobuf.TypeString) -> None:
        self._selector.api_version = apiVersion

    @property
    def kind(self) -> protobuf.FieldMessage:
        return cast(protobuf.FieldMessage, self._selector.kind)

    @kind.setter
    def kind(self, kind: protobuf.TypeString) -> None:
        self._selector.kind = kind

    def __enter__(self) -> typing.Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None:
        pass

    def __aenter__(self) -> typing.Self:
        return self

    def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: types.TracebackType | None,
    ):
        pass

    def __getattr__(self, key: protobuf.TypeString) -> protobuf.Value:
        return self[key]

    def __getitem__(self, key: protobuf.TypeString) -> protobuf.Value:
        return self._schema[key]

    def __bool__(self) -> bool:
        return bool(len(self))

    def __len__(self) -> int:
        return len(self._schema)

    def __contains__(self, item: protobuf.TypeString) -> bool:
        return item in self._schema

    def __iter__(self) -> typing.Generator[str, protobuf.Value]:
        yield from self._schema

    def __hash__(self) -> int:
        return hash(self._schema)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Schema):
            other = other._schema
        return self._schema == other

    def __str__(self) -> str:
        return str(self._schema)

    def __format__(self, spec: str = "yaml") -> str:
        return format(self._schema, spec)


class Conditions:
    def __init__(
        self, observed: protobuf.Message, response: protobuf.Message | None = None
    ):
        self._observed: protobuf.Message = observed
        self._response: protobuf.Message | None = response

    def __getattr__(self, type: str) -> Condition:
        return self[type]

    def __getitem__(self, type: str) -> Condition:
        return Condition(self, type)

    def __bool__(self) -> bool:
        if self._response is not None and len(self._response.conditions):
            return True
        return bool(len(self))

    def __len__(self) -> int:
        return len(self._types())

    def __iter__(self) -> typing.Generator[Condition]:
        for type in self._types():
            yield self[type]

    def _types(self):
        types = set()
        if self._response is not None:
            for condition in self._response.conditions:
                if condition.type:
                    types.add(str(condition.type))
        for condition in self._observed.resource.status.conditions:
            if condition.type:
                types.add(str(condition.type))
        return sorted(types)


class Condition(protobuf.ProtobufValue):
    def __init__(self, conditions: Conditions, type: str):
        self._conditions: Conditions = conditions
        self.type: str = type

    @property
    def _protobuf_value(self) -> dict[str, protobuf.FieldMessage | str]:
        status = self.status
        value: dict[str, protobuf.FieldMessage | str] = {
            "type": self.type,
            "status": "Unknown" if status is None else str(status),
            "reason": self.reason or "",
            "message": self.message or "",
        }
        time = self.lastTransitionTime
        if time:
            value["lastTransitionTime"] = time.isoformat().replace("+00:00", "Z")
        return value

    def __call__(
        self,
        reason: protobuf.TypeString | _notset = _notset,
        message: protobuf.TypeString | _notset = _notset,
        status: bool | protobuf.Value | None | _notset = _notset,
        claim: bool | protobuf.Value | None | _notset = _notset,
    ) -> typing.Self:
        self._ensure_condition()
        if reason is not _notset:
            self.reason = reason
        if message is not _notset:
            self.message = message
        if status is not _notset:
            self.status = status
        if claim is not _notset:
            self.claim = claim
        return self

    @property
    def status(self) -> bool | None:
        condition = self._get_condition()
        if condition:
            if condition.status in (fnv1.Status.STATUS_CONDITION_TRUE, "True", True):
                return True
            if condition.status in (fnv1.Status.STATUS_CONDITION_FALSE, "False", False):
                return False
        return None

    @status.setter
    def status(self, status: bool | protobuf.Value | None) -> None:
        condition = self._ensure_condition()
        if status:
            condition.status = fnv1.Status.STATUS_CONDITION_TRUE
        elif status == None:
            condition.status = fnv1.Status.STATUS_CONDITION_UNKNOWN
        elif isinstance(status, protobuf.Value) and status._isUnknown:
            condition.status = fnv1.Status.STATUS_CONDITION_UNSPECIFIED
        else:
            condition.status = fnv1.Status.STATUS_CONDITION_FALSE

    @property
    def reason(self) -> protobuf.FieldMessage | None:
        condition = self._get_condition()
        if condition:
            return cast(protobuf.FieldMessage, condition.reason)
        return None

    @reason.setter
    def reason(self, reason: protobuf.TypeString) -> None:
        self._ensure_condition().reason = reason

    @property
    def message(self) -> protobuf.FieldMessage | None:
        condition = self._get_condition()
        if condition:
            return cast(protobuf.FieldMessage, condition.message)
        return None

    @message.setter
    def message(self, message: protobuf.TypeString) -> None:
        self._ensure_condition().message = message

    @property
    def lastTransitionTime(self) -> datetime.datetime | None:
        for observed in self._conditions._observed.resource.status.conditions:
            if observed.type == self.type:
                time = observed.lastTransitionTime
                if time:
                    return datetime.datetime.fromisoformat(str(time))
        return None

    @property
    def claim(self) -> bool:
        condition = self._get_condition()
        return (
            bool(condition)
            and condition.target == fnv1.Target.TARGET_COMPOSITE_AND_CLAIM
        )

    @claim.setter
    def claim(self, claim: bool | protobuf.Value | None) -> None:
        condition = self._ensure_condition()
        if claim:
            condition.target = fnv1.Target.TARGET_COMPOSITE_AND_CLAIM
        elif claim == None or (isinstance(claim, protobuf.Value) and claim._isUnknown):
            condition.target = fnv1.Target.TARGET_UNSPECIFIED
        else:
            condition.target = fnv1.Target.TARGET_COMPOSITE

    def _get_condition(self, ensure: bool = False) -> protobuf.Message | None:
        if self._conditions._response is not None:
            for condition in self._conditions._response.conditions:
                if condition.type == self.type:
                    return condition
        if not ensure:
            for observed in self._conditions._observed.resource.status.conditions:
                if observed.type == self.type:
                    return observed
        return None

    def _ensure_condition(self) -> protobuf.Message:
        condition = self._get_condition(True)
        if condition:
            return condition
        if self._conditions._response is None:
            raise ValueError("Condition is read only")
        condition = fnv1.Condition()
        condition.type = self.type
        self._conditions._response.conditions.append(condition)
        return cast(protobuf.Message, self._conditions._response.conditions[-1])


class Results:
    def __init__(self, response: protobuf.Message):
        self._results: protobuf.RepeatedMessage = cast(
            protobuf.RepeatedMessage, response.results
        )

    def info(
        self,
        reason: protobuf.TypeString | _notset = _notset,
        message: protobuf.TypeString | _notset = _notset,
        claim: bool | protobuf.Value | None | _notset = _notset,
    ) -> Result:
        self._results.append()
        result = Result(self._results[-1])
        result.info = True
        if reason is not _notset:
            result.reason = reason
        if message is not _notset:
            result.message = message
        if claim is not _notset:
            result.claim = claim
        return result

    def warning(
        self,
        reason: protobuf.TypeString | _notset = _notset,
        message: protobuf.TypeString | _notset = _notset,
        claim: bool | protobuf.Value | None | _notset = _notset,
    ) -> Result:
        self._results.append()
        result = Result(self._results[-1])
        result.warning = True
        if reason is not _notset:
            result.reason = reason
        if message is not _notset:
            result.message = message
        if claim is not _notset:
            result.claim = claim
        return result

    def fatal(
        self,
        reason: protobuf.TypeString | _notset = _notset,
        message: protobuf.TypeString | _notset = _notset,
        claim: bool | protobuf.Value | None | _notset = _notset,
    ) -> Result:
        self._results.append()
        result = Result(self._results[-1])
        result.fatal = True
        if reason is not _notset:
            result.reason = reason
        if message is not _notset:
            result.message = message
        if claim is not _notset:
            result.claim = claim
        return result

    def __bool__(self) -> bool:
        return bool(len(self))

    def __len__(self) -> int:
        return len(self._results)

    def __getitem__(self, key: int) -> Result:
        if key >= len(self._results):
            return Result()
        return Result(self._results[key])

    def __iter__(self) -> typing.Generator[Result]:
        for ix in range(len(self._results)):
            yield self[ix]


class Result:
    def __init__(self, result: protobuf.Message | None = None):
        self._result: protobuf.Message | None = result

    def __bool__(self) -> bool:
        return self._result is not None

    @property
    def info(self) -> bool:
        return (
            self._result is not None
            and self._result.severity == fnv1.Severity.SEVERITY_NORMAL
        )

    @info.setter
    def info(self, info: bool | protobuf.Value | protobuf.FieldMessage | None) -> None:
        if self._result is not None:
            if info:
                self._result.severity = fnv1.Severity.SEVERITY_NORMAL
            else:
                self._result.severity = fnv1.Severity.SEVERITY_UNSPECIFIED

    @property
    def warning(self) -> bool:
        return (
            self._result is not None
            and self._result.severity == fnv1.Severity.SEVERITY_WARNING
        )

    @warning.setter
    def warning(
        self, warning: bool | protobuf.Value | protobuf.FieldMessage | None
    ) -> None:
        if self._result is not None:
            if warning:
                self._result.severity = fnv1.Severity.SEVERITY_WARNING
            else:
                self._result.severity = fnv1.Severity.SEVERITY_NORMAL

    @property
    def fatal(self) -> bool:
        return (
            self._result is not None
            and self._result.severity == fnv1.Severity.SEVERITY_FATAL
        )

    @fatal.setter
    def fatal(
        self, fatal: bool | protobuf.Value | protobuf.FieldMessage | None
    ) -> None:
        if self._result is not None:
            if fatal:
                self._result.severity = fnv1.Severity.SEVERITY_FATAL
            else:
                self._result.severity = fnv1.Severity.SEVERITY_NORMAL

    @property
    def reason(self) -> protobuf.FieldMessage | None:
        return (
            cast(protobuf.FieldMessage, self._result.reason)
            if self._result is not None
            else None
        )

    @reason.setter
    def reason(self, reason: protobuf.TypeString):
        if self._result is not None:
            self._result.reason = reason

    @property
    def message(self) -> protobuf.FieldMessage | None:
        return (
            cast(protobuf.FieldMessage, self._result.message)
            if self._result is not None
            else None
        )

    @message.setter
    def message(self, message: protobuf.TypeString):
        if self._result is not None:
            self._result.message = message

    @property
    def claim(self) -> bool:
        return (
            self._result is not None
            and self._result.target == fnv1.Target.TARGET_COMPOSITE_AND_CLAIM
        )

    @claim.setter
    def claim(
        self, claim: bool | protobuf.Value | protobuf.FieldMessage | None
    ) -> None:
        if self._result is not None:
            if claim:
                self._result.target = fnv1.Target.TARGET_COMPOSITE_AND_CLAIM
            elif claim == None or (
                isinstance(claim, protobuf.Value) and claim._isUnknown
            ):
                self._result.target = fnv1.Target.TARGET_UNSPECIFIED
            else:
                self._result.target = fnv1.Target.TARGET_COMPOSITE


class _Connection:
    def __init__(self, composite: BaseComposite):
        self._composite: BaseComposite = composite

    @property
    def _resource_name(self) -> protobuf.Value | str:
        return self._composite.connectionSecret.resourceName or "connection-secret"

    @property
    def observed(self) -> protobuf.MapMessage:
        return cast(
            protobuf.MapMessage,
            self._composite.request.observed.composite.connection_details,
        )

    def __getattr__(self, key: protobuf.TypeString) -> protobuf.FieldMessage:
        return self[key]

    def __getitem__(self, key: protobuf.TypeString) -> protobuf.FieldMessage:
        return cast(
            protobuf.FieldMessage,
            self._composite.response.desired.composite.connection_details[key],
        )

    def __bool__(self) -> bool:
        return bool(len(self))

    def __len__(self) -> int:
        return len(self._composite.response.desired.composite.connection_details)

    def __contains__(self, key: protobuf.TypeString) -> bool:
        return key in self._composite.response.desired.composite.connection_details

    def __iter__(self) -> typing.Generator[tuple[str, protobuf.FieldMessage]]:
        yield from self._composite.response.desired.composite.connection_details

    def __str__(self) -> str:
        return format(self)

    def __format__(self, spec: str = "yaml") -> str:
        return format(
            self._composite.response.desired.composite.connection_details, spec
        )

    def __call__(self, **kwargs):
        self._composite.response.desired.composite.connection_details(**kwargs)
        if self._composite.crossplane_v1:
            return
        del self._composite.resources[self._resource_name]
        for key, value in kwargs.items():
            self[key] = value

    def __setattr__(
        self,
        key: protobuf.TypeString,
        value: protobuf.TypeString,
    ) -> None:
        if key == "_composite":
            self.__dict__[str(key)] = value
        else:
            self[key] = value

    def __setitem__(
        self,
        key: protobuf.TypeString,
        value: protobuf.TypeString,
    ) -> None:
        if not isinstance(value, str):
            if value is None:
                return
            if isinstance(value, (protobuf.FieldMessage, protobuf.Value)) and not value:
                return
            value = str(value)
        self._composite.response.desired.composite.connection_details[key] = value
        if self._composite.crossplane_v1 or not self._composite.connectionSecret.name:
            return
        if self._resource_name in self._composite.resources:
            secret = self._composite.resources[self._resource_name]
        else:
            secret = self._composite.resources[self._resource_name]("v1", "Secret")
            if self._composite.connectionSecret.name and len(
                self._composite.connectionSecret.name
            ):
                secret.metadata.name = self._composite.connectionSecret.name
            if not self._composite.metadata.namespace:
                if not self._composite.connectionSecret.namespace:
                    self._composite.results.fatal(
                        "ConnectionNoNamespace",
                        "Cluster scoped XR must specify connection secret namespace",
                    )
                    return
                secret.metadata.namespace = self._composite.connectionSecret.namespace
            secret.type = "connection.crossplane.io/v1alpha1"
        secret.data[key] = protobuf.B64Encode(value)

    def __delattr__(self, key: protobuf.TypeString):
        del self[key]

    def __delitem__(self, key: protobuf.TypeString):
        del self._composite.response.desired.composite.connection_details[key]
        if self._composite.crossplane_v1:
            return
        if self._resource_name in self._composite.resources:
            del self._composite.resources[self._resource_name].data[key]
            if not len(self._composite.resources[self._resource_name].data):
                del self._composite.resources[self._resource_name]
