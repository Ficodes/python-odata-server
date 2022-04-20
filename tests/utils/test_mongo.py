# Copyright (c) 2022 Future Internet Consulting and Development Solutions S.L.

import unittest

from odata_server import edm
from odata_server.utils.mongo import build_initial_projection


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
