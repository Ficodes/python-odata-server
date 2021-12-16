# Copyright (c) 2021 Future Internet Consulting and Development Solutions S.L.

from odata_server import edm


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
