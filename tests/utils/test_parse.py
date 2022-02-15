# Copyright (c) 2021-2022 Future Internet Consulting and Development Solutions S.L.

import unittest
from unittest.mock import Mock

from odata_server.utils.parse import ODataGrammar, parse_key_predicate


class ParseUtilsTestCase(unittest.TestCase):

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


if __name__ == "__main__":
    unittest.main()
