# Copyright (c) 2021-2022 Future Internet Consulting and Development Solutions S.L.

from flask import url_for

from .common import extract_id_value, format_key_predicate


def add_odata_annotations(data, entity_set):
    key_predicate = format_key_predicate(extract_id_value(entity_set.entity_type, data))
    base_url = url_for("odata.{}".format(entity_set.Name), _external=True)
    data["@odata.id"] = f"{base_url}({key_predicate})"
    data["@odata.etag"] = f'W/"{data["uuid"]}"'
    del data["uuid"]

    return data
