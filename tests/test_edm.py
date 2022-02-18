# Copyright (c) 2021-2022 Future Internet Consulting and Development Solutions S.L.

import json
import unittest
import xml.etree.cElementTree as ET

from odata_server import edm


ACTION1 = {
    "Name": "Release",
    "IsBound": False,
    "Parameters": [
        {"Name": "product", "Type": "ODataDemo.Product"},
    ]
}

ACTION2 = {
    "Name": "Release",
    "IsBound": False,
    "Parameters": [
        {"Name": "product", "Type": "ODataDemo.Product"},
        {"Name": "product", "Type": "ODataDemo.Product"},
    ],
    "ReturnType": {
        "Type": "Edm.Bool"
    }
}

ACTION3 = {
    "Name": "Release",
    "IsBound": True,
    "Parameters": [
        {"Name": "version", "Type": "Edm.String", "Unicode": False},
    ],
    "ReturnType": {
        "Type": "Edm.Bool"
    }
}

ENTITY_TYPE1 = {
    "Name": "Shipping",
    "Key": [
        {"Name": "ID"},
    ],
    "Properties": [
        {"Name": "ID", "Type": "Edm.String", "Nullable": False},
        {"Name": "emails", "Type": "Collection(Edm.String)", "Nullable": False},
        {"Name": "recipient", "Type": "Edm.String", "Nullable": False},
    ]
}

ENTITY_TYPE2 = {
    "Name": "Employee",
    "Key": [
        {"Name": "ID"},
    ],
    "Properties": [
        {"Name": "ID", "Type": "Edm.String", "Nullable": False},
        {"Name": "FirstName", "Type": "Edm.String", "Nullable": False},
        {"Name": "LastName", "Type": "Edm.String", "Nullable": False},
    ],
    "NavigationProperty": [
        {"Name": "Manager", "Type": "self.Manager"},
    ]
}

SCHEMA1 = {
    "Namespace": "Testing",
    "Alias": "t",
    "Actions": [
        ACTION1,
    ],
    "EntityTypes": [
        ENTITY_TYPE1,
        ENTITY_TYPE2,
    ]
}

ENTITY_SET1 = {
    "Name": "Products",
    "EntityType": "Product",
    "IncludeInServiceDocument": False,
    "NavigationPropertyBindings": [
        {
            "Path": "Category",
            "Target": "SomeModel.SomeContainer/Categories",
        },
    ],
    "Annotations": [
        {
            "Term": "UI.DisplayName",
            "String": "Products"
        }
    ]
}


class EdmUnitTests(unittest.TestCase):

    def test_action_minimal(self):
        e = edm.Action({
            "Name": "Release",
        })

        self.assertEqual(e.Name, "Release")
        self.assertEqual(e.IsBound, False)
        self.assertEqual(e.EntitySetPath, None)
        self.assertEqual(len(e.Parameters), 0)
        self.assertEqual(len(e.Annotations), 0)

        with self.subTest(msg="JSON serialization"):
            e.json()

        with self.subTest(msg="XML serialization"):
            e.xml()

    def test_action(self):
        for desc in (ACTION1, ACTION2, ACTION3):
            a = edm.Action(desc)

            with self.subTest(msg="JSON serialization"):
                a.json()

            with self.subTest(msg="XML serialization"):
                a.xml()

    def test_annotation(self):
        # Attribute annotations
        test_data = (
            ("String", "abc", "abc"),
            ("Bool", "true", True),
            ("Integer", "5", 5),
        )
        for field, value, expected_value in test_data:
            with self.subTest(field=field, value=value):
                a = edm.Annotation({
                    "Term": "OneTerm",
                    field: value
                })
                self.assertEqual(a.Term, "OneTerm")
                self.assertEqual(a.value, expected_value)
                self.assertEqual(
                    ET.tostring(a.xml(), encoding="utf-8").decode("utf-8"),
                    '<Annotation {}="{}" Term="OneTerm" />'.format(field, value)
                )

        # Element annotations
        test_data = (
            (
                "Null",
                [],
                None,
                "<Null />",
            ),
            (
                "Null",
                [{"Term": "Core.Description", "String": "No rating provided"}],
                None,
                '<Null><Annotation String="No rating provided" Term="Core.Description" /></Null>',
            ),
            (
                "Collection",
                [{"String": "abc"}, {"Null": []}, {"Collection": [{"Integer": 5}, {"Bool": True}]}],
                ["abc", None, [5, True]],
                "<Collection><String>abc</String><Null /><Collection><Integer>5</Integer><Bool>true</Bool></Collection></Collection>",
            ),
            (
                "Record",
                {"Type": "ComplexType1", "PropertyValues": [{"Property": "Insertable", "Bool": True}]},
                {
                    "Insertable": True
                },
                '<Record Type="ComplexType1"><PropertyValue Bool="true" Property="Insertable" /></Record>',
            ),
        )
        for field, value, expected_value, subelement in test_data:
            with self.subTest(field=field, value=value):
                a = edm.Annotation({
                    "Term": "OneTerm",
                    field: value
                })
                self.assertEqual(a.Term, "OneTerm")
                self.assertEqual(a.value, expected_value)
                self.assertEqual(
                    ET.tostring(a.xml(), encoding="utf-8").decode("utf-8"),
                    '<Annotation Term="OneTerm">{}</Annotation>'.format(subelement)
                )
                self.assertEqual(
                    a.json()[1],
                    getattr(a, field).json()
                )

    def test_entity_set_minimal(self):
        e = edm.EntitySet({
            "Name": "Products",
            "EntityType": "Product"
        })

        self.assertEqual(e.Name, "Products")
        self.assertEqual(e.IncludeInServiceDocument, True)
        self.assertEqual(len(e.NavigationPropertyBindings), 0)
        self.assertEqual(len(e.Annotations), 0)

        with self.subTest(msg="JSON serialization"):
            e.json()

    def test_entity_set_full(self):
        e = edm.EntitySet(ENTITY_SET1)

        self.assertEqual(e.Name, "Products")
        self.assertEqual(e.IncludeInServiceDocument, False)
        self.assertEqual(len(e.NavigationPropertyBindings), 1)
        self.assertEqual(len(e.Annotations), 1)

        with self.subTest(msg="JSON serialization"):
            e.json()

    def test_entity_type_minimal(self):
        e = edm.EntityType({
            "Name": "h"
        })

        self.assertEqual(e.Name, "h")
        self.assertEqual(len(e.Properties), 0)

    def test_entity_type_full(self):
        e = edm.EntityType(ENTITY_TYPE1)

        self.assertEqual(e.Name, "Shipping")
        self.assertEqual(len(e.Key.PropertyRefs), 1)
        self.assertEqual(e.Key.PropertyRefs[0].Name, "ID")
        self.assertEqual(len(e.Properties), 3)

    def test_schema_minimal(self):
        s = edm.Schema({
            "Namespace": "Testing"
        })
        self.assertEqual(s.Namespace, "Testing")

    def test_schema_full(self):
        s = edm.Schema(SCHEMA1)
        self.assertEqual(s.Namespace, "Testing")
        self.assertEqual(s.Alias, "t")
        self.assertEqual(len(s.EntityTypes), 2)

    def test_dataservices_minimal(self):
        d = edm.DataServices([{
            "Namespace": "Testing",
        }])
        self.assertEqual(len(d.Schemas), 1)

    def test_dataservices_full(self):
        d = edm.DataServices([
            SCHEMA1
        ])
        self.assertEqual(len(d.Schemas), 1)

    def test_dataservices_full_verbose(self):
        d = edm.DataServices({
            "Schemas": [
                SCHEMA1
            ]
        })
        self.assertEqual(len(d.Schemas), 1)
        self.assertEqual(type(d.json()), list)

    def test_parameter_minimal(self):
        p = edm.Parameter({
            "Name": "param",
            "Type": "Edm.String"
        })

        with self.subTest(version="v4.0", format="json"):
            self.assertEqual(
                p.json(),
                {
                    "$Name": "param",
                    "$Type": "Edm.String"
                }
            )

        with self.subTest(version="v4.0", format="xml"):
            self.assertEqual(
                ET.tostring(p.xml()),
                b'<Parameter Name="param" Type="Edm.String" />',
            )

        with self.subTest(version="v4.01", format="json"):
            self.assertEqual(
                p.json(version="4.01"),
                {
                    "$Name": "param",
                    "$Type": "Edm.String"
                }
            )

        with self.subTest(version="v4.01", format="xml"):
            self.assertEqual(
                ET.tostring(p.xml(version="4.01")),
                b'<Parameter Name="param" Type="Edm.String" />',
            )

    def test_parameter_unicode(self):
        p = edm.Parameter({
            "Name": "param",
            "Type": "Edm.String",
            "Unicode": False,
        })

        with self.subTest(version="v4.0", format="json"):
            self.assertEqual(
                p.json(),
                {
                    "$Name": "param",
                    "$Type": "Edm.String",
                }
            )

        with self.subTest(version="v4.0", format="xml"):
            self.assertEqual(
                ET.tostring(p.xml()),
                b'<Parameter Name="param" Type="Edm.String" />',
            )

        with self.subTest(version="v4.01"):
            self.assertEqual(
                p.json(version="4.01"),
                {
                    "$Name": "param",
                    "$Type": "Edm.String",
                    "$Unicode": False,
                }
            )

        with self.subTest(version="v4.0", format="xml"):
            self.assertEqual(
                ET.tostring(p.xml(version="4.01")),
                b'<Parameter Name="param" Type="Edm.String" Unicode="false" />',
            )

    def test_record_minimal(self):
        r = edm.Record({})
        self.assertEqual(r.json(), {})

    def test_record_simple(self):
        r = edm.Record({
            "Insertable": True,
            "NonInsertableProperties": ["manifest_datetime"]
        })
        self.assertEqual(r.json(), {})

    def test_record_full(self):
        r = edm.Record({
            "Type": "ComplexType",
            "Annotations": [
                {"Term": "Core.Description", "String": "Annotation on record"},
            ],
            "PropertyValues": [
                {"Property": "Insertable", "Bool": True},
                {"Property": "NonInsertableNavigationProperties", "Collection": []},
                {"Property": "NonInsertableProperties", "Collection": [{"PropertyPath": "manifest_datetime"}]},
            ]
        })
        self.assertEqual(r.json(), {
            "@type": "ComplexType",
            "@Core.Description": "Annotation on record",
            "Insertable": True,
            "NonInsertableNavigationProperties": [],
            "NonInsertableProperties": ["manifest_datetime"],
        })

    def test_schema_key_with_alias(self):
        s = edm.Schema({
            "Namespace": "ODataDemo",
            "EntityTypes": [
                {
                    "Name": "Category",
                    "Key": [
                        {"Name": "Info/ID", "Alias": "EntityInfoID"},
                    ],
                    "Properties": [
                        {"Name": "Info", "Type": "self.EntityInfo"},
                        {"Name": "Name", "Nullable": True},
                    ],
                },
            ],
            "EntityContainers": [
                {
                    "Name": "Container",
                }
            ],
            "ComplexTypes": [
                {
                    "Name": "EntityInfo",
                    "Properties": [
                        {"Name": "ID", "Type": "Edm.Int32"},
                        {"Name": "Created", "Type": "Edm.DateTimeOffset", "Precision": 0},
                    ],
                },
            ]
        })
        self.assertEqual(len(s.EntityTypes), 1)
        self.assertEqual(len(s.ComplexTypes), 1)
        self.assertEqual(len(s.EntityContainers), 1)
        print(json.dumps(s.json(), indent=4))

    def test_edmx(self):
        edmx = edm.Edmx({
            "DataServices": [{
                "Namespace": "ODataDemo",
                "EntityTypes": [
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
                        ],
                    }
                ]
            }]
        })

        ET.tostring(edmx.xml())


if __name__ == "__main__":
    unittest.main()
