# Copyright (c) 2022 Future Internet Consulting and Development Solutions S.L.

import datetime
import json
from urllib.parse import urlencode
import uuid

from flask import request, url_for


class JSONEncoder(json.JSONEncoder):
    """JSON encoder that handles extra types compared to the
    built-in :class:`json.JSONEncoder`.

    -   :class:`datetime.datetime` and :class:`datetime.date` are
        serialized to :rfc:`822` strings. This is the same as the HTTP
        date format.
    -   :class:`uuid.UUID` is serialized to a string.
    """

    def default(self, o):
        if isinstance(o, datetime.datetime):
            if o.tzinfo:
                # eg: '2015-09-25T23:14:42.588601+00:00'
                return o.isoformat('T')
            else:
                # No timezone present - assume UTC.
                # eg: '2015-09-25T23:14:42.588601Z'
                return o.isoformat('T') + 'Z'

        if isinstance(o, datetime.date):
            return o.isoformat()

        if isinstance(o, uuid.UUID):
            return str(o)

        return json.JSONEncoder.default(self, o)


def generate_collection_response(results, offset, page_limit, prepare, odata_context, odata_count=None, prepare_kwargs={}):

    yield b'{"@odata.context": "%s"' % odata_context.encode("utf-8")

    if odata_count:
        yield b',"@odata.count": %d' % odata_count

    yield b',"value": ['

    pending_iterations = page_limit
    try:
        result = next(results)
        data = prepare(result, **prepare_kwargs)
        yield json.dumps(data, ensure_ascii=False, cls=JSONEncoder).encode("utf-8") + b'\n'
        pending_iterations -= 1

        while pending_iterations > 0:
            result = next(results)
            data = prepare(result, **prepare_kwargs)
            yield b',' + json.dumps(data, ensure_ascii=False, cls=JSONEncoder).encode("utf-8") + b'\n'
            pending_iterations -= 1
    except StopIteration:
        pass

    yield b']'

    if pending_iterations == 0:
        try:
            hasnext = next(results) is not None
        except StopIteration:
            hasnext = False
    else:
        hasnext = False

    if hasnext:
        query_params = request.args.copy()
        query_params["$skip"] = offset + page_limit

        odata_next_link = b"%(path)s?%(params)s" % {
            b"path": url_for(
                "odata.{}".format(prepare_kwargs["RootEntitySet"].Name),
                _external=True
            ).encode("utf-8"),
            b"params": urlencode(query_params).encode("utf-8"),
        }
        yield b',"@odata.nextLink":"%s"' % odata_next_link

    yield b"}"
