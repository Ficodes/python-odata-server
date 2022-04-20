# Copyright (c) 2021-2022 Future Internet Consulting and Development Solutions S.L.

from odata_server import edm


def build_initial_projection(entity_type, select="", prefix="", anonymous=True):
    projection = {
        "_id": 0,
        "uuid": 1,
    }
    fields_to_remove = []

    if prefix != "":
        prefix += "."

    if select == "*":
        select = ""

    if select == "":
        select = [p.Name for p in entity_type.property_list]
    else:
        select = select.split(",")

    for p in select:
        if p in entity_type.key_properties:
            projection[p] = 1
        else:
            projection["{}{}".format(prefix, p)] = 1

    if not anonymous:
        for p in entity_type.key_properties:
            if p not in projection:
                projection[p] = 1
                fields_to_remove.append(p)

    return projection, fields_to_remove


def get_mongo_prefix(RootEntitySet, subject, seq=None):
    if isinstance(subject, edm.NavigationProperty):
        prefix = subject.Name if subject.isembedded and subject.entity_type != RootEntitySet.entity_type else ""
        if RootEntitySet.prefix != "" and prefix != "":
            prefix = "{}.{}".format(RootEntitySet.prefix, prefix)
        elif RootEntitySet.prefix != "" and prefix == "":
            prefix = RootEntitySet.prefix
    else:
        prefix = RootEntitySet.prefix

    return prefix if seq is None else "{}.{}".format(prefix, seq)
