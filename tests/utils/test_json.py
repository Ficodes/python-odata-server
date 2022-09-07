# Copyright (c) 2022 Future Internet Consulting and Development Solutions S.L.

import json
import unittest
from types import SimpleNamespace

import flask

from odata_server.utils.json import generate_collection_response


def view():
    pass


class JSONTestCase(unittest.TestCase):
    def test_generate_collection_response(self):
        app = flask.Flask(__name__)
        app.add_url_rule("/Product", view_func=view, endpoint="odata.Product")
        test_data = (
            ("empty resultset", (), False),
            ("one result", (1,), False),
            ("several results", (1, 2, 3, 4), False),
            ("full page (no next page)", (1, 2, 3, 4, 5), False),
            ("full page (with next page)", (1, 2, 3, 4, 5, 6), True),
        )
        RootEntitySet = SimpleNamespace(Name="Product")
        for label, results, hasnext in test_data:
            with self.subTest(msg=label):
                prepare = unittest.mock.Mock(
                    side_effect=(
                        {"a": "1"},
                        {"b": "2"},
                        {"c": "3"},
                        {"d": "4"},
                        {"e": "5"},
                    )
                )
                generator = generate_collection_response(
                    iter(results),
                    0,
                    5,
                    prepare,
                    odata_context="a",
                    prepare_kwargs={"RootEntitySet": RootEntitySet},
                )
                with app.test_request_context():
                    body = b"".join(generator)
                data = json.loads(body)
                self.assertTrue(len(data["value"]) <= 5)
                if hasnext:
                    self.assertIn("@odata.nextLink", data)
