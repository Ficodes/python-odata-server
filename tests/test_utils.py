# Copyright (c) 2021-2022 Future Internet Consulting and Development Solutions S.L.

import datetime
import unittest

from flask import Flask

from odata_server import edm
from odata_server.utils import (
    get_collection,
    prepare_anonymous_result,
    prepare_entity_set_result,
    process_collection_filters,
    process_expand_fields,
)


class UtilsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask("tests")

    def test_process_expand_fields(self):
        test_data = (
            ("empty value and no virtual entity", {}, "", False, {}),
            (
                "empty value (virtual entities)",
                {"prop1", "prop2", "prop3", "prop4"},
                "",
                False,
                {},
            ),
            (
                "list of fields (expanding a virtual entity, single value)",
                {"prop1", "prop2"},
                "prop2",
                False,
                {"prop2": 1},
            ),
            (
                "star (expanding all virtual entities)",
                {"prop1", "prop2", "prop4"},
                "*",
                False,
                {"prop1": 1, "prop2": 1, "prop4": 1},
            ),
            (
                "star (expanding all virtual entities, nested virtual entities)",
                {"prop2", "prop4"},
                "*",
                True,
                {
                    "prop2.attr1": 1,
                    "prop2.attr2": 1,
                    "prop4.attr1": 1,
                    "prop4.attr2": 1,
                },
            ),
            (
                "list of fields (expanding a virtual entity, nested virtual entities, single value)",
                {"prop1", "prop2"},
                "prop2",
                True,
                {"prop2.attr1": 1, "prop2.attr2": 1},
            ),
            (
                "list of fields (expanding a virtual entity and all nested virtual entities, single value)",
                {"prop1", "prop2"},
                "prop2($expand=*)",
                True,
                {"prop2": 1},
            ),
            (
                "list of fields (expanding a virtual entity, collection value)",
                {"prop1", "prop4"},
                "prop4",
                False,
                {"prop4": 1},
            ),
            (
                "list of fields (expanding a virtual entity, nested virtual entities, collection value)",
                {"prop1", "prop4"},
                "prop4",
                True,
                {"prop4.attr1": 1, "prop4.attr2": 1},
            ),
            (
                "list of fields (expanding an entity on another mongo collection)",
                {"prop2"},
                "prop1",
                False,
                {},
            ),
        )

        navproperties = (
            ("prop1", "Product"),
            ("prop2", "Category"),
            ("prop4", "Trips"),
            ("prop4", "Photo"),
        )
        for label, virtual_entities, expand_value, nested, expected in test_data:
            with self.subTest(msg=label):
                entity_set = edm.EntitySet(
                    {"Name": "A", "EntityType": "ODataDemo.Product"}
                )
                entity_set.bindings = {
                    "prop2": edm.EntitySet(
                        {"Name": "Categories", "EntityType": "ODataDemo.Category"}
                    )
                }
                entity_set.bindings["prop2"].bindings = {}
                entity_set.entity_type = edm.EntityType({"Name": "Product"})
                entity_set.entity_type.virtual_entities = virtual_entities
                entity_set.entity_type.navproperties = {}
                for prop, prop_type in navproperties:
                    navprop = edm.NavigationProperty(
                        {
                            "Name": prop,
                            "Type": prop_type
                            if prop in ("prop1", "prop2")
                            else "Collection({})".format(prop_type),
                        }
                    )
                    navprop.entity_type = edm.EntityType(
                        {
                            "Name": prop_type,
                            "Properties": [
                                {"Name": "ID", "Type": "Edm.Int32"},
                                {"Name": "attr1", "Type": "Edm.String"},
                                {"Name": "attr2", "Type": "Edm.String"},
                            ],
                        }
                    )
                    navprop.entity_type.key_properties = ("ID",)
                    navprop.entity_type.virtual_entities = set()
                    if nested:
                        navprop.entity_type.NavigationProperties.append(
                            edm.NavigationProperty(
                                {"Name": "A", "Type": "ODataDemo.Product"}
                            )
                        )
                        navprop.entity_type.navproperties = {
                            "A": navprop.entity_type.NavigationProperties[0]
                        }
                        navprop.entity_type.navproperties["A"].iscollection = False
                        navprop.entity_type.navproperties[
                            "A"
                        ].entity_type = entity_set.entity_type
                        navprop.entity_type.virtual_entities = {"A"}
                    navprop.iscollection = prop in ("prop3", "prop4")
                    entity_set.entity_type.navproperties[prop] = navprop
                entity_set.entity_type.key_properties = ("ID",)
                projection = {}
                process_expand_fields(
                    entity_set, entity_set.entity_type, expand_value, projection
                )
                self.assertEqual(projection, expected)

    def test_process_expand_fields_error(self):
        test_data = (
            (
                "list of fields (no virtual entity, no normal navigation property)",
                {},
                "Prop1",
                {},
            ),
        )
        for label, virtual_entities, expand_value, expected in test_data:
            with self.subTest(msg=label):
                entity_set = edm.EntitySet(
                    {"Name": "A", "EntityType": "ODataDemo.Product"}
                )
                entity_set.entity_type = edm.EntityType({"Name": "Product"})
                entity_set.entity_type.virtual_entities = virtual_entities
                entity_set.entity_type.navproperties = {
                    prop: edm.NavigationProperty({"Name": prop, "Type": prop_type})
                    for prop_type, prop in virtual_entities.items()
                }
                entity_set.entity_type.key_properties = ("ID",)
                projection = {}
                self.assertRaises(
                    Exception,
                    process_expand_fields,
                    entity_set,
                    expand_value,
                    projection,
                )

    def test_process_collection_filters(self):
        test_data = (
            ("ID eq '4'", {"ID": {"$eq": "4"}}),
            ("ID lt 2021-11-29", {"ID": {"$lt": "2021-11-29"}}),
            (
                "ID gt 2022-02-15T10:40:30Z",
                {
                    "ID": {
                        "$gt": datetime.datetime(
                            2022, 2, 15, 10, 40, 30, 0, tzinfo=datetime.timezone.utc
                        )
                    }
                },
            ),
            (
                "ID lt 2022-02-15T10:40:30.545Z",
                {
                    "ID": {
                        "$lt": datetime.datetime(
                            2022,
                            2,
                            15,
                            10,
                            40,
                            30,
                            545000,
                            tzinfo=datetime.timezone.utc,
                        )
                    }
                },
            ),
            (
                "ID lt 2022-02-15T10%3A40%3A30Z",
                {
                    "ID": {
                        "$lt": datetime.datetime(
                            2022, 2, 15, 10, 40, 30, tzinfo=datetime.timezone.utc
                        )
                    }
                },
            ),
            ("ID le 10", {"ID": {"$lte": 10}}),
            ("ID gt 10", {"ID": {"$gt": 10}}),
            ("ID ge 10", {"ID": {"$gte": 10}}),
            # This kind of test is now not required as parse_qs removes leading and trailing spaces
            # (
            #     " %20ID ne 3.4",
            #     {"ID": {"$ne": 3.4}}
            # ),
            ("ID eq '''a''b'", {"ID": {"$eq": "'a'b"}}),
            ("ID in ('a', 'b')", {"ID": {"$in": ["a", "b"]}}),
            (
                "ID in ('a', 'b') and client_bar_code eq null",
                {
                    "ID": {"$in": ["a", "b"]},
                    "client_bar_code": {"$eq": None},
                },
            ),
            (
                "(ReleaseDate ge 2022-02-06T21:00:00%2B02:00 and ReleaseDate le 2022-02-13T23:00:00Z)",
                {
                    "ReleaseDate": {
                        "$lte": datetime.datetime(
                            2022, 2, 13, 23, 0, tzinfo=datetime.timezone.utc
                        ),
                        "$gte": datetime.datetime(
                            2022, 2, 6, 19, 0, tzinfo=datetime.timezone.utc
                        ),
                    }
                },
            ),
            (
                "(ReleaseDate le 2022-02-13T23:00:00Z and ReleaseDate le 2022-02-06T23:00:00Z)",
                {
                    "ReleaseDate": {
                        "$lte": datetime.datetime(
                            2022, 2, 6, 23, 0, tzinfo=datetime.timezone.utc
                        ),
                    }
                },
            ),
            (
                # Check order does not affect this
                "(ReleaseDate le 2022-02-06T23:00:00Z and ReleaseDate le 2022-02-13T23:00:00Z)",
                {
                    "ReleaseDate": {
                        "$lte": datetime.datetime(
                            2022, 2, 6, 23, 0, tzinfo=datetime.timezone.utc
                        ),
                    }
                },
            ),
            (
                "(ReleaseDate ge 2022-02-06T23:00:00Z and ReleaseDate ge 2022-02-13T23:00:00Z)",
                {
                    "ReleaseDate": {
                        "$gte": datetime.datetime(
                            2022, 2, 13, 23, 0, tzinfo=datetime.timezone.utc
                        ),
                    }
                },
            ),
            (
                # Check order does not affect this
                "(ReleaseDate ge 2022-02-13T23:00:00Z and ReleaseDate ge 2022-02-06T23:00:00Z)",
                {
                    "ReleaseDate": {
                        "$gte": datetime.datetime(
                            2022, 2, 13, 23, 0, tzinfo=datetime.timezone.utc
                        ),
                    }
                },
            ),
            ("ID eq%20%27%5B%5D%27", {"ID": {"$eq": "[]"}}),
            (
                "hassubset(colors, ['green', 'purple'])",
                {"colors": {"$all": ["green", "purple"]}},
            ),
            (
                "hassubset(colors, ['green', 5, [1], {\"a\": 'b'}])",
                {"colors": {"$all": ["green", 5, [1], {"a": "b"}]}},
            ),
            (
                "contains(ID, '001522abc%5Bs%5B')",
                {"ID": {"$regex": "001522abc\\[s\\["}},
            ),
            (
                "contains(ID, '001522abc%5Bs%5B') eq true",
                {"ID": {"$regex": "001522abc\\[s\\["}},
            ),
            (
                "contains(ID, '001522abc%5Bs%5B') eq false",
                {"ID": {"$regex": "(?!001522abc\\[s\\[)"}},
            ),
            (
                "contains(ID, '001522abc%5Bs%5B') or B eq '3'",
                {
                    "$or": [
                        {"ID": {"$regex": "001522abc\\[s\\["}},
                        {"B": {"$eq": "3"}},
                    ]
                },
            ),
            (
                "B eq null and startswith(ID, '001522abc%5Bs%5B')",
                {
                    "ID": {"$regex": "^001522abc\\[s\\["},
                    "B": {"$eq": None},
                },
            ),
            (
                "startswith(ID, '001522abc%5Bs%5B') eq true and B eq null",
                {
                    "ID": {"$regex": "^001522abc\\[s\\["},
                    "B": {"$eq": None},
                },
            ),
            (
                "startswith(ID, '001522abc%5Bs%5B') eq false and B eq null",
                {
                    "ID": {"$regex": "^(?!001522abc\\[s\\[)"},
                    "B": {"$eq": None},
                },
            ),
            (
                "startswith(ID, '001522abc%5Bs%5B') eq 5 and B eq null",
                {
                    "ID": {"$regex": "^(?!001522abc\\[s\\[)"},
                    "B": {"$eq": None},
                },
            ),
            (
                "client_bar_code eq null and client_references eq []",
                {"client_bar_code": {"$eq": None}, "client_references": {"$eq": []}},
            ),
            (
                "(B eq null or endswith(ID, '001522abc%5Bs%5B'))",
                {
                    "$or": [
                        {"B": {"$eq": None}},
                        {"ID": {"$regex": "001522abc\\[s\\[$"}},
                    ]
                },
            ),
            (
                "client_bar_code eq null or is_nulled eq true",
                {
                    "$or": [
                        {"client_bar_code": {"$eq": None}},
                        {"is_nulled": {"$eq": True}},
                    ]
                },
            ),
            (
                "client_bar_code eq null or is_nulled eq true or category in (1, 2)",
                {
                    "$or": [
                        {"client_bar_code": {"$eq": None}},
                        {"is_nulled": {"$eq": True}},
                        {"category": {"$in": [1, 2]}},
                    ],
                },
            ),
            (
                "client_bar_code eq null or is_nulled eq true and category in (1, 2) or D eq 1",
                {
                    "$or": [
                        {"client_bar_code": {"$eq": None}},
                        {"is_nulled": {"$eq": True}, "category": {"$in": [1, 2]}},
                        {"D": {"$eq": 1}},
                    ],
                },
            ),
            (
                "(client_bar_code eq null or is_nulled eq true) and (category in (1, 2))",
                {
                    "$or": [
                        {"client_bar_code": {"$eq": None}},
                        {"is_nulled": {"$eq": True}},
                    ],
                    "category": {"$in": [1, 2]},
                },
            ),
            (
                "(A eq 1 and B gt 10 or is_nulled eq true) or category in (1, 2)",
                {
                    "$or": [
                        {"A": {"$eq": 1}, "B": {"$gt": 10}},
                        {"is_nulled": {"$eq": True}},
                        {"category": {"$in": [1, 2]}},
                    ]
                },
            ),
            (
                "(A eq 1 or B gt 10 and is_nulled eq true) or (C in (1, 2) and D eq true)",
                {
                    "$or": [
                        {"A": {"$eq": 1}},
                        {"B": {"$gt": 10}, "is_nulled": {"$eq": True}},
                        {"C": {"$in": [1, 2]}, "D": {"$eq": True}},
                    ]
                },
            ),
            (
                "(A eq 1 and B gt 10) and (C in (1, 2) and D eq true)",
                {
                    "A": {"$eq": 1},
                    "B": {"$gt": 10},
                    "C": {"$in": [1, 2]},
                    "D": {"$eq": True},
                },
            ),
            (
                "(A eq 1) and A eq 1",
                {
                    "A": {"$eq": 1},
                },
            ),
            (
                "(A eq 1 and B eq 3) and A eq 1",
                {
                    "A": {"$eq": 1},
                    "B": {"$eq": 3},
                },
            ),
            (
                "A in (1, 2, 3, 3)",
                {
                    "A": {"$in": [1, 2, 3]},
                },
            ),
            (
                "A in (1, 2, 3) and A in (1, 2)",
                {
                    "A": {"$in": [1, 2]},
                },
            ),
        )

        for expr, expected in test_data:
            with self.subTest(expr=expr):
                filters = {}
                process_collection_filters(expr, "", filters, {})
                self.assertEqual(filters, expected)

    @unittest.mock.patch("odata_server.utils.parse_qs", return_value={})
    @unittest.mock.patch(
        "odata_server.utils.url_for", new=unittest.mock.Mock(return_value="/$metadata")
    )
    @unittest.mock.patch(
        "odata_server.utils.flask.url_for",
        new=unittest.mock.Mock(return_value="/Products"),
    )
    def test_get_collection(self, parse_qs):
        mongo = unittest.mock.Mock()
        mongo.get_collection().find().skip().limit.return_value = iter(
            (
                {
                    "ID": 1,
                    "uuid": "abc",
                },
            )
        )
        RootEntitySet = edm.EntitySet(
            {
                "Name": "Products",
                "EntityType": "Product",
            }
        )
        RootEntitySet.prefix = ""
        RootEntitySet.mongo_collection = "product"
        RootEntitySet.entity_type = edm.EntityType(
            {
                "Name": "Product",
                "Key": [
                    {"Name": "ID"},
                ],
                "Properties": [
                    {"Name": "ID", "Type": "Edm.String", "Nullable": False},
                ],
            }
        )
        edm.process_entity_type(RootEntitySet.entity_type)
        subject = RootEntitySet
        prefers = {
            "maxpagesize": 20,
        }
        with self.app.test_request_context():
            get_collection(mongo, RootEntitySet, subject, prefers)

    @unittest.mock.patch("odata_server.utils.parse_qs", return_value={})
    @unittest.mock.patch(
        "odata_server.utils.parse_orderby",
        new=unittest.mock.Mock(return_value=(("ID", 1),)),
    )
    @unittest.mock.patch(
        "odata_server.utils.url_for", new=unittest.mock.Mock(return_value="/$metadata")
    )
    @unittest.mock.patch(
        "odata_server.utils.flask.url_for",
        new=unittest.mock.Mock(return_value="/Products"),
    )
    def test_get_collection_orderby(self, parse_qs):
        mongo = unittest.mock.Mock()
        mongo.get_collection().find().sort().skip().limit.return_value = iter(
            (
                {
                    "ID": 1,
                    "uuid": "abc",
                },
            )
        )
        RootEntitySet = edm.EntitySet(
            {
                "Name": "Products",
                "EntityType": "Product",
            }
        )
        RootEntitySet.prefix = ""
        RootEntitySet.mongo_collection = "product"
        RootEntitySet.entity_type = edm.EntityType(
            {
                "Name": "Product",
                "Key": [
                    {"Name": "ID"},
                ],
                "Properties": [
                    {"Name": "ID", "Type": "Edm.String", "Nullable": False},
                ],
            }
        )
        edm.process_entity_type(RootEntitySet.entity_type)
        subject = RootEntitySet
        prefers = {
            "maxpagesize": 20,
        }
        with self.app.test_request_context():
            get_collection(mongo, RootEntitySet, subject, prefers)

    @unittest.mock.patch("odata_server.utils.parse_qs", return_value={})
    @unittest.mock.patch(
        "odata_server.utils.url_for", new=unittest.mock.Mock(return_value="/$metadata")
    )
    @unittest.mock.patch(
        "odata_server.utils.flask.url_for",
        new=unittest.mock.Mock(return_value="/Products"),
    )
    def test_get_collection_count(self, parse_qs):
        mongo = unittest.mock.Mock()
        mongo.get_collection().find().skip().limit.return_value = iter(
            (
                {
                    "ID": 1,
                    "uuid": "abc",
                },
            )
        )
        mongo.get_collection().count_documents.return_value = 1
        RootEntitySet = edm.EntitySet(
            {
                "Name": "Products",
                "EntityType": "Product",
            }
        )
        RootEntitySet.prefix = ""
        RootEntitySet.mongo_collection = "product"
        RootEntitySet.entity_type = edm.EntityType(
            {
                "Name": "Product",
                "Key": [
                    {"Name": "ID"},
                ],
                "Properties": [
                    {"Name": "ID", "Type": "Edm.String", "Nullable": False},
                ],
            }
        )
        edm.process_entity_type(RootEntitySet.entity_type)
        subject = RootEntitySet
        prefers = {
            "maxpagesize": 20,
        }
        with self.app.test_request_context():
            get_collection(mongo, RootEntitySet, subject, prefers, count=True)

    @unittest.mock.patch("odata_server.utils.parse_qs", return_value={})
    @unittest.mock.patch(
        "odata_server.utils.url_for", new=unittest.mock.Mock(return_value="/$metadata")
    )
    @unittest.mock.patch(
        "odata_server.utils.flask.url_for",
        new=unittest.mock.Mock(return_value="/Products"),
    )
    def test_get_collection_mongo_prefix_entity(self, parse_qs):
        mongo = unittest.mock.Mock()
        mongo.get_collection().aggregate.return_value = iter(
            (
                {
                    "ID": 1,
                    "uuid": "abc",
                },
            )
        )
        RootEntitySet = edm.EntitySet(
            {
                "Name": "Products",
                "EntityType": "Product",
            }
        )
        RootEntitySet.prefix = "products"
        RootEntitySet.mongo_collection = "product"
        RootEntitySet.entity_type = edm.EntityType(
            {
                "Name": "Product",
                "Key": [
                    {"Name": "ID"},
                ],
                "Properties": [
                    {"Name": "ID", "Type": "Edm.String", "Nullable": False},
                ],
            }
        )
        edm.process_entity_type(RootEntitySet.entity_type)
        subject = RootEntitySet
        prefers = {
            "maxpagesize": 20,
        }
        with self.app.test_request_context():
            get_collection(mongo, RootEntitySet, subject, prefers)

    @unittest.mock.patch("odata_server.utils.parse_qs", return_value={})
    @unittest.mock.patch(
        "odata_server.utils.parse_orderby",
        new=unittest.mock.Mock(return_value=(("ID", 1),)),
    )
    @unittest.mock.patch(
        "odata_server.utils.url_for", new=unittest.mock.Mock(return_value="/$metadata")
    )
    @unittest.mock.patch(
        "odata_server.utils.flask.url_for",
        new=unittest.mock.Mock(return_value="/Products"),
    )
    def test_get_collection_mongo_prefix_entity_orderby(self, parse_qs):
        mongo = unittest.mock.Mock()
        mongo.get_collection().aggregate.return_value = iter(
            (
                {
                    "ID": 1,
                    "uuid": "abc",
                },
            )
        )
        RootEntitySet = edm.EntitySet(
            {
                "Name": "Products",
                "EntityType": "Product",
            }
        )
        RootEntitySet.prefix = "products"
        RootEntitySet.mongo_collection = "product"
        RootEntitySet.entity_type = edm.EntityType(
            {
                "Name": "Product",
                "Key": [
                    {"Name": "ID"},
                ],
                "Properties": [
                    {"Name": "ID", "Type": "Edm.String", "Nullable": False},
                ],
            }
        )
        edm.process_entity_type(RootEntitySet.entity_type)
        subject = RootEntitySet
        prefers = {
            "maxpagesize": 20,
        }
        with self.app.test_request_context():
            get_collection(mongo, RootEntitySet, subject, prefers)

    @unittest.mock.patch("odata_server.utils.parse_qs", return_value={})
    @unittest.mock.patch(
        "odata_server.utils.process_collection_filters",
        new=unittest.mock.Mock(return_value={"Seq": {"$gt": 1}}),
    )
    @unittest.mock.patch(
        "odata_server.utils.url_for", new=unittest.mock.Mock(return_value="/$metadata")
    )
    @unittest.mock.patch(
        "odata_server.utils.flask.url_for",
        new=unittest.mock.Mock(return_value="/Products"),
    )
    def test_get_collection_mongo_prefix_entity_seq_filter(self, parse_qs):
        mongo = unittest.mock.Mock()
        mongo.get_collection().aggregate.return_value = iter(
            (
                {
                    "ID": 1,
                    "uuid": "abc",
                },
            )
        )
        RootEntitySet = edm.EntitySet(
            {
                "Name": "Products",
                "EntityType": "Product",
            }
        )
        RootEntitySet.prefix = "products"
        RootEntitySet.mongo_collection = "product"
        RootEntitySet.entity_type = edm.EntityType(
            {
                "Name": "Product",
                "Key": [
                    {"Name": "ID"},
                ],
                "Properties": [
                    {"Name": "ID", "Type": "Edm.String", "Nullable": False},
                ],
            }
        )
        edm.process_entity_type(RootEntitySet.entity_type)
        subject = RootEntitySet
        prefers = {
            "maxpagesize": 20,
        }
        with self.app.test_request_context():
            get_collection(mongo, RootEntitySet, subject, prefers)

    @unittest.mock.patch("odata_server.utils.parse_qs", return_value={})
    @unittest.mock.patch(
        "odata_server.utils.url_for", new=unittest.mock.Mock(return_value="/$metadata")
    )
    @unittest.mock.patch(
        "odata_server.utils.flask.url_for",
        new=unittest.mock.Mock(return_value="/Products"),
    )
    def test_get_collection_mongo_prefix_entity_count(self, parse_qs):
        mongo = unittest.mock.Mock()
        mongo.get_collection().aggregate.side_effect = (
            iter(
                (
                    {
                        "ID": 1,
                        "uuid": "abc",
                    },
                )
            ),
            iter(({"count": 1},)),
        )
        RootEntitySet = edm.EntitySet(
            {
                "Name": "Products",
                "EntityType": "Product",
            }
        )
        RootEntitySet.prefix = "products"
        RootEntitySet.mongo_collection = "product"
        RootEntitySet.entity_type = edm.EntityType(
            {
                "Name": "Product",
                "Key": [
                    {"Name": "ID"},
                ],
                "Properties": [
                    {"Name": "ID", "Type": "Edm.String", "Nullable": False},
                ],
            }
        )
        edm.process_entity_type(RootEntitySet.entity_type)
        subject = RootEntitySet
        prefers = {
            "maxpagesize": 20,
        }
        with self.app.test_request_context():
            get_collection(mongo, RootEntitySet, subject, prefers, count=True)

    @unittest.mock.patch("odata_server.utils.parse_qs", return_value={})
    @unittest.mock.patch(
        "odata_server.utils.url_for", new=unittest.mock.Mock(return_value="/$metadata")
    )
    @unittest.mock.patch(
        "odata_server.utils.flask.url_for",
        new=unittest.mock.Mock(return_value="/Products"),
    )
    def test_get_collection_mongo_prefix_collection(self, parse_qs):
        mongo = unittest.mock.Mock()
        mongo.get_collection().aggregate.return_value = iter(
            (
                {
                    "ID": 1,
                    "Seq": 0,
                    "uuid": "abc",
                },
            )
        )
        RootEntitySet = edm.EntitySet(
            {
                "Name": "Products",
                "EntityType": "Product",
            }
        )
        RootEntitySet.prefix = "products"
        RootEntitySet.mongo_collection = "product"
        RootEntitySet.entity_type = edm.EntityType(
            {
                "Name": "Product",
                "Key": [
                    {"Name": "ID"},
                    {"Name": "Seq"},
                ],
                "Properties": [
                    {"Name": "ID", "Type": "Edm.String", "Nullable": False},
                    {"Name": "Seq", "Type": "Edm.Int16", "Nullable": False},
                ],
            }
        )
        edm.process_entity_type(RootEntitySet.entity_type)
        subject = RootEntitySet
        prefers = {
            "maxpagesize": 20,
        }
        with self.app.test_request_context():
            get_collection(mongo, RootEntitySet, subject, prefers)

    @unittest.mock.patch("odata_server.utils.crop_result", new=unittest.mock.Mock())
    @unittest.mock.patch("odata_server.utils.expand_result", new=unittest.mock.Mock())
    @unittest.mock.patch(
        "odata_server.utils.add_odata_annotations", new=unittest.mock.Mock()
    )
    def test_prepare_entity_set_result(self):
        result = {}
        RootEntitySet = unittest.mock.Mock()
        expand_details = {}
        prefix = ""
        fields_to_remove = []
        prepare_entity_set_result(
            result, RootEntitySet, expand_details, prefix, fields_to_remove
        )

    @unittest.mock.patch("odata_server.utils.crop_result", new=unittest.mock.Mock())
    @unittest.mock.patch("odata_server.utils.expand_result", new=unittest.mock.Mock())
    def test_prepare_anonymous_result(self):
        result = {}
        RootEntitySet = unittest.mock.Mock()
        expand_details = {}
        prefix = ""
        prepare_anonymous_result(result, RootEntitySet, expand_details, prefix)


if __name__ == "__main__":
    unittest.main()
