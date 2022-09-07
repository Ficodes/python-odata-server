# Copyright (c) 2022 Future Internet Consulting and Development Solutions S.L.

import types
import unittest

from flask import Flask

from odata_server.utils.http import make_response


class HTTPUtilsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask("tests")

    @unittest.mock.patch("odata_server.utils.http.stream_with_context")
    @unittest.mock.patch("odata_server.utils.http.Response")
    def test_make_response(self, Response, stream_with_context):
        test_data = (
            (None, None, {"OData-Version": "4.0"}),
            ({}, None, None),
            (
                (c for c in ("{", "}")),
                None,
                {"Content-Type": "application/json;odata.streaming=true"},
            ),
            (None, "etag", {"OData-Version": "4.0"}),
            ({}, "etag2", None),
            (
                (c for c in ("{", "}")),
                "etag3",
                {"Content-Type": "application/json;odata.streaming=true"},
            ),
        )

        for body, etag, headers in test_data:
            with self.subTest(body=body, etag=etag, headers=headers):
                Response.reset_mock()
                stream_with_context.reset_mock()

                make_response(body, status=200, etag=etag, headers=headers)

                Response.assert_called_once_with(
                    unittest.mock.ANY, 200, headers=headers
                )
                if etag is not None:
                    Response().set_etag.assert_called_once_with(etag, weak=True)
                    Response().add_etag.assert_not_called()
                elif isinstance(body, types.GeneratorType):
                    Response().set_etag.assert_not_called()
                    Response().add_etag.assert_not_called()
                else:
                    Response().set_etag.assert_not_called()
                    Response().add_etag.assert_called_once_with(weak=True)

                if isinstance(body, types.GeneratorType):
                    stream_with_context.assert_called_once_with(body)
                else:
                    stream_with_context.assert_not_called()
