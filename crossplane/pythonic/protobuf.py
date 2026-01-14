##################################################################################
#
# Pythonic class wrappers around protobuf classes that enables traversing
# and modifying the protobuf message structure much like one can in JavaScript.
# For example, to get a region value from the composite's spec:
#
#   region = request.observed.composite.resource.spec.region
#
# If any item in the path to the field does not exist an "Unknown" object is returned.
# To set a field in the composite status:
#
#   response.desired.composite.resource.status.homepage.url = 'https://for.example.com'
#
# Here all items in the path to the field that do not exist will be created.
#
##################################################################################

import base64
import datetime
import google.protobuf.struct_pb2
import json
import sys
import yaml

_Unknown = object()
append = sys.maxsize


def Map(**kwargs):
    return Value(None, None, kwargs)

def List(*args):
    return Value(None, None, args)

def Unknown():
    return Value(None, None)

def Yaml(string, readOnly=None):
    if isinstance(string, (FieldMessage, Value)):
        string = str(string)
    return Value(None, None, yaml.safe_load(string), readOnly)

def Json(string, readOnly=None):
    if isinstance(string, (FieldMessage, Value)):
        string = str(string)
    return Value(None, None, json.loads(string), readOnly)

def B64Encode(string):
    if isinstance(string, (FieldMessage, Value)):
        string = str(string)
    return base64.b64encode(string.encode('utf-8')).decode('utf-8')

def B64Decode(string):
    if isinstance(string, (FieldMessage, Value)):
        string = str(string)
    return base64.b64decode(string.encode('utf-8')).decode('utf-8')


class Message:
    def __init__(self, parent, key, descriptor, message=_Unknown, readOnly=False):
        self._set_attribute('_parent', parent)
        self._set_attribute('_key', key)
        self._set_attribute('_descriptor', descriptor)
        self._set_attribute('_message', message)
        self._set_attribute('_readOnly', readOnly)
        self._set_attribute('_cache', {})

    def _set_attribute(self, key, value):
        self.__dict__[key] = value

    def __getattr__(self, key):
        return self[key]

    def __getitem__(self, key):
        key = self._validate_key(key)
        if key in self._cache:
            return self._cache[key]
        field = self._descriptor.fields_by_name.get(key)
        if not field:
            raise AttributeError(obj=self, name=key)
        if self._message is _Unknown:
            value = _Unknown
        else:
            value = getattr(self._message, key)
        if value is _Unknown and field.has_default_value:
            value = field.default_value
        if field.is_repeated:
            if field.type == field.TYPE_MESSAGE and field.message_type.GetOptions().map_entry:
                value = MapMessage(self, key, field.message_type.fields_by_name['value'], value, self._readOnly)
            else:
                value = RepeatedMessage(self, key, field, value, self._readOnly)
        elif field.type == field.TYPE_MESSAGE:
            if field.message_type.name in ('Struct', 'ListValue'):
                value = Value(self, key, value, self._readOnly)
            else:
                value = Message(self, key, field.message_type, value, self._readOnly)
        else:
            value = FieldMessage(self, key, field.type, value)
        self._cache[key] = value
        return value

    def __bool__(self):
        return self._message is not _Unknown

    def __len__(self):
        return len(self._descriptor.fields)

    def __contains__(self, key):
        return key in self._descriptor.fields_by_name

    def __iter__(self):
        for key in sorted(self._descriptor.fields_by_name):
            yield key, self[key]

    def __hash__(self):
        if self._message is not _Unknown:
            return hash(tuple(hash(item) for item in sorted(iter(self), key=lambda item: item[0])))
        return 0

    def __eq__(self, other):
        if not isinstance(other, Message):
            return False
        if self._descriptor.full_name != other._descriptor.full_name:
            return False
        if self._message is _Unknown:
            return other._message is _Unknown
        elif other._message is _Unknown:
            return False
        if len(self) != len(other):
            return False
        for key, value in self:
            if key not in other:
                return False
            if value != other[key]:
                return False
        return True

    def __str__(self):
        return format(self)

    def __format__(self, spec='yaml'):
        return _formatObject(self, spec)

    def _fullName(self, key=None):
        if self._key is not None:
            if self._parent is not None:
                name = self._parent._fullName(self._key)
            else:
                name = str(self._key)
            if key is not None:
                if '.' in key:
                    name += f"[{key}]"
                else:
                    name += f".{key}"
            return name
        if key is not None:
            return str(key)
        return ''

    def _create_child(self, key):
        if self._readOnly:
            raise ValueError(f"{self._readOnly} is read only")
        key = self._validate_key(key)
        if self._message is _Unknown:
            self.__dict__['_message'] = self._parent._create_child(self._key)
        return getattr(self._message, key)

    def __call__(self, **kwargs):
        if self._readOnly:
            raise ValueError(f"{self._readOnly} is read only")
        if self._message is _Unknown:
            self.__dict__['_message'] = self._parent._create_child(self._key)
        self._message.Clear()
        self._cache.clear()
        for key, value in kwargs.items():
            self[key] = value
        return self

    def __setattr__(self, key, value):
        self[key] = value

    def __setitem__(self, key, value):
        if self._readOnly:
            raise ValueError(f"{self._readOnly} is read only")
        key = self._validate_key(key)
        if key not in self._descriptor.fields_by_name:
            raise AttributeError(obj=self, name=key)
        field = self._descriptor.fields_by_name[key]
        if self._message is _Unknown:
            self.__dict__['_message'] = self._parent._create_child(self._key)
        if isinstance(value, Message):
            value = value._message
        elif isinstance(value, (MapMessage, RepeatedMessage)):
            value = value._messages
        elif isinstance(value, FieldMessage):
            value = value._value
        elif isinstance(value, Value):
            value = value._raw
        if field.type == field.TYPE_BYTES and isinstance(value, str):
            value = value.encode('utf-8')
        setattr(self._message, key, value)
        self._cache.pop(key, None)

    def __delattr__(self, key):
        del self[key]

    def __delitem__(self, key):
        if self._readOnly:
            raise ValueError(f"{self._readOnly} is read only")
        key = self._validate_key(key)
        if key not in self._descriptor.fields_by_name:
            raise AttributeError(obj=self, name=key)
        if self._message is not _Unknown:
            self._message.ClearField(key)
            self._cache.pop(key, None)

    def _validate_key(self, key):
        if isinstance(key, FieldMessage):
            key = key._value
        elif isinstance(key, Value):
            key = key._raw
        if not isinstance(key, str):
            raise TypeError(f"Unexpected key type: {key.__class__}")
        return key


class MapMessage:
    def __init__(self, parent, key, field, messages=_Unknown, readOnly=False):
        self._set_attribute('_parent', parent)
        self._set_attribute('_key', key)
        self._set_attribute('_field', field)
        self._set_attribute('_messages', messages)
        self._set_attribute('_readOnly', readOnly)
        self._set_attribute('_cache', {})

    def _set_attribute(self, key, value):
        self.__dict__[key] = value

    def __getattr__(self, key):
        return self[key]

    def __getitem__(self, key):
        key = self._validate_key(key)
        if key in self._cache:
            return self._cache[key]
        if self._messages is _Unknown or key not in self._messages:
            value = _Unknown
        else:
            value = self._messages[key]
        if value is None and self._field.has_default_value:
            value = self._field.default_value
        if self._field.type == self._field.TYPE_MESSAGE:
            if self._field.message_type.name in ('Struct', 'ListValue'):
                value = Value(self, key, value, self._readOnly)
            else:
                value = Message(self, key, self._field.message_type, value, self._readOnly)
        else:
            value = FieldMessage(self, key, self._field.type, value)
        self._cache[key] = value
        return value

    def __bool__(self):
        return self._messages is not _Unknown

    def __len__(self):
        return 0 if self._messages is _Unknown else len(self._messages)

    def __contains__(self, key):
        return self._messages is not _Unknown and key in self._messages

    def __iter__(self):
        if self._messages is not _Unknown:
            for key in sorted(self._messages):
                yield key, self[key]

    def __hash__(self):
        if self._nessages is not None:
            return hash(tuple(hash(item) for item in sorted(iter(self), key=lambda item: item[0])))
        return 0

    def __eq__(self, other):
        if not isinstance(other, MapMessage):
            return False
        if self._field.type != other._field.type:
            return False
        if self._field.type == self._field.TYPE_MESSAGE:
            if self._field.message_type.full_name != other._field.message_type.full_name:
                return False
        if self._messages is _Unknown:
            return other._messages is _Unknown
        elif other._messages is _Unknown:
            return False
        if len(self) != len(other):
            return False
        for key, value in self:
            if key not in other:
                return False
            if value != other[key]:
                return False
        return True

    def __str__(self):
        return format(self)

    def __format__(self, spec='yaml'):
        return _formatObject(self, spec)

    def _fullName(self, key=None):
        if self._key is not None:
            if self._parent is not None:
                name = self._parent._fullName(self._key)
            else:
                name = str(self._key)
            if key is not None:
                if '.' in key:
                    name += f"[{key}]"
                else:
                    name += f".{key}"
            return name
        if key is not None:
            return str(key)
        return ''

    def _create_child(self, key):
        if self._readOnly:
            raise ValueError(f"{self._readOnly} is read only")
        key = self._validate_key(key)
        if self._messages is _Unknown:
            self.__dict__['_messages'] = self._parent._create_child(self._key)
        return self._messages[key]

    def __call__(self, **kwargs):
        if self._readOnly:
            raise ValueError(f"{self._readOnly} is read only")
        if self._messages is _Unknown:
            self.__dict__['_messages'] = self._parent._create_child(self._key)
        self._messages.clear()
        self._cache.clear()
        for key, value in kwargs.items():
            self[key] = value
        return self

    def __setattr__(self, key, message):
        self[key] = message

    def __setitem__(self, key, message):
        if self._readOnly:
            raise ValueError(f"{self._readOnly} is read only")
        key = self._validate_key(key)
        if self._messages is _Unknown:
            self._messages = self._parent._create_child(self._key)
        if isinstance(message, Message):
            message = message._message
        elif isinstance(message, (MapMessage, RepeatedMessage)):
            message = message._messages
        elif isinstance(message, FieldMessage):
            message = message._value
        elif isinstance(message, Value):
            message = message._raw
        if message is _Unknown:
            self._messages.pop(key, None)
        else:
            if self._field.type == self._field.TYPE_BYTES and isinstance(message, str):
                message = message.encode('utf-8')
            self._messages[key] = message
        self._cache.pop(key, None)

    def __delattr__(self, key):
        del self[key]

    def __delitem__(self, key):
        if self._readOnly:
            raise ValueError(f"{self._readOnly} is read only")
        key = self._validate_key(key)
        if self._messages is not _Unknown:
            if key in self._messages:
                del self._messages[key]
            self._cache.pop(key, None)

    def _validate_key(self, key):
        if isinstance(key, FieldMessage):
            key = key._value
        elif isinstance(key, Value):
            key = key._raw
        if not isinstance(key, str):
            raise TypeError(f"Unexpected key type: {key.__class__}")
        return key


class RepeatedMessage:
    def __init__(self, parent, key, field, messages=_Unknown, readOnly=False):
        self._parent = parent
        self._key = key
        self._field = field
        self._messages = messages
        self._readOnly = readOnly
        self._cache = {}

    def __getitem__(self, key):
        key = self._validate_key(key)
        if key in self._cache:
            return self._cache[key]
        if self._messages is _Unknown or key >= len(self._messages):
            value = _Unknown
        else:
            value = self._messages[key]
        if value is None and self._field.has_default_value:
            value = self._field.default_value
        if self._field.type == self._field.TYPE_MESSAGE:
            if self._field.message_type.name in ('Struct', 'ListValue'):
                value = Value(self, key, value, self._readOnly)
            else:
                value = Message(self, key, self._field.message_type, value, self._readOnly)
        else:
            value = FieldMessage(self, key, self._field.type, value)
        self._cache[key] = value
        return value

    def __bool__(self):
        return self._messages is not _Unknown

    def __len__(self):
        return 0 if self._messages is _Unknown else len(self._messages)

    def __contains__(self, value):
        if self._messages is not _Unknown:
            for message in self:
                if value == message:
                    return True
        return False

    def __iter__(self):
        if self._messages is not _Unknown:
            for ix in range(len(self._messages)):
                yield self[ix]

    def __hash__(self):
        if self._messages is not _Unknown:
            return hash(tuple(hash(item) for item in self))
        return 0

    def __eq__(self, other):
        if not isinstance(other, RepeatedMessage):
            return False
        if self._field.type != other._field.type:
            return False
        if self._field.type == self._field.TYPE_MESSAGE:
            if self._field.message_type.full_name != other._field.message_type.full_name:
                return False
        if self._messages is _Unknown:
            return other._messages is _Unknown
        elif other._messages is _Unknown:
            return False
        if len(self) != len(other):
            return False
        for ix, value in enumerate(self):
            if value != other[ix]:
                return False
        return True

    def __str__(self):
        return format(self)

    def __format__(self, spec='yaml'):
        return _formatObject(self, spec)

    def _fullName(self, key=None):
        if self._key is not None:
            if self._parent is not None:
                name = self._parent._fullName(self._key)
            else:
                name = str(self._key)
            if key is not None:
                name += f"[{key}]"
            return name
        if key is not None:
            return str(key)
        return ''

    def _create_child(self, key):
        if self._readOnly:
            raise ValueError(f"{self._readOnly} is read only")
        key = self._validate_key(key)
        if self._messages is _Unknown:
            self.__dict__['_messages'] = self._parent._create_child(self._key)
        if key == append:
            key = len(self._messages)
        elif key < 0:
            key = len(self._messages) + key
        while key >= len(self._messages):
            self._messages.add()
        return self._messages[key]

    def __call__(self, *args):
        if self._readOnly:
            raise ValueError(f"{self._readOnly} is read only")
        if self._messages is _Unknown:
            self.__dict__['_messages'] = self._parent._create_child(self._key)
        self._messages.clear()
        self._cache.clear()
        for arg in args:
            self.append(arg)
        return self

    def __setitem__(self, key, message):
        if self._readOnly:
            raise ValueError(f"{self._readOnly} is read only")
        key = self._validate_key(key)
        if self._messages is _Unknown:
            self._messages = self._parent._create_child(self._key)
        if key < 0:
            key = len(self._messages) + key
        if isinstance(message, Message):
            message = message._message
        elif isinstance(message, (MapMessage, RepeatedMessage)):
            message = message._messages
        elif isinstance(message, FieldMessage):
            message = message._value
        elif isinstance(message, Value):
            message = message._raw
        if message is _Unknown:
            if key < len(self._messages):
                self._messages.pop(key)
                self._cache.clear()
        else:
            if self._field.type == self._field.TYPE_BYTES and isinstance(message, str):
                message = message.encode('utf-8')
            if key >= len(self._messages):
                self._messages.append(message)
            else:
                self._messages[key] = message
            self._cache.pop(key, None)

    def __delitem__(self, key):
        if self._readOnly:
            raise ValueError(f"{self._readOnly} is read only")
        key = self._validate_key(key)
        if self._messages is not _Unknown:
            del self._messages[key]
            self._cache.pop(key, None)

    def append(self, message=_Unknown):
        if self._readOnly:
            raise ValueError(f"{self._readOnly} is read only")
        if self._messages is _Unknown:
            self._messages = self._parent._create_child(self._key)
        if message is _Unknown:
            message = self._messages.add()
        else:
            message = self._messages.append(message)
        return self[len(self._messages) - 1]

    def _validate_key(self, key):
        if isinstance(key, FieldMessage):
            key = key._value
        elif isinstance(key, Value):
            key = key._raw
        if not isinstance(key, int):
            raise TypeError(f"Unexpected key type: {key.__class__}")
        return key


class FieldMessage:
    def __init__(self, parent, key, kind, value):
        self._parent = parent
        self._key = key
        self._kind = kind
        self._value = value

    def __bool__(self):
        return self._value is not _Unknown

    def __len__(self):
        if self._value is _Unknown:
            return 0
        return len(self._value)

    def __contains__(self, key):
        if self._value is _Unknown:
            return False
        return key in self._value

    def __hash__(self):
        if self._value is _Unknown:
            return 0
        return hash(self._value)

    def __eq__(self, other):
        if self._value is _Unknown:
            return False
        if isinstance(other, FieldMessage):
            return self._value == other._value
        return self._value == other

    def __bytes__(self):
        if self._value is _Unknown:
            return None
        if isinstance(self._value, str):
            return self._value.encode('utf-8')
        return bytes(self._value)

    def __str__(self):
        if self._value is _Unknown:
            return None
        if isinstance(self._value, bytes):
            return self._value.decode('utf-8')
        return str(self._value)

    def __format__(self, spec=''):
        if self._value is _Unknown:
            return None
        return format(self._value, spec)

    def __int__(self):
        if self._value is _Unknown:
            return None
        return int(self._value)

    def __float__(self):
        if self._value is _Unknown:
            return None
        return float(self._value)

    def _fullName(self, key=None):
        if self._key is not None:
            if self._parent is not None:
                name = self._parent._fullName(self._key)
            else:
                name = str(self._key)
            if key is not None:
                if '.' in key:
                    name += f"[{key}]"
                else:
                    name += f".{key}"
            return name
        if key is not None:
            return str(key)
        return ''


class ProtobufValue:
    @property
    def _protobuf_value(self):
        return None


class Value:
    def __init__(self, parent, key, value=_Unknown, readOnly=None):
        self._set_attribute('_parent', parent)
        self._set_attribute('_key', key)
        self._set_attribute('_dependencies', {})
        self._set_attribute('_unknowns', {})
        self._set_attribute('_cache', {})
        self._set_attribute('_readOnly', None)
        if isinstance(value, (google.protobuf.struct_pb2.Value, google.protobuf.struct_pb2.Struct, google.protobuf.struct_pb2.ListValue)) or value is _Unknown:
            self._set_attribute('_value', value)
        else:
            self._set_attribute('_value', google.protobuf.struct_pb2.Value())
            if value is None:
                self._value.null_value = 0
            elif isinstance(value, dict):
                self._value.struct_value.Clear()
                for k, v in value.items():
                    self[k] = v
            elif isinstance(value, (tuple, list)):
                self._value.list_value.Clear()
                for ix, v in enumerate(value):
                    self[ix] = v
            elif isinstance(value, bool): # Must be before number check
                self._value.bool_value = value
            elif isinstance(value, (int, float)):
                self._value.number_value = value
            elif isinstance(value, str):
                self._value.string_value = value
            else:
                raise ValueError(f"Unexpected Value type: {value.__class__}")
        self._set_attribute('_readOnly', readOnly)

    def _set_attribute(self, key, value):
        self.__dict__[key] = value

    def __getattr__(self, key):
        return self[key]

    def __getitem__(self, key):
        key = self._validate_key(key)
        if key in self._cache:
            return self._cache[key]
        if key in self._unknowns:
            return self._unknowns[key]
        if isinstance(key, str):
            match self._kind:
                case 'struct_value':
                    value = self._value.struct_value.fields.get(key, _Unknown)
                case 'Struct':
                    value = self._value.fields.get(key, _Unknown)
                case 'Unknown':
                    value = _Unknown
                case _:
                    raise ValueError(f"Invalid key \"{key}\" for kind: {self._kind}")
        elif isinstance(key, int):
            match self._kind:
                case 'list_value':
                    if key < len(self._value.list_value.values):
                        value = self._value.list_value.values[key]
                    else:
                        value = _Unknown
                case 'ListValue':
                    if key < len(self._value.values):
                        value = self._value.values[key]
                    else:
                        value = _Unknown
                case 'Unknown':
                    value = _Unknown
                case _:
                    raise ValueError(f"Invalid key \"{key}\" for kind: {self._kind}")
        else:
            raise NotImplementedError()
        value = Value(self, key, value, self._readOnly)
        self._cache[key] = value
        return value

    def __bool__(self):
        return not self._isUnknown

    def __len__(self):
        match self._kind:
            case 'struct_value':
                return len(self._value.struct_value.fields) + len(self._unknowns)
            case 'Struct':
                return len(self._value.fields) + len(self._unknowns)
            case 'list_value':
                return len(self._value.list_value.values) + len(self._unknowns)
            case 'ListValue':
                return len(self._value.values) + len(self._unknowns)
            case 'string_value':
                return len(self._value.string_value)
            case 'bool_value':
                return 1 if self._value.bool_value else 0
        return 0

    def __contains__(self, item):
        match self._kind:
            case 'struct_value':
                return item in self._value.struct_value.fields or item in self._unknowns
            case 'Struct':
                return item in self._value.fields or item in self._unknowns
            case 'list_value' | 'ListValue':
                for value in self:
                    if item == value:
                        return True
        return False

    def __iter__(self):
        match self._kind:
            case 'struct_value':
                for key in sorted(set(self._value.struct_value.fields) | set(self._unknowns.keys())):
                    yield key, self[key]
            case 'Struct':
                for key in sorted(set(self._value.fields) | set(self._unknowns.keys())):
                    yield key, self[key]
            case 'list_value':
                for ix in range(len(self._value.list_value.values)):
                    yield self[ix]
                for ix in sorted(self._unknowns.keys()):
                    if ix >= len(self._value.list_value.values):
                        yield self[ix]
            case 'ListValue':
                for ix in range(len(self._value.values)):
                    yield self[ix]
                for ix in sorted(self._unknowns.keys()):
                    if ix >= len(self._value.values):
                        yield self[ix]

    def __hash__(self):
        match self._kind:
            case 'struct_value' | 'Struct':
                return hash(tuple(hash(item) for item in sorted(iter(self), key=lambda item: item[0])))
            case 'list_value' | 'ListValue':
                return hash(tuple(hash(item) for item in self))
            case 'string_value':
                return hash(self._value.string_value)
            case 'null_value':
                return hash(None)
            case 'number_value':
                return hash(self._value.number_value)
            case 'bool_value':
                return hash(self._value.bool_value)
        return 0

    def __eq__(self, other):
        kind = self._kind
        if isinstance(other, Value) and other._kind != kind:
            return False
        match kind:
            case 'struct_value' | 'Struct':
                if not isinstance(other, (Value, dict)):
                    return False
                if len(self) != len(other):
                    return False
                for key, value in self:
                    if key not in other:
                        return False
                    if value != other[key]:
                        return False
                return True
            case 'list_value' | 'ListValue':
                if not isinstance(other, (Value, tuple, list)):
                    return False
                if len(self) != len(other):
                    return False
                for ix, value in enumerate(self):
                    if value != other[ix]:
                        return False
                return True
            case 'Unknown':
                if isinstance(other, Value):
                    return other._isUnknown
                return False
            case 'string_value':
                if isinstance(other, Value):
                    return self._value.string_value == other._value.string_value
                if isinstance(other, str):
                    return self._value.string_value == other
                return False
            case 'null_value':
                if isinstance(other, Value):
                    return True
                return other is None
            case 'number_value':
                if isinstance(other, Value):
                    return self._value.number_value == other._value.number_value
                if isinstance(other, (int, float)):
                    return self._value.number_value == other
                return False
            case 'bool_value':
                if isinstance(other, Value):
                    return self._value.bool_value == other._value.bool_value
                if isinstance(other, bool):
                    return self._value.bool_value == other
                return False
        return False

    def __str__(self):
        return format(self, '')

    def __format__(self, spec='yaml'):
        if not spec:
            match self._kind:
                case 'Unknown':
                    return '<<UNKNOWN>>'
                case 'string_value':
                    return self._value.string_value
                case 'null_value':
                    return 'null'
                case 'number_value':
                    value = self._value.number_value
                    if value.is_integer():
                        value = int(value)
                    return str(value)
                case 'bool_value':
                    return 'true' if self._value.bool_value else 'false'
        return _formatObject(self, spec)

    def __int__(self):
        kind = self._kind
        match kind:
            case 'string_value':
                return int(self._value.string_value)
            case 'number_value':
                return int(self._value.number_value)
            case 'bool_value':
                return int(self._value.bool_value)
            case 'Unknown':
                return 0
        raise TypeError(f"Cannot convert kind to integer: {kind}")

    def __float__(self):
        kind = self._kind
        match kind:
            case 'string_value':
                return float(self._value.string_value)
            case 'number_value':
                return float(self._value.number_value)
            case 'bool_value':
                return float(self._value.bool_value)
            case 'Unknown':
                return 0.0
        raise TypeError(f"Cannot convert kind to float: {kind}")

    def _fullName(self, key=None):
        if self._key is not None:
            if self._parent is not None:
                name = self._parent._fullName(self._key)
            else:
                name = str(self._key)
            if key is not None:
                if self._isMap:
                    if key.isidentifier():
                        name += f".{key}"
                    else:
                        name += f"['{key}']"
                elif self._isList:
                    name += f"[{key}]"
                else:
                    if isinstance(key, int):
                        name += f"[{key}]"
                    else:
                        if '.' in key:
                            name += f"[{key}]"
                        else:
                            name += f".{key}"
            return name
        if key is not None:
            return str(key)
        return ''

    def __call__(self, *args, **kwargs):
        if self._readOnly:
            raise ValueError(f"{self._readOnly} is read only")
        self.__dict__['_value'] = google.protobuf.struct_pb2.Value()
        self._cache.clear()
        self._dependencies.clear()
        self._unknowns.clear()
        if len(kwargs):
            if len(args):
                raise ValueError('Connect specify both kwargs and args')
            for key, value in kwargs.items():
                self[key] = value
        elif len(args):
            for key in range(len(args)):
                self[key] = args[key]
        return self

    def __setattr__(self, key, value):
        self[key] = value

    def __setitem__(self, key, value):
        if self._readOnly:
            raise ValueError(f"{self._readOnly} is read only")
        key = self._validate_key(key)
        if isinstance(key, str):
            if self._ensure_map() == 'struct_value':
                values = self._value.struct_value.fields
            else:
                values = self._value.fields
        elif isinstance(key, int):
            if self._ensure_list() == 'list_value':
                values = self._value.list_value.values
            else:
                values = self._value.values
            if key == append:
                key = len(values)
            elif key < 0:
                key = len(values) + key
            while key >= len(values):
                values.add()
        else:
            raise NotImplementedError()
        self._cache.pop(key, None)
        self._dependencies.pop(key, None)
        self._unknowns.pop(key, None)
        if isinstance(value, ProtobufValue):
            value = value._protobuf_value
        if value is None:
            values[key].null_value = 0
        elif isinstance(value, bool): # Must be before int check
            values[key].bool_value = value
        elif isinstance(value, bytes):
            values[key].string_value = value._value.decode('utf-8')
        elif isinstance(value, str):
            values[key].string_value = value
        elif isinstance(value, (int, float)):
            values[key].number_value = value
        elif isinstance(value, dict):
            values[key].struct_value.Clear()
            for k, v in value.items():
                self[key][k] = v
        elif isinstance(value, (list, tuple)):
            values[key].list_value.Clear()
            for ix, v in enumerate(value):
                self[key][ix] = v
        elif isinstance(value, FieldMessage):
            self._dependencies[key] = value
            if isinstance(value._value, str):
                values[key].string_value = value._value
            elif isinstance(value._value, bytes):
                values[key].string_value = value._value.decode('utf-8')
            elif value._value is None:
                values[key].null_value = value._value.null_value
            elif isinstance(value._value, (int, float)):
                values[key].number_value = value._value
            elif isinstance(value._value, bool):
                values[key].bool_value = value._value
            elif value._value is _Unknown:
                self._setUnknown(key, value)
            else:
                raise ValueError(f"Unexpected field type: {value._value.__class__}")
        elif isinstance(value, Value):
            self._dependencies[key] = value
            match value._kind:
                case 'struct_value' | 'Struct':
                    values[key].struct_value.Clear()
                    for k, v in value:
                        self[key][k] = v
                case 'list_value' | 'ListValue':
                    values[key].list_value.Clear()
                    for ix, v in enumerate(value):
                        self[key][ix] = v
                case 'string_value':
                    values[key].string_value = value._value.string_value
                case 'null_value':
                    values[key].null_value = value._value.null_value
                case 'number_value':
                    values[key].number_value = value._value.number_value
                case 'bool_value':
                    values[key].bool_value = value._value.bool_value
                case 'Unknown':
                    self._setUnknown(key, value)
                case _:
                    raise ValueError(f"Unexpected value kind: {value._kind}")
        else:
            raise ValueError(f"Unexpected type: {value.__class__}")

    @property
    def _raw(self):
        match self._kind:
            case 'struct_value':
                return self._value.struct_value
            case 'list_value':
                return self._value.list_value
            case 'string_value':
                return self._value.string_value
            case 'null_value':
                return self._value.null_value
            case 'number_value':
                return self._value.number_value
            case 'bool_value':
                return self._value.bool_value
            case 'Struct' | 'ListValue':
                return self._value
            case 'Unknown':
                return _Unknown

    def _setUnknown(self, key, value):
        self._dependencies.pop(key, None)
        self._unknowns[key] = value
        match self._kind:
            case 'struct_value':
                if key in self._value.struct_value.fields:
                    del self._value.struct_value[key]
            case 'Struct':
                if key in self._value.fields:
                    del self._value[key]
            case 'list_value':
                if key < len(self._value.list_value.values):
                    self._value.list_value.values[key].Clear()
                for ix in reversed(range(len(self._value.list_value.values))):
                    if ix not in self._unknowns:
                        break
                    del self._value.list_value[ix]
            case 'ListValue':
                if key < len(self._value.values):
                    self._value.values[key].Clear()
                for ix in reversed(range(len(self._value.values))):
                    if ix not in self._unknowns:
                        break
                    del self._value[ix]

    def __delattr__(self, key):
        del self[key]

    def __delitem__(self, key):
        if self._readOnly:
            raise ValueError(f"{self._readOnly} is read only")
        kind = self._kind
        if kind == 'Unknown':
            return
        key = self._validate_key(key)
        if isinstance(key, str):
            match kind:
                case 'struct_value':
                    if key in self._value.struct_value.fields:
                        del self._value.struct_value[key]
                case 'Struct':
                    if key in self._value.fields:
                        del self._value[key]
                case _:
                    raise ValueError(f"Invalid key \"{key}\" for kind: {self._kind}")
            self._cache.pop(key, None)
            self._dependencies.pop(key, None)
            self._unknowns.pop(key, None)
        elif isinstance(key, int):
            match kind:
                case 'list_value':
                    values = self._value.list_value
                case 'ListValue':
                    values = self._value
                case _:
                    raise ValueError(f"Invalid key \"{key}\" for kind: {self._kind}")
            if key < len(values.values):
                del values[key]
            self._cache.pop(key, None)
            self._dependencies.pop(key, None)
            self._unknowns.pop(key, None)
            for ix in sorted(self._dependencies.keys()):
                if ix > key:
                    self._cache.pop(ix, None)
                    self._dependencies[ix - 1] = self._dependences[ix]
                    del self._dependencies[ix]
            for ix in sorted(self._unknowns.keys()):
                if ix > key:
                    self._cache.pop(ix, None)
                    self._unknowns[ix - 1] = self._unknowns[ix]
                    del self._unknowns[ix]
            for ix in reversed(range(len(values.values))):
                if ix not in self._unknowns:
                    break
                del values[ix]
        else:
            raise NotImplementedError()

    def _create_child(self, key):
        if self._readOnly:
            raise ValueError(f"{self._readOnly} is read only")
        key = self._validate_key(key)
        if isinstance(key, str):
            if self._ensure_map() == 'struct_value':
                fields = self._value.struct_value.fields
            else:
                fields = self._value.fields
            fields[key].Clear()
            return fields[key]
        if isinstance(key, int):
            if self._ensure_list() == 'list_value':
                values = self._value.list_value.values
            else:
                values = self._value.values
            if key == append:
                key = len(values)
            elif key < 0:
                key = len(values) + key
            while key >= len(values):
                values.add()
            values[key].Clear()
            return values[key]
        raise NotImplementedError()

    def _validate_key(self, key):
        if isinstance(key, FieldMessage):
            key = key._value
        elif isinstance(key, Value):
            key = key._raw
        if not isinstance(key, (str, int)):
            raise TypeError(f"Unexpected key type: {key.__class__}")
        return key

    def _ensure_map(self):
        kind = self._kind
        if kind == 'Unknown':
            if self._parent is None:
                self.__dict__['_value'] = google.protobuf.struct_pb2.Value()
            else:
                self.__dict__['_value'] = self._parent._create_child(self._key)
            if isinstance(self._value, google.protobuf.struct_pb2.Value) and self._value.WhichOneof('kind') is None:
                self._value.struct_value.Clear()
            kind = self._kind
        if kind not in ('struct_value', 'Struct'):
            raise ValueError(f"Invalid map kind: {kind}")
        return kind

    def _ensure_list(self):
        kind = self._kind
        if kind == 'Unknown':
            if self._parent is None:
                self.__dict__['_value'] = google.protobuf.struct_pb2.Value()
            else:
                self.__dict__['_value'] = self._parent._create_child(self._key)
            if isinstance(self._value, google.protobuf.struct_pb2.Value) and self._value.WhichOneof('kind') is None:
                self._value.list_value.Clear()
            kind = self._kind
        if kind not in ('list_value', 'ListValue'):
            raise ValueError(f"Invalid list kind: {kind}")
        return kind

    @property
    def _kind(self):
        if isinstance(self._value, google.protobuf.struct_pb2.Value):
            return self._value.WhichOneof('kind') or 'Unknown'
        if isinstance(self._value, google.protobuf.struct_pb2.Struct):
            return 'Struct'
        if isinstance(self._value, google.protobuf.struct_pb2.ListValue):
            return 'ListValue'
        if self._value is _Unknown:
            return 'Unknown'
        raise ValueError(f"Unexpected value type: {self._value.__class__}")

    @property
    def _isUnknown(self):
        return self._kind == 'Unknown'

    @property
    def _isMap(self):
        return self._kind in ('struct_value', 'Struct')

    @property
    def _isList(self):
        return self._kind in ('list_value', 'ListValue')

    @property
    def _getUnknowns(self):
        unknowns = {}
        for key, unknown in self._unknowns.items():
            unknowns[self._fullName(key)] = unknown._fullName()
        if self._isMap:
            for key, value in self:
                if isinstance(value, Value):
                    unknowns.update(value._getUnknowns)
        elif self._isList:
            for value in self:
                if isinstance(value, Value):
                    unknowns.update(value._getUnknowns)
        return unknowns

    @property
    def _getDependencies(self):
        dependencies = {}
        for key, dependency in self._dependencies.items():
            dependencies[self._fullName(key)] = dependency._fullName()
        for key, unknown in self._unknowns.items():
            dependencies[self._fullName(key)] = unknown._fullName()
        if self._isMap:
            for key, value in self:
                if isinstance(value, Value):
                    dependencies.update(value._getDependencies)
        elif self._isList:
            for value in self:
                if isinstance(value, Value):
                    dependencies.update(value._getDependencies)
        return dependencies

    def _patchUnknowns(self, patches):
        for key in list(self._unknowns.keys()):
            self[key] = patches[key]
        if self._isMap:
            for key, value in self:
                if isinstance(value, Value) and len(value):
                    patch = patches[key]
                    print(patch.__class__, str(patch))
                    if isinstance(patch, Value) and patch._kind == value._kind and len(patch):
                        value._patchUnknowns(patch)
        elif self._isList:
            for ix, value in enumerate(self):
                if isinstance(value, Value) and len(value):
                    patch = patches[ix]
                    if isinstance(patch, Value) and patch._kind == value._kind and len(patch):
                        value._patchUnknowns(patch)

    def _renderUnknowns(self, trimFullName):
        for key, unknown in list(self._unknowns.items()):
            self[key] = f"UNKNOWN:{trimFullName(unknown._fullName())}"
            self._dependencies[key] = unknown
        if self._isMap:
            for key, value in self:
                if isinstance(value, Value) and len(value):
                    value._renderUnknowns(trimFullName)
        elif self._isList:
            for ix, value in enumerate(self):
                if isinstance(value, Value) and len(value):
                    value._renderUnknowns(trimFullName)


def _formatObject(object, spec='yaml'):
    match spec:
        case 'json':
            return json.dumps(object, indent=2, cls=_JSONEncoder)
        case 'jsonc':
            return json.dumps(object, separators=(',', ':'), cls=_JSONEncoder)
        case 'protobuf':
            if isinstance(object, Message):
                return str(object._message)
            if isinstance(object, (MapMessage, RepeatedMessage)):
                return str(object._messages)
            if isinstance(object, Value):
                return str(object._value)
            return format(object)
        case _:
            return yaml.dump(object, Dumper=_Dumper)


class _JSONEncoder(json.JSONEncoder):
    def default(self, object):
        if isinstance(object, (Message, MapMessage)):
            if object:
                return {key: value for key, value in object}
            return None
        if isinstance(object, RepeatedMessage):
            if object:
                return [value for value in object]
            return None
        if isinstance(object, FieldMessage):
            return object._value
        if isinstance(object, Value):
            match object._kind:
                case 'struct_value' | 'Struc':
                    return {key: value for key, value in object}
                case 'list_value' | 'ListValue':
                    return [value for value in object]
                case 'string_value':
                    return object._value.string_value
                case 'null_value':
                    return None
                case 'number_value':
                    value = object._value.number_value
                    if value.is_integer():
                        value = int(value)
                    return value
                case 'bool_value':
                    return object._value.bool_value
                case 'Unknown':
                    return '<<UNKNOWN>>'
                case _:
                    return '<<UNEXPECTED>>'
        if isinstance(object, datetime.datetime):
            return object.isoformat()
        return super(_JSONEncoder, self).default(object)


class _Dumper(yaml.SafeDumper):

    def represent_str(self, data):
        return self.represent_scalar('tag:yaml.org,2002:str', data, '|' if '\n' in data else None)

    def represent_message_dict(self, message):
        return self.represent_dict({key: value for key, value in message})

    def represent_message_list(self, messages):
        return self.represent_list([value for value in messages])

    def represent_message_field(self, field):
        if isinstance(field._value, str):
            return self.represent_str(field._value)
        if isinstance(field._value, bytes):
            return self.represent_binary(field._value)
        if field._value is None:
            return self.represent_none()
        if isinstance(field._value, int):
            return self.represent_int(field._value)
        if isinstance(field._value, float):
            if field._value.is_integer():
                return self.represent_int(int(field._value))
            return self.represent_float(field._value)
        if isinstance(field._value, bool):
            return self.represent_bool(field._value)
        if field._value is _Unknown:
            return self.represent_str('<<UNKNOWN>>')
        return self.represent_str('<<UNEXPECTED>>')

    def represent_value(self, value):
        match value._kind:
            case 'struct_value' | 'Struct':
                return self.represent_dict({k:v for k,v in value})
            case 'list_value' | 'ListValue':
                return self.represent_list([v for v in value])
            case 'string_value':
                return self.represent_str(value._value.string_value)
            case 'null_value':
                return self.represent_none(None)
            case 'number_value':
                value = value._value.number_value
                if value.is_integer():
                    return self.represent_int(int(value))
                return self.represent_float(value)
            case 'bool_value':
                return self.represent_bool(value._value.bool_value)
            case 'Unknown':
                return self.represent_str('<<UNKNOWN>>')
            case _:
                return self.represent_str('<<UNEXPECTED>>')

_Dumper.add_representer(str, _Dumper.represent_str)
_Dumper.add_representer(Message, _Dumper.represent_message_dict)
_Dumper.add_representer(MapMessage, _Dumper.represent_message_dict)
_Dumper.add_representer(RepeatedMessage, _Dumper.represent_message_list)
_Dumper.add_representer(FieldMessage, _Dumper.represent_message_field)
_Dumper.add_representer(Value, _Dumper.represent_value)
