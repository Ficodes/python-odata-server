# Copyright (c) 2021-2022 Future Internet Consulting and Development Solutions S.L.

import unittest
from unittest.mock import ANY, Mock, patch

import werkzeug
from flask import Flask

from odata_server.flask import odata_bp

edmx = {
    "DataServices": [
        {
            "Namespace": "ODataDemo",
            "EntityTypes": [
                {
                    "Name": "PricePlan",
                    "Key": [{"Name": "ID"}],
                    "Properties": [
                        {"Name": "ID", "Type": "Edm.Int32", "Nullable": False},
                        {"Name": "Name", "Type": "Edm.String", "Nullable": False},
                    ],
                },
                {
                    "Name": "Product",
                    "HasStream": True,
                    "Key": [{"Name": "ID"}],
                    "Properties": [
                        {"Name": "ID", "Type": "Edm.Int32", "Nullable": False},
                        {
                            "Name": "Description",
                            "Type": "Edm.String",
                            "Annotations": [
                                {"Term": "Core.IsLanguageDependent"},
                            ],
                        },
                        {
                            "Name": "Rating",
                            "Type": "Edm.Int32",
                            "Nullable": True,
                        },
                        {
                            "Name": "ReleaseDate",
                            "Type": "Edm.Date",
                            "Nullable": False,
                            "Annotations": [
                                {"Term": "Org.OData.Core.V1.Computed", "Bool": True},
                            ],
                        },
                        {
                            "Name": "DiscontinuedDate",
                            "Type": "Edm.Date",
                            "Nullable": True,
                        },
                    ],
                    "NavigationProperties": [
                        {
                            "Name": "PricePlan",
                            "Type": "ODataDemo.PricePlan",
                            "Nullable": False,
                        },
                        {
                            "Name": "Category",
                            "Partner": "Products",
                            "Type": "ODataDemo.Category",
                            "Nullable": False,
                            "Annotations": [
                                {"Term": "PythonODataServer.Embedded", "Bool": True},
                            ],
                        },
                    ],
                },
                {
                    "Name": "Category",
                    "Key": [{"Name": "ID"}],
                    "Properties": [
                        {"Name": "ID", "Type": "Edm.Int32", "Nullable": False},
                        {
                            "Name": "Name",
                            "Type": "Edm.String",
                            "Nullable": False,
                            "Annotations": [
                                {"Term": "Core.IsLanguageDependent"},
                            ],
                        },
                    ],
                    "NavigationProperties": [
                        {
                            "Name": "Products",
                            "Partner": "Category",
                            "Type": "Collection(ODataDemo.Product)",
                            "OnDelete": {"Action": "Cascade"},
                        }
                    ],
                },
            ],
            "EntityContainers": [
                {
                    "Name": "DemoService",
                    "EntitySets": [
                        {
                            "Name": "Products",
                            "EntityType": "ODataDemo.Product",
                            "NavigationPropertyBindings": [
                                {"Path": "Category", "Target": "Categories"},
                                {
                                    "Path": "PricePlan",
                                    "Target": "PricePlans",
                                },
                            ],
                            "Annotations": [
                                {
                                    "Term": "PythonODataServer.CustomInsertBusinessLogic",
                                    "String": "tests.test_flask.custom_insert_business",
                                }
                            ],
                        },
                        {
                            "Name": "Categories",
                            "EntityType": "ODataDemo.Category",
                            "NavigationPropertyBindings": [
                                {"Path": "Products", "Target": "Products"}
                            ],
                        },
                        {
                            "Name": "PricePlans",
                            "EntityType": "ODataDemo.PricePlan",
                        },
                    ],
                }
            ],
        }
    ]
}


def custom_insert_business(RootEntitySet, body):
    body["ReleaseDate"] = "2021-12-03"


DEFAULT_PREFERS = {
    "maxpagesize": 25,
    "return": "representation",
}


MINIMAL_PAYLOAD = {"ID": 5, "Description": "A new product"}

FULL_PAYLOAD = {"ID": 5, "Description": "A new product", "Rating": 3.4}

FULL_PAYLOAD_DEEP = {
    "ID": 5,
    "Description": "A new product",
    "Rating": 3.4,
    "PricePlan": {"ID": 1, "Name": "Free"},
}

mongo = Mock()
app = Flask(__name__)
app.register_blueprint(odata_bp, options={"mongo": mongo, "edmx": edmx}, url_prefix="")


class BluePrintTestCase(unittest.TestCase):
    def setUp(self):
        mongo.reset_mock(return_value=True, side_effect=True)
        self.app = app.test_client()

    def test_metadata_api_default_xml(self):
        response = self.app.get("/$metadata")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["OData-Version"], "4.0")
        self.assertEqual(
            response.headers["Content-Type"], "application/xml;charset=utf-8"
        )

    def test_metadata_api_xml_format_param(self):
        response = self.app.get("/$metadata?$format=xml")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["OData-Version"], "4.0")
        self.assertEqual(
            response.headers["Content-Type"], "application/xml;charset=utf-8"
        )

    def test_metadata_api_json_format_param(self):
        response = self.app.get("/$metadata?$format=json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["OData-Version"], "4.0")
        self.assertEqual(
            response.headers["Content-Type"], "application/json;charset=utf-8"
        )

    def test_metadata_api_format_param_not_supported(self):
        response = self.app.get("/$metadata?$format=yaml")
        self.assertEqual(response.status_code, 415)

    @patch("odata_server.flask.get")
    def test_get_entity_api_by_id(self, get):
        get.return_value = ({}, 200)
        response = self.app.get("/Products(5)")
        self.assertEqual(response.status_code, 200)
        get.assert_called_once_with(mongo, ANY, ANY, {"ID": 5}, DEFAULT_PREFERS)

    @patch("odata_server.flask.get")
    def test_get_entity_api_by_id_not_found(self, get):
        get.return_value = ({}, 404)
        response = self.app.get("/Products(5)")
        self.assertEqual(response.status_code, 404)
        # TODO check error response body
        get.assert_called_once_with(mongo, ANY, ANY, {"ID": 5}, DEFAULT_PREFERS)

    @patch("odata_server.flask.get_property")
    def test_get_entity_property_api_by_id(self, get_property):
        get_property.return_value = ({}, 200)
        response = self.app.get("/Products(5)/Description")
        self.assertEqual(response.status_code, 200)
        get_property.assert_called_once_with(
            mongo, ANY, {"ID": 5}, DEFAULT_PREFERS, ANY, raw=False
        )

    @patch("odata_server.flask.get_property")
    def test_get_entity_property_api_by_id_raw(self, get_property):
        get_property.return_value = ({}, 200)
        response = self.app.get("/Products(5)/Description/$value")
        self.assertEqual(response.status_code, 200)
        get_property.assert_called_once_with(
            mongo, ANY, {"ID": 5}, DEFAULT_PREFERS, ANY, raw=True
        )

    @patch("odata_server.flask.get_collection")
    def test_get_entity_collection_api_without_filters(self, get_collection):
        get_collection.return_value = ({}, 200)
        response = self.app.get("/Products")
        self.assertEqual(response.status_code, 200)

    @patch("odata_server.flask.get_collection")
    def test_get_entity_collection_invalid_navigation(self, get_collection):
        response = self.app.get("/Products(rer")
        self.assertEqual(response.status_code, 404)

    def test_get_entity_collection_api_orderby(self):
        test_data = (
            ("Name", [("Name", 1)]),
            ("Name asc", [("Name", 1)]),
            ("Name desc", [("Name", -1)]),
        )
        for orderby_expr, expected in test_data:
            with self.subTest(orderby=orderby_expr):
                mongo.get_collection().find().sort().skip().limit.return_value = iter(
                    ()
                )
                mongo.reset_mock()
                response = self.app.get("/Products?$orderby={}".format(orderby_expr))
                mongo.get_collection().find().sort.assert_called_once_with(expected)
                self.assertEqual(response.status_code, 200)

    def test_get_entity_collection_api_empty_filter(self):
        mongo.get_collection().find().skip().limit.return_value = iter(())
        mongo.reset_mock()
        response = self.app.get("/Products?$filter=")
        mongo.get_collection().find.assert_called_once_with(
            {"uuid": {"$exists": True}}, ANY
        )
        self.assertEqual(response.status_code, 200)

    def test_get_entity_collection_api_basic_filters(self):
        test_data = (
            ("Basic eq operator", "Name eq 'Bread'"),
            ("Basic eq operator (dates)", "ReleaseDate eq 2022-02-15"),
            ("Logical or", "Name eq 'Bread' or Price gt 10"),
        )
        for label, filter_expr in test_data:
            with self.subTest(msg=label):
                mongo.get_collection().find().skip().limit.return_value = iter(())
                response = self.app.get("/Products?$filter={}".format(filter_expr))
                self.assertEqual(response.status_code, 200)
                # force processing of the body generator
                response.json

    def test_get_entity_collection_api_invalid_filter(self):
        test_data = (
            ("Empty value", "$Name"),
            ("Unclosed string literal", "Name eq 'Bread"),
        )
        for label, filter_expr in test_data:
            with self.subTest(msg=label):
                # Invalid string literal (missing closing quote)
                response = self.app.get("/Products?$filter={}".format(filter_expr))
                self.assertEqual(response.status_code, 400)

    @patch("odata_server.flask.get")
    def xtest_get_entity_navigation_property_id(self, get):
        get.return_value = ({}, 200)
        response = self.app.get("/Categories(0)/Products(1)")
        self.assertEqual(response.status_code, 200)

    @patch("odata_server.flask.get_collection")
    def test_get_entity_collection_count_value(self, get_collection):
        mongo.get_collection().count_documents.return_value = 3
        response = self.app.get("/Categories/$count")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, 3)

    @patch("odata_server.flask.get_collection")
    def test_get_entity_collection_count(self, get_collection):
        get_collection.return_value = ({"@odata.count": 3}, 200)
        response = self.app.get("/Categories?$count=true")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["@odata.count"], 3)

    @patch("odata_server.flask.get_collection")
    def test_get_entity_navigation_property_collection_embedded(self, get_collection):
        get_collection.return_value = ({"@odata.count": 3}, 200)
        response = self.app.get("/Categories(0)/Products")
        self.assertEqual(response.status_code, 200)
        get_collection.assert_called_once_with(
            mongo, ANY, ANY, DEFAULT_PREFERS, filters={"ID": {"$eq": 0}}, count=False
        )

    @patch("odata_server.flask.get")
    def test_get_entity_navigation_property_single_value_embedded(self, get):
        get.return_value = ({}, 200)
        response = self.app.get("/Products(0)/Category")
        self.assertEqual(response.status_code, 200)
        get.assert_called_once_with(mongo, ANY, ANY, {"ID": 0}, ANY)

    @patch("odata_server.flask.get")
    def test_get_entity_navigation_property_single_value(self, get):
        mongo.get_collection().find_one.return_value = {"PricePlan": 13}
        get.return_value = ({}, 200)
        response = self.app.get("/Products(0)/PricePlan")
        self.assertEqual(response.status_code, 200)
        get.assert_called_once_with(mongo, ANY, ANY, {"ID": 0}, ANY)

    @patch("odata_server.flask.get_collection")
    def test_get_entity_collection_expand_navigation_property(self, get_collection):
        get_collection.return_value = ({"@odata.count": 3}, 200)
        response = self.app.get("/Categories?$expand=Products")
        self.assertEqual(response.status_code, 200)

    def test_post_entity_collection_single_entity(self):
        for label, payload in (
            ("Minimal payload", MINIMAL_PAYLOAD),
            ("Full payload", FULL_PAYLOAD),
        ):
            with self.subTest(msg=label):
                mongo.reset_mock()
                response = self.app.post("/Products", json=payload)
                self.assertEqual(response.status_code, 201)
                self.assertEqual(
                    response.headers.get("Location"), "http://localhost/Products(5)"
                )
                self.assertEqual(
                    response.headers.get("Preference-Applied"), "return=representation"
                )
                mongo.get_collection().insert_one.assert_called_once()

    def test_post_entity_collection_single_entity_invalid(self):
        for field in MINIMAL_PAYLOAD.keys():
            with self.subTest(removed_field=field):
                payload = MINIMAL_PAYLOAD.copy()
                del payload[field]

                response = self.app.post("/Products", json=payload)
                self.assertEqual(response.status_code, 400)
                mongo.get_collection().insert_one.assert_not_called()

    def test_post_entity_collection_single_entity_representation_minimal(self):
        response = self.app.post(
            "/Products", json=MINIMAL_PAYLOAD, headers={"Prefer": "return=minimal"}
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(
            response.headers.get("Location"), "http://localhost/Products(5)"
        )
        self.assertEqual(response.headers.get("Preference-Applied"), "return=minimal")
        mongo.get_collection().insert_one.assert_called_once()

    def test_post_entity_collection_single_entity_duplicate_key(self):
        mongo.get_collection().insert_one.side_effect = werkzeug.exceptions.Conflict()
        response = self.app.post("/Products", json=MINIMAL_PAYLOAD)
        self.assertEqual(response.status_code, 409)

    def test_post_entity_collection_multiple_entities(self):
        response = self.app.post("/Products", json=FULL_PAYLOAD_DEEP)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.headers.get("Location"), "http://localhost/Products(5)"
        )
        self.assertEqual(
            response.headers.get("Preference-Applied"), "return=representation"
        )
        mongo.get_collection().insert_one.assert_called_once()


if __name__ == "__main__":
    unittest.main()
