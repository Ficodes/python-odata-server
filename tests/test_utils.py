# Copyright (c) 2021 Future Internet Consulting and Development Solutions S.L.

import datetime
import unittest
from unittest.mock import Mock

from odata_server import edm
from odata_server.utils import ODataGrammar, parse_key_predicate, process_collection_filters, process_expand_fields


class UtilsTestCase(unittest.TestCase):

    def test_parse_key_predicate_single_key_property(self):
        test_data = (
            ("(5)", {"ID": 5}),
            ("(true)", {"ID": True}),
            ("(null)", {"ID": None}),
            ("(3.5)", {"ID": 3.5}),
            ("('5')", {"ID": "5"}),
            ("(ID=5)", {"ID": 5}),
            ("(ID=2021-10-20)", {"ID": datetime.datetime(2021, 10, 20, 0, 0, tzinfo=datetime.timezone.utc)}),
        )
        for predicate, expected in test_data:
            with self.subTest(predicate=predicate):
                EntityType = Mock(
                    key_properties=("ID",)
                )
                key_predicate = ODataGrammar("keyPredicate").parse_all(predicate)
                self.assertEqual(parse_key_predicate(EntityType, key_predicate), expected)

    def test_parse_key_predicate_compound_key_property(self):
        test_data = (
            ("(Prop1=5,Prop2=false)", {"Prop1": 5, "Prop2": False}),
            ("(Prop2=5,Prop1=false)", {"Prop1": False, "Prop2": 5}),
        )
        for predicate, expected in test_data:
            with self.subTest(predicate=predicate):
                EntityType = Mock(
                    key_properties=("Prop1", "Prop2")
                )
                key_predicate = ODataGrammar("keyPredicate").parse_all(predicate)
                self.assertEqual(parse_key_predicate(EntityType, key_predicate), expected)

    def test_parse_key_predicate_errors(self):
        test_data = (
            ("(ID=5,Prop2=3)", False),
            ("(@Price)", False),  # Not Supported
            ("(5)", True),
            ("(ID=5)", True),  # Missing some key properties
            ("(ID=5,ID=6,Prop2=3)", True),  # Duplicated key property
            ("(ID=@Price,Prop2=3)", True),  # Not Supported
        )
        for predicate, compound in test_data:
            with self.subTest(predicate=predicate):
                EntityType = Mock(
                    key_properties=["ID"]
                )
                if compound:
                    EntityType.key_properties.append("Prop2")

                key_predicate = ODataGrammar("keyPredicate").parse_all(predicate)
                self.assertRaises(Exception, parse_key_predicate, EntityType, key_predicate)

    def test_process_expand_fields(self):
        test_data = (
            (
                "empty value and no virtual entity",
                {},
                "",
                False,
                {}
            ),
            (
                "empty value (virtual entities)",
                {"prop1", "prop2", "prop3", "prop4"},
                "",
                False,
                {}
            ),
            (
                "list of fields (expanding a virtual entity, single value)",
                {"prop1", "prop2"},
                "prop2",
                False,
                {"prop2": 1}
            ),
            (
                "star (expanding all virtual entities)",
                {"prop1", "prop2", "prop4"},
                "*",
                False,
                {"prop1": 1, "prop2": 1, "prop4": 1}
            ),
            (
                "star (expanding all virtual entities, nested virtual entities)",
                {"prop2", "prop4"},
                "*",
                True,
                {"prop2.attr1": 1, "prop2.attr2": 1, "prop4.attr1": 1, "prop4.attr2": 1}
            ),
            (
                "list of fields (expanding a virtual entity, nested virtual entities, single value)",
                {"prop1", "prop2"},
                "prop2",
                True,
                {"prop2.attr1": 1, "prop2.attr2": 1}
            ),
            (
                "list of fields (expanding a virtual entity and all nested virtual entities, single value)",
                {"prop1", "prop2"},
                "prop2($expand=*)",
                True,
                {"prop2": 1}
            ),
            (
                "list of fields (expanding a virtual entity, collection value)",
                {"prop1", "prop4"},
                "prop4",
                False,
                {"prop4": 1}
            ),
            (
                "list of fields (expanding a virtual entity, nested virtual entities, collection value)",
                {"prop1", "prop4"},
                "prop4",
                True,
                {"prop4.attr1": 1, "prop4.attr2": 1}
            ),
            (
                "list of fields (expanding an entity on another mongo collection)",
                {"prop2"},
                "prop1",
                False,
                {}
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
                entity_set = edm.EntitySet({"Name": "A", "EntityType": "ODataDemo.Product"})
                entity_set.bindings = {
                    "prop2": edm.EntitySet({"Name": "Categories", "EntityType": "ODataDemo.Category"})
                }
                entity_set.bindings["prop2"].bindings = {}
                entity_set.entity_type = edm.EntityType({"Name": "Product"})
                entity_set.entity_type.virtual_entities = virtual_entities
                entity_set.entity_type.navproperties = {}
                for prop, prop_type in navproperties:
                    navprop = edm.NavigationProperty({"Name": prop, "Type": prop_type if prop in ("prop1", "prop2") else "Collection({})".format(prop_type)})
                    navprop.entity_type = edm.EntityType({
                        "Name": prop_type,
                        "Properties": [
                            {"Name": "ID", "Type": "Edm.Int32"},
                            {"Name": "attr1", "Type": "Edm.String"},
                            {"Name": "attr2", "Type": "Edm.String"},
                        ]
                    })
                    navprop.entity_type.key_properties = ("ID",)
                    navprop.entity_type.virtual_entities = set()
                    if nested:
                        navprop.entity_type.NavigationProperties.append(
                            edm.NavigationProperty({"Name": "A", "Type": "ODataDemo.Product"})
                        )
                        navprop.entity_type.navproperties = {
                            "A": navprop.entity_type.NavigationProperties[0]
                        }
                        navprop.entity_type.navproperties["A"].iscollection = False
                        navprop.entity_type.navproperties["A"].entity_type = entity_set.entity_type
                        navprop.entity_type.virtual_entities = {"A"}
                    navprop.iscollection = prop in ("prop3", "prop4")
                    entity_set.entity_type.navproperties[prop] = navprop
                entity_set.entity_type.key_properties = ("ID",)
                projection = {}
                process_expand_fields(entity_set, entity_set.entity_type, expand_value, projection)
                self.assertEqual(projection, expected)

    def test_process_expand_fields_error(self):
        test_data = (
            (
                "list of fields (no virtual entity, no normal navigation property)",
                {},
                "Prop1",
                {}
            ),
        )
        for label, virtual_entities, expand_value, expected in test_data:
            with self.subTest(msg=label):
                entity_set = edm.EntitySet({"Name": "A", "EntityType": "ODataDemo.Product"})
                entity_set.entity_type = edm.EntityType({"Name": "Product"})
                entity_set.entity_type.virtual_entities = virtual_entities
                entity_set.entity_type.navproperties = {
                    prop: edm.NavigationProperty({"Name": prop, "Type": prop_type})
                    for prop_type, prop in virtual_entities.items()
                }
                entity_set.entity_type.key_properties = ("ID",)
                projection = {}
                self.assertRaises(Exception, process_expand_fields, entity_set, expand_value, projection)

    def test_process_collection_filters(self):
        test_data = (
            (
                "ID eq '4'",
                {"ID": {"$eq": "4"}}
            ),
            (
                "ID lt 2021-11-29",
                {"ID": {"$lt": datetime.datetime(2021, 11, 29, 0, 0, tzinfo=datetime.timezone.utc)}}
            ),
            (
                "ID le 10",
                {"ID": {"$lte": 10}}
            ),
            (
                "ID gt 10",
                {"ID": {"$gt": 10}}
            ),
            (
                "ID ge 10",
                {"ID": {"$gte": 10}}
            ),
            (
                " %20ID ne 3.4",
                {"ID": {"$ne": 3.4}}
            ),
            (
                "ID eq '''a''b'",
                {"ID": {"$eq": "'a'b"}}
            ),
            (
                "ID in ('a', 'b')",
                {"ID": {"$in": ["a", "b"]}}
            ),
            (
                "ID in ('a', 'b') and client_bar_code eq null",
                {
                    "ID": {"$in": ["a", "b"]},
                    "client_bar_code": {"$eq": None},
                }
            ),
            (
                "ID eq%20%27%5B%5D%27",
                {"ID": {"$eq": "[]"}}
            ),
            (
                "client_bar_code eq null and client_references eq []",
                {
                    "client_bar_code": {"$eq": None},
                    "client_references": {"$eq": []}
                }
            ),
            (
                "client_bar_code eq null or is_nulled eq true",
                {
                    "$or": [
                        {"client_bar_code": {"$eq": None}},
                        {"is_nulled": {"$eq": True}},
                    ]
                }
            ),
            (
                "client_bar_code eq null or is_nulled eq true or category in (1, 2)",
                {
                    "$or": [
                        {"client_bar_code": {"$eq": None}},
                        {"is_nulled": {"$eq": True}},
                        {"category": {"$in": [1, 2]}},
                    ],
                }
            ),
            (
                "client_bar_code eq null or is_nulled eq true and category in (1, 2) or D eq 1",
                {
                    "$or": [
                        {"client_bar_code": {"$eq": None}},
                        {
                            "is_nulled": {"$eq": True},
                            "category": {
                                "$in": [1, 2]
                            }
                        },
                        {"D": {"$eq": 1}},
                    ],
                }
            ),
            (
                "(client_bar_code eq null or is_nulled eq true) and (category in (1, 2))",
                {
                    "$or": [
                        {"client_bar_code": {"$eq": None}},
                        {"is_nulled": {"$eq": True}},
                    ],
                    "category": {
                        "$in": [1, 2]
                    }
                }
            ),
            (
                "(A eq 1 and B gt 10 or is_nulled eq true) or category in (1, 2)",
                {
                    "$or": [
                        {"A": {"$eq": 1}, "B": {"$gt": 10}},
                        {"is_nulled": {"$eq": True}},
                        {"category": {
                            "$in": [1, 2]
                        }}
                    ]
                }
            ),
            (
                "(A eq 1 or B gt 10 and is_nulled eq true) or (C in (1, 2) and D eq true)",
                {
                    "$or": [
                        {"A": {"$eq": 1}},
                        {"B": {"$gt": 10}, "is_nulled": {"$eq": True}},
                        {"C": {"$in": [1, 2]}, "D": {"$eq": True}},
                    ]
                }
            ),
            (
                "(A eq 1 and B gt 10) and (C in (1, 2) and D eq true)",
                {
                    "A": {"$eq": 1},
                    "B": {"$gt": 10},
                    "C": {"$in": [1, 2]},
                    "D": {"$eq": True},
                }
            ),
        )

        for expr, expected in test_data:
            with self.subTest(expr=expr):
                filters = {}
                process_collection_filters(expr, filters, {})
                self.assertEqual(filters, expected)


if __name__ == "__main__":
    unittest.main()
