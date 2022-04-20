# Copyright (c) 2022 Future Internet Consulting and Development Solutions S.L.

import unittest

from odata_server import edm
from odata_server.utils.mongo import build_initial_projection, get_mongo_prefix


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


class MongoUtilsTestCase(unittest.TestCase):

    def test_build_initial_projection(self):
        test_data = (
            (
                ENTITY_TYPE_1,
                "",
                "",
                True,
                (
                    {
                        "_id": 0,
                        "uuid": 1,
                        "ID": 1,
                        "description": 1,
                    },
                    [],
                )
            ),
            (
                ENTITY_TYPE_1,
                "*",
                "",
                True,
                (
                    {
                        "_id": 0,
                        "uuid": 1,
                        "ID": 1,
                        "description": 1,
                    },
                    [],
                )
            ),
            (
                ENTITY_TYPE_1,
                "description",
                "",
                True,
                (
                    {
                        "_id": 0,
                        "uuid": 1,
                        "description": 1,
                    },
                    [],
                )
            ),
            (
                ENTITY_TYPE_1,
                "description",
                "",
                False,
                (
                    {
                        "_id": 0,
                        "uuid": 1,
                        "ID": 1,
                        "description": 1,
                    },
                    ["ID"],
                )
            ),
            (
                ENTITY_TYPE_1,
                "description",
                "products",
                True,
                (
                    {
                        "_id": 0,
                        "uuid": 1,
                        "products.description": 1,
                    },
                    [],
                )
            ),
            (
                ENTITY_TYPE_1,
                "description",
                "products",
                False,
                (
                    {
                        "_id": 0,
                        "uuid": 1,
                        "ID": 1,
                        "products.description": 1,
                    },
                    ["ID"],
                )
            ),
        )
        for entity_type, select, prefix, anonymous, expected_result in test_data:
            with self.subTest(select=select, prefix=prefix, anonymous=anonymous):
                entity_type = edm.EntityType(entity_type)
                edm.process_entity_type(entity_type)

                projection = build_initial_projection(entity_type, select=select, prefix=prefix, anonymous=anonymous)

                self.assertEqual(projection, expected_result)

    def test_get_mongo_prefix(self):
        List = edm.EntityType({
            "Name": "List",
        })
        Product = edm.EntityType({
            "Name": "Product",
        })
        NavigationProperty = edm.NavigationProperty({
            "Name": "products",
            "Type": "Product",
        })
        NavigationProperty.entity_type = Product
        RootEntitySet = edm.EntitySet({
            "Name": "List",
            "EntityType": "List",
        })
        RootEntitySet.entity_type = List

        test_data = (
            ("", None, False, None, ""),
            ("", NavigationProperty, False, None, ""),
            ("", NavigationProperty, True, None, "products"),
            ("products", None, False, None, "products"),
            ("products", None, False, 0, "products.0"),
            ("lists", NavigationProperty, False, None, "lists"),
            ("lists", NavigationProperty, True, None, "lists.products"),
            ("lists", NavigationProperty, True, 0, "lists.products.0"),
        )
        for prefix, subject, isembedded, seq, expected_result in test_data:
            with self.subTest(prefix=prefix, seq=seq):
                RootEntitySet.prefix = prefix
                NavigationProperty.isembedded = isembedded
                if subject is None:
                    subject = RootEntitySet

                result = get_mongo_prefix(RootEntitySet, subject, seq)

                self.assertEqual(result, expected_result)
