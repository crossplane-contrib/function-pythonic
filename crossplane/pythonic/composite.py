
import datetime
from google.protobuf.duration_pb2 import Duration
from crossplane.function.proto.v1 import run_function_pb2 as fnv1

from . import protobuf


_notset = object()


class ConnectionSecret:
    def __get__(self, composite, objtype=None):
        if composite.crossplane_v1:
            return composite.spec.writeConnectionSecretToRef
        secret = getattr(composite, '_connectionSecret', None)
        if not secret:
            secret = protobuf.Map()
            for key, value in composite.request.input.writeConnectionSecretToRef:
                secret[key] = value
            composite._connectionSecret = secret
        return secret

    def __set__(self, composite, values):
        if composite.crossplane_v1:
            if values != composite.spec.writeConnectionSecretToRef:
                raise NotImplementedError('Connection Secret cannot be set in Crossplane V1')
            return
        secret = protobuf.Map()
        for key, value in values:
            secret[key] = value
        composite._connectionSecret = secret


class Connection:
    def __get__(self, composite, objtype=None):
        connection = getattr(composite, '_connection', None)
        if not connection:
            connection = _Connection(composite)
            composite._connection = connection
        return connection

    def __set__(self, composite, values):
        connection = self.__get__(composite)
        coneection()
        for key, value in values:
            connection[key] = value


class TTL:
    def __get__(self, composite, objtype=None):
        if composite.response.meta.ttl.nanos:
            return float(composite.response.meta.ttl.seconds) + (float(composite.response.meta.ttl.nanos) / 1000000000.0)
        return int(composite.response.meta.ttl.seconds)

    def __set__(self, composite, ttl):
        if isinstance(ttl, int):
            composite.response.meta.ttl.seconds = ttl
            composite.response.meta.ttl.nanos = 0
        elif isinstance(ttl, float):
            composite.response.meta.ttl.seconds = int(ttl)
            if ttl.is_integer():
                composite.response.meta.ttl.nanos = 0
            else:
                composite.response.meta.ttl.nanos = int((ttl - int(composite.response.meta.ttl.seconds)) * 1000000000)
        else:
            raise ValueError('ttl must be an int or float')


class Ready:
    def __get__(self, composite, objtype=None):
        ready = composite.desired._parent.ready
        if ready == fnv1.Ready.READY_TRUE:
            return True
        if ready == fnv1.Ready.READY_FALSE:
            return False
        return None

    def __set__(self, composite, ready):
        if ready:
            ready = fnv1.Ready.READY_TRUE
        elif ready == None or (isinstance(ready, protobuf.Value) and ready._isUnknown):
            ready = fnv1.Ready.READY_UNSPECIFIED
        else:
            ready = fnv1.Ready.READY_FALSE
        composite.desired._parent.ready = ready


class BaseComposite:
    def __init__(self, crossplane_v1, request, single_use, logger):
        self.crossplane_v1 = crossplane_v1
        self.request = protobuf.Message(None, 'request', request.DESCRIPTOR, request, 'Function Request')
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
        self.response = protobuf.Message(None, 'response', response.DESCRIPTOR, response)
        self.logger = logger
        if single_use:
            self.parameters = self.request.observed.composite.resource.spec.parameters
        else:
            self.parameters = self.request.input.parameters
        self.credentials = Credentials(self.request)
        self.context = self.response.context
        self.environment = self.context['apiextensions.crossplane.io/environment']
        self.requireds = Requireds(self)
        self.resources = Resources(self)
        self.unknownsFatal = True
        self.autoReady = True
        self.usages = False

        observed = self.request.observed.composite
        desired = self.response.desired.composite
        self.observed = observed.resource
        self.desired = desired.resource
        self.apiVersion = self.observed.apiVersion
        self.kind = self.observed.kind
        self.metadata = self.observed.metadata
        self.spec = self.observed.spec
        self.status = self.desired.status
        self.conditions = Conditions(observed, self.response)
        self.results = Results(self.response)
        self.events = Results(self.response) # Deprecated, use self.results

    ttl = TTL()
    connectionSecret = ConnectionSecret()
    connection = Connection()
    ready = Ready()

    async def compose(self):
        raise NotImplementedError()


class Credentials:
    def __init__(self, request):
        self.__dict__['_request'] = request

    def __getattr__(self, key):
        return self[key]

    def __getitem__(self, key):
        return Credential(self._request.credentials[key])

    def __bool__(self):
        return bool(self._request.credentials)

    def __len__(self):
        return len(self._request.credentials)

    def __contains__(self, key):
        return key in self._request.credentials

    def __iter__(self):
        for key, resource in self._request.credentials:
            yield key, self[key]


class Credential:
    def __init__(self, credential):
        self.__dict__['_credential'] = credential

    def __getattr__(self, key):
        return self[key]

    def __getitem__(self, key):
        return self._credential.credential_data.data[key]

    def __bool__(self):
        return bool(self._credential.credential_data.data)

    def __len__(self):
        return len(self._credential.credential_data.data)

    def __contains__(self, key):
        return key in self._credential.credential_data.data

    def __iter__(self):
        for key, resource in self._credential.credential_data.data:
            yield key, self[key]


class Resources:
    def __init__(self, composite):
        self.__dict__['_composite'] = composite
        self.__dict__['_cache'] = {}

    def __getattr__(self, key):
        return self[key]

    def __getitem__(self, key):
        resource = self._cache.get(key)
        if not resource:
            resource = Resource(self._composite, key)
            self._cache[key] = resource
        return resource

    def __bool__(self):
        return bool(self._composite.response.desired.resources)

    def __len__(self):
        return len(self._composite.response.desired.resources)

    def __contains__(self, key):
        return key in self._composite.response.desired.resources

    def __iter__(self):
        for name, resource in self._composite.response.desired.resources:
            yield name, self[name]

    def __setattr__(self, key, resource):
        self[key] = resource

    def __setitem__(self, key, resource):
        self._composite.response.desired.resources[key].resource = resource
        self._cache.pop(key, None)

    def __delattr__(self, key):
        del self[key]

    def __delitem__(self, key):
        if key in self._composite.response.desired.resources:
            del self._composite.response.desired.resources[key]
        self._cache.pop(key, None)


class Resource:
    def __init__(self, composite, name):
        self.name = name
        observed = composite.request.observed.resources[name]
        desired = composite.response.desired.resources[name]
        self.observed = observed.resource
        self.desired = desired.resource
        self.conditions = Conditions(observed)
        self.connection = observed.connection_details
        self.unknownsFatal = None
        self.autoReady = None
        self.usages = None

    def __call__(self, apiVersion=_notset, kind=_notset, namespace=_notset, name=_notset):
        self.desired()
        if apiVersion != _notset:
            self.apiVersion = apiVersion
        if kind != _notset:
            self.kind = kind
        if namespace != _notset:
            self.metadata.namespace = namespace
        if name != _notset:
            self.metadata.name = name
        return self

    @property
    def apiVersion(self):
        return self.desired.apiVersion

    @apiVersion.setter
    def apiVersion(self, apiVersion):
        self.desired.apiVersion = apiVersion

    @property
    def kind(self):
        return self.desired.kind

    @kind.setter
    def kind(self, kind):
        self.desired.kind = kind

    @property
    def externalName(self):
        if 'crossplane.io/external-name' in self.metadata.annotations:
            return self.metadata.annotations['crossplane.io/external-name']
        return self.observed.metadata.annotations['crossplane.io/external-name']

    @externalName.setter
    def externalName(self, name):
        self.metadata.annotations['crossplane.io/external-name'] = name

    @property
    def metadata(self):
        return self.desired.metadata

    @metadata.setter
    def metadata(self, metadata):
        self.desired.metadata = metadata

    @property
    def spec(self):
        return self.desired.spec

    @spec.setter
    def spec(self, spec):
        self.desired.spec = spec

    @property
    def type(self):
        return self.desired.type

    @type.setter
    def type(self, type):
        self.desired.type = type

    @property
    def data(self):
        return self.desired.data

    @data.setter
    def data(self, data):
        self.desired.data = data

    @property
    def status(self):
        return self.observed.status

    @property
    def ready(self):
        ready = self.desired._parent.ready
        if ready == fnv1.Ready.READY_TRUE:
            return True
        if ready == fnv1.Ready.READY_FALSE:
            return False
        return None

    @ready.setter
    def ready(self, ready):
        if ready:
            ready = fnv1.Ready.READY_TRUE
        elif ready == None or (isinstance(ready, protobuf.Value) and ready._isUnknown):
            ready = fnv1.Ready.READY_UNSPECIFIED
        else:
            ready = fnv1.Ready.READY_FALSE
        self.desired._parent.ready = ready


class Requireds:
    def __init__(self, composite):
        self._composite = composite
        self._cache = {}

    def __getattr__(self, key):
        return self[key]

    def __getitem__(self, key):
        required = self._cache.get(key)
        if not required:
            required = RequiredResources(self._composite, key)
            self._cache[key] = required
        return required

    def __bool__(self):
        return bool(len(self))

    def __len__(self):
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

    def __contains__(self, key):
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

    def __iter__(self):
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
        for name in sorted(names):
            yield name, self[name]


class RequiredResources:
    def __init__(self, composite, name):
        self.name = name
        if composite.crossplane_v1:
            self._selector = composite.response.requirements.extra_resources[name]
            self._resources = composite.request.extra_resources[name]
        else:
            self._selector = composite.response.requirements.resources[name]
            self._resources = composite.request.required_resources[name]
        self._cache = {}

    def __call__(self, apiVersion=_notset, kind=_notset, namespace=_notset, name=_notset, labels=_notset):
        self._selector()
        if apiVersion != _notset:
            self.apiVersion = apiVersion
        if kind != _notset:
            self.kind = kind
        if namespace != _notset:
            self.namespace = namespace
        if name != _notset:
            self.matchName = name
        if labels != _notset:
            self.matchLabels = labels
        return self

    @property
    def apiVersion(self):
        return self._selector.api_version

    @apiVersion.setter
    def apiVersion(self, apiVersion):
        self._selector.api_version = apiVersion

    @property
    def kind(self):
        return self._selector.kind

    @kind.setter
    def kind(self, kind):
        self._selector.kind = kind

    @property
    def namespace(self):
        return self._selector.namespace

    @namespace.setter
    def namespace(self, namespace):
        self._selector.namespace = namespace

    @property
    def matchName(self):
        return self._selector.match_name

    @matchName.setter
    def matchName(self, name):
        self._selector.match_name = name

    @property
    def matchLabels(self):
        return self._selector.match_labels.labels

    @matchLabels.setter
    def matchLabels(self, labels):
        self._selector.match_labels.labels()
        if labels:
            for entry in labels:
                if isinstance(entry, str):
                    self._selector.match_labels.labels[entry] = labels[entry]
                elif isinstance(entry, (list, tuple)):
                    self._selector.match_labels.labels[entry[0]] = entry[1]

    def __getitem__(self, ix):
        resource = self._cache.get(ix)
        if not resource:
            resource = RequiredResource(self.name, ix, self._resources.items[ix])
            self._cache[ix] = resource
        return resource

    def __bool__(self):
        return bool(self._resources.items)

    def __len__(self):
        return len(self._resources.items)

    def __iter__(self):
        for ix in range(len(self)):
            yield self[ix]


class RequiredResource:
    def __init__(self, name, ix, resource):
        self.name = name
        self.ix = ix
        self.observed = resource.resource
        self.apiVersion = self.observed.apiVersion
        self.kind = self.observed.kind
        self.metadata = self.observed.metadata
        self.spec = self.observed.spec
        self.type = self.observed.type
        self.data = self.observed.data
        self.status = self.observed.status
        self.conditions = Conditions(resource)
        self.connection = self.observed.connection_details

    def __bool__(self):
        return bool(self.observed)


class Conditions:
    def __init__(self, observed, response=None):
        self._observed = observed
        self._response = response

    def __getattr__(self, type):
        return self[type]

    def __getitem__(self, type):
        return Condition(self, type)

    def __bool__(self):
        if self._response is not None:
            if self._response.conditions:
                return True
        if self._observed.resource.status.conditions:
            return True
        return False

    def __len__(self):
        return len(self._types())

    def __iter__(self):
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
    def __init__(self, conditions, type):
        self._conditions = conditions
        self.type = type

    @property
    def _protobuf_value(self):
        status = self.status
        value = {
            'type': self.type,
            'status': 'Unknown' if status is None else str(status),
            'reason': self.reason or '',
            'message': self.message or '',
        }
        time = self.lastTransitionTime
        if time:
            value['lastTransitionTime'] = time.isoformat().replace('+00:00', 'Z')
        return value

    def __call__(self, reason=_notset, message=_notset, status=_notset, claim=_notset):
        self._find_condition(True)
        if reason != _notset:
            self.reason = reason
        if message != _notset:
            self.message = message
        if status != _notset:
            self.status = status
        if claim != _notset:
            self.claim = claim
        return self

    @property
    def status(self):
        condition = self._find_condition()
        if condition:
            if condition.status in (fnv1.Status.STATUS_CONDITION_TRUE, 'True', True):
                return True
            if condition.status in (fnv1.Status.STATUS_CONDITION_FALSE, 'False', False):
                return False
        return None

    @status.setter
    def status(self, status):
        condition = self._find_condition(True)
        if status:
            condition.status = fnv1.Status.STATUS_CONDITION_TRUE
        elif status == None:
            condition.status = fnv1.Status.STATUS_CONDITION_UNKNOWN
        elif isinstance(status, protobuf.Value) and status._isUnknown:
            condition.status = fnv1.Status.STATUS_CONDITION_UNSPECIFIED
        else:
            condition.status = fnv1.Status.STATUS_CONDITION_FALSE


    @property
    def reason(self):
        condition = self._find_condition()
        if condition:
            return condition.reason
        return None

    @reason.setter
    def reason(self, reason):
        self._find_condition(True).reason = reason

    @property
    def message(self):
        condition = self._find_condition()
        if condition:
            return condition.message
        return None

    @message.setter
    def message(self, message):
        self._find_condition(True).message = message

    @property
    def lastTransitionTime(self):
        for observed in self._conditions._observed.resource.status.conditions:
            if observed.type == self.type:
                time = observed.lastTransitionTime
                if time:
                    return datetime.datetime.fromisoformat(str(time))
        return None

    @property
    def claim(self):
        condition = self._find_condition()
        return condition and condition.target == fnv1.Target.TARGET_COMPOSITE_AND_CLAIM

    @claim.setter
    def claim(self, claim):
        condition = self._find_condition(True)
        if claim:
            condition.target = fnv1.Target.TARGET_COMPOSITE_AND_CLAIM
        elif claim == None or (isinstance(claim, protobuf.Value) and claim._isUnknown):
            condition.target = fnv1.Target.TARGET_UNSPECIFIED
        else:
            condition.target = fnv1.Target.TARGET_COMPOSITE

    def _find_condition(self, create=False):
        if self._conditions._response is not None:
            for condition in self._conditions._response.conditions:
                if condition.type == self.type:
                    return condition
        if not create:
            for observed in self._conditions._observed.resource.status.conditions:
                if observed.type == self.type:
                    return observed
            return None
        if self._conditions._response is None:
            raise ValueError('Condition is read only')
        condition = fnv1.Condition()
        condition.type = self.type
        return self._conditions._response.conditions.append(condition)


class Results:
    def __init__(self, response):
        self._results = response.results

    def info(self, reason=_notset, message=_notset, claim=_notset):
        result = Result(self._results.append())
        result.info = True
        if reason != _notset:
            result.reason = reason
        if message != _notset:
            result.message = message
        if claim != _notset:
            result.claim = claim
        return result

    def warning(self, reason=_notset, message=_notset, claim=_notset):
        result = Result(self._results.append())
        result.warning = True
        if reason != _notset:
            result.reason = reason
        if message != _notset:
            result.message = message
        if claim != _notset:
            result.claim = claim
        return result

    def fatal(self, reason=_notset, message=_notset, claim=_notset):
        result = Result(self._results.append())
        result.fatal = True
        if reason != _notset:
            result.reason = reason
        if message != _notset:
            result.message = message
        if claim != _notset:
            result.claim = claim
        return result

    def __bool__(self):
        return len(self) > 0

    def __len__(self):
        len(self._results)

    def __getitem__(self, key):
        if key >= len(self._results):
            return Result()
        return Result(self._results[key])

    def __iter__(self):
        for ix in range(len(self._results)):
            yield self[ix]


class Result:
    def __init__(self, result=None):
        self._result = result

    def __bool__(self):
        return self._result is not None

    @property
    def info(self):
        return bool(self) and self._result.severity == fnv1.Severity.SEVERITY_NORMAL

    @info.setter
    def info(self, info):
        if bool(self):
            if info:
                self._result.severity = fnv1.Severity.SEVERITY_NORMAL
            else:
                self._result.severity = fnv1.Severity.SEVERITY_UNSPECIFIED

    @property
    def warning(self):
        return bool(self) and self._result.severity == fnv1.Severity.SEVERITY_WARNING

    @warning.setter
    def warning(self, warning):
        if bool(self):
            if warning:
                self._result.severity = fnv1.Severity.SEVERITY_WARNING
            else:
                self._result.severity = fnv1.Severity.SEVERITY_NORMAL

    @property
    def fatal(self):
        return bool(self) and self._result.severity == fnv1.Severity.SEVERITY_FATAL

    @fatal.setter
    def fatal(self, fatal):
        if bool(self):
            if fatal:
                self._result.severity = fnv1.Severity.SEVERITY_FATAL
            else:
                self._result.severity = fnv1.Severity.SEVERITY_NORMAL

    @property
    def reason(self):
        return self._result.reason if bool(self) else None

    @reason.setter
    def reason(self, reason):
        if bool(self):
            self._result.reason = reason

    @property
    def message(self):
        return self._result.message if bool(self) else None

    @message.setter
    def message(self, message):
        if bool(self):
            self._result.message = message

    @property
    def claim(self):
        return bool(self) and self._result == fnv1.Target.TARGET_COMPOSITE_AND_CLAIM

    @claim.setter
    def claim(self, claim):
        if bool(self):
            if claim:
                self._result.target = fnv1.Target.TARGET_COMPOSITE_AND_CLAIM
            elif claim == None or (isinstance(claim, protobuf.Value) and claim._isUnknown):
                self._result.target = fnv1.Target.TARGET_UNSPECIFIED
            else:
                self._result.target = fnv1.Target.TARGET_COMPOSITE


class _Connection:
    def __init__(self, composite):
        self._set_attribute('_composite', composite)

    def _set_attribute(self, key, value):
        self.__dict__[key] = value

    @property
    def _resource_name(self):
        return self._composite.connectionSecret.resourceName or 'connection-secret'

    @property
    def observed(self):
        if self._composite.crossplane_v1:
            return self._composite.response.observed.composite.connection_details
        data = protobuf.Map()
        for key, value in self._composite.resources[self._resource_name].observed.data:
            data[key] = protobuf.B64Decode(value)        
        return data

    def __getattr__(self, key):
        return self[key]

    def __getitem__(self, key):
        if self._composite.crossplane_v1:
            return self._composite.response.desired.composite.connection_details[key]
        value = self._composite.resources[self._resource_name].data[key]
        if value:
            value = protobuf.B64Decode(value)
        return value

    def __bool__(self):
        if self._composite.crossplane_v1:
            return bool(self._composite.response.desired.composite.connection_details)
        return bool(self._composite.resources[self._resource_name].data)

    def __len__(self):
        if self._composite.crossplane_v1:
            return len(self._composite.response.desired.composite.connection_details)
        return len(self._composite.resources[self._resource_name].data)

    def __contains__(self, key):
        if self._composite.crossplane_v1:
            return key in self._composite.response.desired.composite.connection_details

    def __iter__(self):
        keys = set()
        if self._composite.crossplane_v1:
            for key, value in self._composite.response.desired.composite.connection_details:
                yield key, value
        for key, value in self._composite.resources[self._resource_name].data:
            yield key, protobuf.B64Decode(value)

    def __str__(self):
        return format(self)

    def __format__(self, spec='yaml'):
        if self._composite.crossplane_v1:
            return format(self._composite.response.desired.composite.connection_details, spec)
        data = protobuf.Map()
        for key, value in self._composite.resources[self._resource_name].data:
            data[key] = protobuf.B64Decode(value)
        return format(data, spec)

    def __call__(self, **kwargs):
        if self._composite_v1:
            self._composite.response.desired.composite.connection_details(**kwargs)
            return
        del self._composite.resources[self._resource_name]
        for key, value in kwargs:
            self[key] = value

    def __setattr__(self, key, value):
        self[key] = value

    def __setitem__(self, key, value):
        if not isinstance(value, str):
            if value is None:
                return
            if isinstance(value, (protobuf.FieldMessage, protobuf.Value)):
                if not value:
                    return
            value = str(value)
        if self._composite.crossplane_v1:
            self._composite.response.desired.composite.connection_details[key] = value
            return
        #if not self._composite.connectionSecret.name:
        #    return
        if self._resource_name in self._composite.resources:
            secret = self._composite.resources[self._resource_name]
        else:
            secret = self._composite.resources[self._resource_name]('v1', 'Secret')
            print(bool(self._composite.connectionSecret.name), len(self._composite.connectionSecret.name))
            if self._composite.connectionSecret.name and len(self._composite.connectionSecret.name):
                secret.metadata.name = self._composite.connectionSecret.name
            if not self._composite.metadata.namespace:
                if not self._composite.connectionSecret.namespace:
                    self._composite.results.fatal('ConnectionNoNamespace', 'Cluster scoped XR must specify connection secret namespace')
                    return
                secret.metadata.namespace = self._composite.connectionSecret.namespace
            secret.type = 'connection.crossplane.io/v1alpha1'
        secret.data[key] = protobuf.B64Encode(value)

    def __delattr__(self, key):
        del self[key]

    def __delitem__(self, key):
        if self._composite.crossplane_v1:
            del self._composite.response.desired.composite.connection_details[key]
            return
        if self._resource_name in self._composite.resources:
            del self._composite.resources[self._resource_name].data[key]
            if not len(self._composite.resources[self._resource_name].data):
                del self._composite.resources[self._resource_name]
