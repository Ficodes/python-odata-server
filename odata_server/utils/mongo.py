# Copyright (c) 2021-2022 Future Internet Consulting and Development Solutions S.L.

import re
from urllib.parse import unquote

from odata_server import edm

COMMA_RE = re.compile(r"\s*,\s*")


def build_initial_projection(entity_type, select="", prefix="", anonymous=True):
    projection = {
        "_id": 0,
        "uuid": 1,
    }
    fields_to_remove = []

    if prefix != "":
        prefix += "."

    select = unquote(select)
    if select == "*":
        select = ""

    if select == "":
        select = [p.Name for p in entity_type.property_list]
    else:
        # TODO use abnf grammar adding support for using whitespace around
        # comma characters
        select = [field for field in COMMA_RE.split(select) if field != ""]
        if len(select) == 0:
            select = [p.Name for p in entity_type.property_list]

    for p in select:
        if p in entity_type.key_properties:
            projection[p] = 1
        else:
            projection[f"{prefix}{p}"] = 1

    if not anonymous:
        for p in entity_type.key_properties:
            if p not in projection:
                projection[p] = 1
                fields_to_remove.append(p)

    return projection, fields_to_remove


def get_mongo_prefix(RootEntitySet, subject, seq=None):
    if isinstance(subject, edm.NavigationProperty):
        prefix = (
            subject.Name
            if subject.isembedded and subject.entity_type != RootEntitySet.entity_type
            else ""
        )
        if RootEntitySet.prefix != "" and prefix != "":
            prefix = f"{RootEntitySet.prefix}.{prefix}"
        elif RootEntitySet.prefix != "" and prefix == "":
            prefix = RootEntitySet.prefix
    else:
        prefix = RootEntitySet.prefix

    return prefix if seq is None else f"{prefix}.{seq}"
