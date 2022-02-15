# Copyright (c) 2021 Future Internet Consulting and Development Solutions S.L.

import json
import os
import re
from urllib.parse import unquote

import abnf
import arrow
# TODO depend on a generic abort method
from flask import abort


STRIP_WHITESPACE_FROM_URLENCODED_RE = re.compile(r"(?:^(?:[ \t]|%20|%09)+|(?:[ \t]|%20|%09)+$)")


class ODataGrammar(abnf.Rule):

    ParserError = abnf.parser.ParseError


ODataGrammar.from_file(os.path.join(os.path.dirname(__file__), "..", "data", "odata.abnf"))


def parse_primitive_literal(node):
    value_type = node.name
    value = node.value
    if value_type == "string":
        return unquote(value)[1:-1].replace("''", "'")
    elif value_type in ("booleanValue", "decimalValue", "int16Value", "int32Value", "int64Value", "nullValue"):
        return json.loads(value)
    elif value_type in ("dateTimeOffsetValueInUrl",):
        return arrow.get(value).datetime
    elif value_type in ("dateValue",):
        return arrow.get(value).format("YYYY-MM-DD")
    else:
        abort(501)


def parse_key_value(key_value_node):
    if key_value_node.name == "keyPropertyValue":
        # keyPropertyValue are always a primitiveLiteral node
        value_node = key_value_node.children[0].children[0]
        return parse_primitive_literal(value_node)
    else:  # key_value_node == "parameterAlias"
        raise Exception("Not supported")


def parse_key_predicate(EntityType, key_predicate):
    key_properties = set(EntityType.key_properties)
    single_key = len(key_properties) == 1
    if key_predicate.children[0].name == "simpleKey":
        if not single_key:
            abort(400, "{} uses a compound key".format(EntityType.Name))

        key = tuple(key_properties)[0]
        id_value = parse_key_value(key_predicate.children[0].children[1])
        return {key: id_value}
    elif key_predicate.children[0].name == "compoundKey":
        keypairs = key_predicate.children[0].children[1:-1]
        key = {}
        for keypair in keypairs:
            if keypair.value == ",":
                continue

            key_id = keypair.children[0].value
            try:
                key_properties.remove(key_id)
            except KeyError:
                if key_id in EntityType.key_properties:
                    abort(400, "Duplicated key value for {}".format(key_id))
                else:
                    abort(400, "{} does not use {} as key property".format(EntityType.Name, key_id))

            key[key_id] = parse_key_value(keypair.children[2])

        if len(key_properties) > 0:
            abort(400, "The following key properties are missing: {}".format(key_properties))

        return key
    else:
        abort(501)


def parse_qs(qs):
    asdict = {}
    aslist = []
    for name_value in qs.split(b"&"):
        if not name_value:
            continue
        nv = name_value.split(b"=", 1)
        if len(nv) != 2:
            nv.append("")

        name = unquote(nv[0].replace(b"+", b" ").decode("utf-8"))
        # Extra feature not required by OData spec: strip whitespace from get parameters
        value = STRIP_WHITESPACE_FROM_URLENCODED_RE.sub("", nv[1].replace(b"+", b" ").decode("utf-8"))
        aslist.append((name, value))
        asdict[name] = value

    return asdict
