# Copyright (c) 2021-2022 Future Internet Consulting and Development Solutions S.L.

import json


def format_literal(value):
    if type(value) == str:
        return "'{}'".format(value)
    else:
        return json.dumps(value)


def format_key_predicate(id_value: dict):
    if len(id_value) == 1:
        return format_literal(tuple(id_value.values())[0])
    else:
        return ",".join("{}={}".format(key, format_literal(value)) for key, value in id_value.items())


def extract_id_value(entity_type, data: dict):
    return {
        prop: data[prop]
        for prop in entity_type.key_properties
    }
