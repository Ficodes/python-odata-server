# Copyright (c) 2021-2022 Future Internet Consulting and Development Solutions S.L.

from datetime import datetime, timezone
import math
import unittest
from unittest.mock import Mock

import werkzeug

from odata_server.utils.parse import (
    ODataGrammar, parse_key_predicate, parse_orderby, parse_primitive_literal
)


class ParseUtilsTestCase(unittest.TestCase):

    def test_parse_primitive_literal(self):
        test_data = (
            ("sbyteValue", "-5", -5),
            ("byteValue", "5", 5),
            ("int16Value", "5", 5),
            ("int32Value", "5", 5),
            ("int64Value", "5", 5),
            ("decimalValue", "5e-3", 5e-3),
            ("decimalValue", "INF", math.inf),
            ("decimalValue", "NaN", math.nan),
            ("decimalValue", "-INF", -math.inf),
            ("doubleValue", "5e-3", 5e-3),
            ("doubleValue", "INF", math.inf),
            ("doubleValue", "NaN", math.nan),
            ("doubleValue", "-INF", -math.inf),
            ("singleValue", "5e-3", 5e-3),
            ("singleValue", "INF", math.inf),
            ("singleValue", "NaN", math.nan),
            ("singleValue", "-INF", -math.inf),
            ("booleanValue", "true", True),
            ("nullValue", "null", None),
            ("string", "'hello'", "hello"),
            ("dateTimeOffsetValueInUrl", "2021-10-20T10:00:00.000Z", datetime(2021, 10, 20, 10, 0, tzinfo=timezone.utc)),
            ("dateValue", "2021-10-20", "2021-10-20"),
        )

        for literal_type, value, expected in test_data:
            with self.subTest(literal_type=literal_type, value=value):
                node = Mock(
                    value=value,
                )
                node.name = literal_type

                result = parse_primitive_literal(node)
                if value == "NaN":
                    self.assertTrue(math.isnan(result))
                else:
                    self.assertEqual(result, expected)

    def test_parse_primitive_literal_not_supported(self):
        test_data = (
            "guidValue",
            "duration",
            "timeOfDayValueInUrl",
            "enum",
            "binary",
            "geographyCollection",
            "geographyLineString",
            "geographyMultiLineString",
            "geographyMultiPoint",
            "geographyMultiPolygon",
            "geographyPoint",
            "geographyPolygon",
            "geometryCollection",
            "geometryLineString",
            "geometryMultiLineString",
            "geometryMultiPoint",
            "geometryMultiPolygon",
            "geometryPoint",
            "geometryPolygon",
        )

        for literal_type in test_data:
            with self.subTest(literal_type=literal_type):
                node = Mock(
                    value="anything",
                )
                node.name = literal_type

                with self.assertRaises(werkzeug.exceptions.NotImplemented):
                    parse_primitive_literal(node)

    def test_parse_key_predicate_single_key_property(self):
        test_data = (
            ("(5)", {"ID": 5}),
            ("(true)", {"ID": True}),
            ("(null)", {"ID": None}),
            ("(3.5)", {"ID": 3.5}),
            ("('5')", {"ID": "5"}),
            ("(ID=5)", {"ID": 5}),
            ("(ID=2021-10-20)", {"ID": "2021-10-20"}),
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

    def test_parse_orderby(self):
        test_data = (
            ("", []),
            ("BaseRate asc", [("BaseRate", 1)]),
            ("Rating desc,BaseRate", [("Rating", -1), ("BaseRate", 1)]),
            # ("Rating desc,geo.distance(Location, geography'POINT(-122.131577 47.678581)') asc", []),
            # ("search.score() desc,Rating desc,geo.distance(Location, geography'POINT(-122.131577 47.678581)') asc", []),
        )

        for value, expected in test_data:
            with self.subTest(value=value):
                self.assertEqual(parse_orderby(value), expected)

    def test_parse_orderby_invalid(self):
        with self.assertRaises(werkzeug.exceptions.BadRequest):
            parse_orderby("in va lid")


if __name__ == "__main__":
    unittest.main()
