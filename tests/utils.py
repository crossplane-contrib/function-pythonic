
import datetime
import yaml
from google.protobuf.struct_pb2 import Struct, ListValue


def yaml_load(text):
    return _yaml_clean(yaml.safe_load(text))

def _yaml_clean(values):
    if isinstance(values, dict):
        for field, value in values.items():
            values[field] = _yaml_clean(value)
    elif isinstance(values, (list, tuple)):
        for ix, value in enumerate(values):
            values[ix] = _yaml_clean(value)
    elif isinstance(values, datetime.datetime):
        values = values.isoformat().replace('+00:00', 'Z')
    return values


def message_merge(message, values):
    for field, value in values.items():
        descriptor = message.DESCRIPTOR.fields_by_name.get(field)
        if not descriptor:
            print('no field', message, field, value)
        if isinstance(value, (dict, list, tuple)):
            current = getattr(message, field)
            if isinstance(value, dict):
                if isinstance(current, Struct):
                    map_merge(current, value)
                else:
                    if descriptor.is_repeated:
                        if descriptor.message_type.GetOptions().map_entry:
                            message_map_merge(descriptor, current, value)
                        else:
                            message_list_merge(current, value)
                    else:
                        message_merge(current, value)
            else:
                if isinstance(current, ListValue):
                    list_merge(current, value)
                else:
                    descriptor = message.DESCRIPTOR.fields_by_name.get(field)
                    if descriptor.is_repeated:
                        if descriptor.message_type.GetOptions().map_entry:
                            message_map_merge(descriptor, current, value)
                        else:
                            message_list_merge(current, value)
                    else:
                        message_merge(current, value)
            continue
        try:
            setattr(message, field, value)
        except AttributeError:
            print(message, field, value, descriptor.type, descriptor.TYPE_BYTES)
            raise

def message_map_merge(descriptor, message, values):
    descriptor = descriptor.message_type.fields_by_name['value']
    for field, value in values.items():
        if isinstance(value, (dict, list, tuple)):
            current = message[field]
            if isinstance(current, Struct):
                map_merge(current, value)
            else:
                message_merge(current, value)
        else:
            if isinstance(value, str) and descriptor.type == descriptor.TYPE_BYTES:
                value = value.encode()
            message[field] = value

def message_list_merge(message, values):
    for ix, value in enumerate(values):
        if ix < len(message):
            message_merge(message[ix], value)
        else:
            message_merge(message.add(), value)

def map_merge(message, values):
    for field, value in values.items():
        if isinstance(value, (dict, list, tuple)):
            if field in message:
                current = message[field]
                if isinstance(value, dict):
                    map_merge(current, value)
                else:
                    list_merge(current, value)
                continue
        elif value is None:
            if field in message:
                del message[field]
            continue
        message[field] = value

def list_merge(message, values):
    for ix, value in enumerate(values):
        if ix < len(message):
            if isinstance(value, (dict, list, tuple)):
                current = message[ix]
                if isinstance(value, dict):
                    map_merge(current, value)
                else:
                    list_merge(current, value)
            else:
                message[ix] = value
        else:
            message.append(value)

def message_dict(message):
    result = {}
    for field, value in message.ListFields():
        if field.type == field.TYPE_MESSAGE:
            if field.message_type.name == 'Struct':
                value = map_dict(value)
            elif field.message_type.name == 'ListValue':
                value = list_list(value)
            elif field.is_repeated:
                if field.message_type.GetOptions().map_entry:
                    value = message_map_dict(field, value)
                else:
                    value = message_list_list(field, value)
            else:
                value = message_dict(value)
        elif field.type in (field.TYPE_DOUBLE, field.TYPE_FLOAT):
            if value.is_integer():
                value = int(value)
        elif field.type == field.TYPE_BYTES:
            value = value.decode()
        result[field.name] = value
    return result

def message_map_dict(descriptor, message):
    descriptor = descriptor.message_type.fields_by_name['value']
    result = {}
    for field, value in message.items():
        if descriptor.type == descriptor.TYPE_MESSAGE:
            if descriptor.message_type.name == 'Struct':
                value = map_dict(value)
            elif descriptor.message_type.name == 'ListValue':
                value = list_list(value)
            else:
                value = message_dict(value)
        elif descriptor.type in (descriptor.TYPE_DOUBLE, descriptor.TYPE_FLOAT):
            if value.is_integer():
                value = int(value)
        elif descriptor.type == descriptor.TYPE_BYTES:
            value = value.decode()
        result[field] = value
    return result

def message_list_list(descriptor, message):
    result = []
    for value in message:
        if descriptor.type == descriptor.TYPE_MESSAGE:
            if descriptor.message_type.name == 'Struct':
                value = map_dict(value)
            elif descriptor.message_type.name == 'ListValue':
                value = list_list(value)
            else:
                value = message_dict(value)
        elif descriptor.type in (descriptor.TYPE_DOUBLE, descriptor.TYPE_FLOAT):
            if value.is_integer():
                value = int(value)
        elif descriptor.type == descriptor.TYPE_BYTES:
            value = value.decode()
        result.append(value)
    return result

def map_dict(message):
    result = {}
    for field, value in message.items():
        if isinstance(value, Struct):
            value = map_dict(value)
        elif isinstance(value, ListValue):
            value = list_list(value)
        elif isinstance(value, float):
            if value.is_integer():
                value = int(value)
        result[field] = value
    return result

def list_list(message):
    result = []
    for value in message:
        if isinstance(value, Struct):
            value = map_dict(value)
        elif isinstance(value, ListValue):
            value = list_list(value)
        elif isinstance(value, float):
            if value.is_integer():
                value = int(value)
        result.append(value)
    return result
