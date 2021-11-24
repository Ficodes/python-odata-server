# Copyright (c) 2021 Future Internet Consulting and Development Solutions S.L.

import unittest
from unittest.mock import ANY, Mock, patch

from flask import Flask

from odata_server.flask import odata_bp


edmx = {
    "DataServices": [{
        "Namespace": "ODataDemo",
        "EntityTypes": [
            {
                "Name": "PricePlan",
                "Key": [{"Name": "ID"}],
                "Properties": [
                    {
                        "Name": "ID",
                        "Type": "Edm.Int32",
                        "Nullable": False
                    },
                    {
                        "Name": "Name",
                        "Type": "Edm.String",
                        "Nullable": False
                    }
                ]
            },
            {
                "Name": "Product",
                "HasStream": True,
                "Key": [{"Name": "ID"}],
                "Properties": [
                    {
                        "Name": "ID",
                        "Type": "Edm.Int32",
                        "Nullable": False
                    },
                    {
                        "Name": "Description",
                        "Type": "Edm.String",
                        "Annotations": [
                            {"Term": "Core.IsLanguageDependent"},
                        ],
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
                    }
                ],
            },
            {
                "Name": "Category",
                "Key": [{"Name": "ID"}],
                "Properties": [
                    {
                        "Name": "ID",
                        "Type": "Edm.Int32",
                        "Nullable": False
                    },
                    {
                        "Name": "Name",
                        "Type": "Edm.String",
                        "Nullable": False,
                        "Annotations": [
                            {"Term": "Core.IsLanguageDependent"},
                        ]
                    },
                ],
                "NavigationProperties": [
                    {
                        "Name": "Products",
                        "Partner": "Category",
                        "Type": "Collection(ODataDemo.Product)",
                        "OnDelete": {"Action": "Cascade"}
                    }
                ]
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
                            {
                                "Path": "Category",
                                "Target": "Categories"
                            },
                            {
                                "Path": "PricePlan",
                                "Target": "PricePlans",
                            }
                        ],
                    },
                    {
                        "Name": "Categories",
                        "EntityType": "ODataDemo.Category",
                        "NavigationPropertyBindings": [{
                            "Path": "Products",
                            "Target": "Products"
                        }],
                    },
                    {
                        "Name": "PricePlans",
                        "EntityType": "ODataDemo.PricePlan",
                    }
                ],

            }
        ]
    }]
}


mongo = Mock()
app = Flask(__name__)
app.register_blueprint(odata_bp, options={"mongo": mongo, "edmx": edmx}, url_prefix="")


class BluePrintTestCase(unittest.TestCase):

    def setUp(self):
        mongo.reset_mock()
        self.app = app.test_client()

    def test_metadata_api_default_xml(self):
        response = self.app.get("/$metadata")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["OData-Version"], "4.0")
        self.assertEqual(response.headers["Content-Type"], "application/xml;charset=utf-8")

    def test_metadata_api_xml_format_param(self):
        response = self.app.get("/$metadata?$format=xml")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["OData-Version"], "4.0")
        self.assertEqual(response.headers["Content-Type"], "application/xml;charset=utf-8")

    def test_metadata_api_json_format_param(self):
        response = self.app.get("/$metadata?$format=json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["OData-Version"], "4.0")
        self.assertEqual(response.headers["Content-Type"], "application/json;charset=utf-8")

    def test_metadata_api_format_param_not_supported(self):
        response = self.app.get("/$metadata?$format=yaml")
        self.assertEqual(response.status_code, 415)

    @patch("odata_server.flask.get")
    def test_get_entity_api_by_id(self, get):
        get.return_value = ({}, 200)
        response = self.app.get("/Products(5)")
        self.assertEqual(response.status_code, 200)
        get.assert_called_once_with(mongo, ANY, ANY, {"ID": 5}, {"maxpagesize": 25})

    @patch("odata_server.flask.get")
    def test_get_entity_api_by_id_not_found(self, get):
        get.return_value = ({}, 404)
        response = self.app.get("/Products(5)")
        self.assertEqual(response.status_code, 404)
        # TODO check error response body
        get.assert_called_once_with(mongo, ANY, ANY, {"ID": 5}, {"maxpagesize": 25})

    @patch("odata_server.flask.get_property")
    def test_get_entity_property_api_by_id(self, get_property):
        get_property.return_value = ({}, 200)
        response = self.app.get("/Products(5)/Description")
        self.assertEqual(response.status_code, 200)
        get_property.assert_called_once_with(mongo, ANY, {"ID": 5}, {"maxpagesize": 25}, ANY, raw=False)

    @patch("odata_server.flask.get_property")
    def test_get_entity_property_api_by_id_raw(self, get_property):
        get_property.return_value = ({}, 200)
        response = self.app.get("/Products(5)/Description/$value")
        self.assertEqual(response.status_code, 200)
        get_property.assert_called_once_with(mongo, ANY, {"ID": 5}, {"maxpagesize": 25}, ANY, raw=True)

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
                mongo.get_collection().find().sort().skip().limit.return_value = ()
                mongo.reset_mock()
                response = self.app.get("/Products?$orderby={}".format(orderby_expr))
                mongo.get_collection().find().sort.assert_called_once_with(expected)
                self.assertEqual(response.status_code, 200)

    def test_get_entity_collection_api_empty_filter(self):
        mongo.get_collection().find().skip().limit.return_value = ()
        mongo.reset_mock()
        response = self.app.get("/Products?$filter=")
        mongo.get_collection().find.assert_called_once_with({"uuid": {"$exists": True}}, ANY)
        self.assertEqual(response.status_code, 200)

    def test_get_entity_collection_api_basic_filters(self):
        test_data = (
            ("Basic eq operator", "Name eq 'Bread'"),
            ("Logical or", "Name eq 'Bread' or Price gt 10"),
        )
        for label, filter_expr in test_data:
            with self.subTest(msg=label):
                mongo.get_collection().find().skip().limit.return_value = ()
                response = self.app.get("/Products?$filter={}".format(filter_expr))
                self.assertEqual(response.status_code, 200)

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
        get.return_value = (
            {},
            200
        )
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
        get_collection.return_value = (
            {
                "@odata.count": 3
            },
            200
        )
        response = self.app.get("/Categories?$count=true")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["@odata.count"], 3)

    @patch("odata_server.flask.get_collection")
    def test_get_entity_navigation_property_collection_embedded(self, get_collection):
        get_collection.return_value = (
            {
                "@odata.count": 3
            },
            200
        )
        response = self.app.get("/Categories(0)/Products")
        self.assertEqual(response.status_code, 200)
        get_collection.assert_called_once_with(mongo, ANY, ANY, {"maxpagesize": 25}, filters={"ID": {"$eq": 0}}, count=False)

    @patch("odata_server.flask.get")
    def test_get_entity_navigation_property_single_value_embedded(self, get):
        get.return_value = ({}, 200)
        response = self.app.get("/Products(0)/Category")
        self.assertEqual(response.status_code, 200)
        get.assert_called_once_with(mongo, ANY, ANY, {"ID": 0}, ANY)

    @patch("odata_server.flask.get")
    def test_get_entity_navigation_property_single_value(self, get):
        mongo.get_collection().find_one.return_value = {
            "PricePlan": 13
        }
        get.return_value = ({}, 200)
        response = self.app.get("/Products(0)/PricePlan")
        self.assertEqual(response.status_code, 200)
        get.assert_called_once_with(mongo, ANY, ANY, {"ID": 0}, ANY)

    @patch("odata_server.flask.get_collection")
    def test_get_entity_collection_expand_navigation_property(self, get_collection):
        get_collection.return_value = (
            {
                "@odata.count": 3
            },
            200
        )
        response = self.app.get("/Categories?$expand=Products")
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
