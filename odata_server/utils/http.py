# Copyright (c) 2021-2022 Future Internet Consulting and Development Solutions S.L.

import json
import types

from flask import request, Response, stream_with_context

from odata_server.utils.json import JSONEncoder


def build_response_headers(maxpagesize=None, _return=None, streaming=False, metadata="full", version="4.0"):
    preferences = {}

    if maxpagesize is not None:
        preferences["odata.maxpagesize"] = maxpagesize

    if _return is not None:
        preferences["return"] = _return

    content_type = [
        "application/json",
        "{}={}".format(
            "odata.metadata" if version == "4.0" else "metadata",
            metadata,
        ),
        "charset=utf-8",
    ]
    if streaming is True:
        content_type.append("{}=true".format("odata.streaming" if version == "4.0" else "streaming"))

    headers = {
        "Content-Type": ";".join(content_type),
        "OData-Version": version,
        "Preference-Applied": ",".join(["{}={}".format(key, value) for key, value in preferences.items()])
    }
    return headers


def make_response(data=None, status=200, etag=None, headers={}):
    if isinstance(data, types.GeneratorType):
        body = stream_with_context(data)
    elif data is not None:
        body = json.dumps(data, ensure_ascii=False, sort_keys=True, cls=JSONEncoder).encode("utf-8")
    else:
        body = None

    response = Response(body, status, headers=headers)
    if etag is not None:
        response.set_etag(etag, weak=True)
    else:
        response.add_etag(weak=True)
    return response.make_conditional(request)
