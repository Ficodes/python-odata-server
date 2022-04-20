# Copyright (c) 2022 Future Internet Consulting and Development Solutions S.L.

from copy import deepcopy
import unittest

from odata_server import edm
from odata_server.utils.common import (
    build_initial_projection, crop_result, extract_id_value, format_literal,
    format_key_predicate
)


ENTITY_TYPE_1 = {
    "Name": "Product",
    "Key": [
        {"Name": "ID"},
    ],
    "Properties": [
        {"Name": "ID", "Type": "Edm.String", "Nullable": False},
        {"Name": "description", "Type": "Edm.String", "Nullable": False},
    ],
}


class CommonUtilsTestCase(unittest.TestCase):

    def test_build_initial_projection(self):
        test_data = (
            (
                ENTITY_TYPE_1,
                "",
                "",
                {
                    "_id": 0,
                    "uuid": 1,
                    "ID": 1,
                    "description": 1,
                },
            ),
            (
                ENTITY_TYPE_1,
                "*",
                "",
                {
                    "_id": 0,
                    "uuid": 1,
                    "ID": 1,
                    "description": 1,
                },
            ),
            (
                ENTITY_TYPE_1,
                "description",
                "",
                {
                    "_id": 0,
                    "uuid": 1,
                    "description": 1,
                },
            ),
            (
                ENTITY_TYPE_1,
                "description",
                "products",
                {
                    "_id": 0,
                    "uuid": 1,
                    "products.description": 1,
                },
            ),
        )
        for entity_type, select, prefix, expected_result in test_data:
            with self.subTest():
                entity_type = edm.EntityType(entity_type)
                edm.process_entity_type(entity_type)

                projection = build_initial_projection(entity_type, select=select, prefix=prefix)

                self.assertEqual(projection, expected_result)

    def test_crop_result(self):
        data = {
            "ID": 1,
            "products": {
                "name": "product1",
                "categories": {
                    "name": "cat1",
                },
            },
            "Seq": 0,
        }
        test_data = (
            ("", data),
            (
                "products",
                {
                    "ID": 1,
                    "Seq": 0,
                    "name": "product1",
                    "categories": {
                        "name": "cat1",
                    },
                },
            ),
            (
                "products.tags",
                {
                    "ID": 1,
                    "Seq": 0,
                },
            ),
            (
                "products.categories",
                {
                    "ID": 1,
                    "Seq": 0,
                    "name": "cat1",
                },
            ),
        )
        for prefix, expected_result in test_data:
            with self.subTest(prefix=prefix):
                self.assertEqual(crop_result(deepcopy(data), prefix), expected_result)

    def test_format_literal(self):
        test_data = (
            (True, "true"),
            (False, "false"),
            (5, "5"),
            ("a", "'a'"),
        )

        for value, expected_value in test_data:
            with self.subTest(value=value):
                self.assertEqual(format_literal(value), expected_value)

    def test_format_key_predicate(self):
        test_data = (
            ({"id": 5}, "5"),
            ({"type": "a", "seq": 1, "odd": True}, "type='a',seq=1,odd=true"),
        )

        for value, expected_value in test_data:
            with self.subTest(value=value):
                self.assertEqual(format_key_predicate(value), expected_value)

    def test_extract_id_value(self):
        entity_type = unittest.mock.Mock(
            key_properties=set(("a", "b"))
        )
        self.assertEqual(
            extract_id_value(
                entity_type,
                {
                    "a": 1,
                    "b": 2,
                    "c": 3,
                },
            ),
            {
                "a": 1,
                "b": 2,
            },
        )

    def test_extract_id_value_key_error(self):
        entity_type = unittest.mock.Mock(
            key_properties=set(("a", "b"))
        )
        with self.assertRaises(KeyError):
            extract_id_value(
                entity_type,
                {
                    "a": 1,
                },
            )
