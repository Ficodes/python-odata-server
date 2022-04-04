# Copyright (c) 2022 Future Internet Consulting and Development Solutions S.L.

import unittest

from odata_server.utils.common import extract_id_value, format_literal, format_key_predicate


class CommonUtilsTestCase(unittest.TestCase):

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
