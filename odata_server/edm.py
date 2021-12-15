# Copyright (c) 2021 Future Internet Consulting and Development Solutions S.L.

import importlib
from typing import Optional
import xml.etree.cElementTree as ET

from odata_server import meta


class EdmItemBase(type):

    def __new__(cls, name, bases, attrs, **kwargs):
        prefix = attrs.pop("prefix", None)
        defaultsubkind = attrs.pop("defaultsubkind", None)
        namespaces = attrs.pop("namespaces", {})

        new_class = super().__new__(cls, name, bases, attrs, **kwargs)
        class_name = new_class.__name__

        new_class._attrs = {}
        for base in bases:
            new_class._attrs.update(base._attrs)
        new_class._attrs.update({attr_name: attr for attr_name, attr in attrs.items() if isinstance(attr, meta.attribute)})
        new_class._xml_tag = "{}:{}".format(prefix, class_name) if prefix is not None else class_name
        new_class._namespaces = namespaces
        new_class._defaultsubkind = defaultsubkind
        attr_list = tuple(new_class._attrs.items())
        new_class._wrapped_element = attr_list[0][0] if len(attr_list) == 1 and attr_list[0][1].type == list else None

        return new_class


class EdmItem(metaclass=EdmItemBase):

    def __init__(self, definition: dict, parent: Optional[EdmItemBase] = None):
        self.parent = parent

        wrapped_element = self.__class__._wrapped_element
        if wrapped_element is not None and type(definition) == list:
            definition = {wrapped_element: definition}

        for attr_name, attr in self.__class__._attrs.items():
            if attr.required and attr_name not in definition:
                raise ValueError("Missing {} attribute".format(attr_name))

            value = definition.get(attr_name, attr.default)
            if attr.type == list:
                setattr(self, attr_name, [attr.items(item, self) for item in value])
            elif issubclass(attr.type, EdmItem) and value is not None:
                setattr(self, attr_name, attr.type(value))
            elif value is not None:
                setattr(self, attr_name, attr.type(value))
            else:
                setattr(self, attr_name, None)

    def xml(self):
        root = ET.Element(self.__class__._xml_tag)

        for ns_prefix, ns_uri in self.__class__._namespaces.items():
            root.set("xmlns:{}".format(ns_prefix) if ns_prefix != "" else "xmlns", ns_uri)

        for attr_name, attr in self.__class__._attrs.items():
            if attr.static is not None:
                root.set(attr_name, attr.static)
                continue

            value = getattr(self, attr_name)
            if value is None:
                continue
            elif issubclass(attr.type, EdmItem):
                root.append(value.xml())
            elif attr.type == list and issubclass(attr.items, EdmItem):
                for e in value:
                    root.append(e.xml())
            elif type(value) == bool:
                root.set(attr_name, "true" if value else "false")
            elif value is not None:
                root.set(attr_name, str(value))

        return root

    def json(self):
        wrapped_element = self.__class__._wrapped_element
        if wrapped_element is not None:
            value = getattr(self, wrapped_element)
            return [e.json() for e in value]

        data = {}

        for attr_name, attr in self.__class__._attrs.items():
            final_attr_name = "${}".format(attr_name)
            if attr.static is not None:
                data[final_attr_name] = attr.static
                continue

            value = getattr(self, attr_name)
            if value is None:
                continue
            elif issubclass(attr.type, DataServices):
                # TODO particular case
                key = "$Namespace"

                for entry in value.json():
                    data[entry[key]] = entry
                    del entry[key]
            elif issubclass(attr.type, EdmItem):
                data[final_attr_name] = value.json()
            elif attr.type == list:

                if issubclass(attr.items, NavigationPropertyBinding):
                    # TODO particular case
                    key_attr = "Path"
                    value_attr = "Target"

                    for entry in value:
                        data[getattr(entry, key_attr)] = getattr(entry, value_attr)
                elif issubclass(attr.items, Annotation):
                    for e in value:
                        key, avalue = e.json()
                        data[key] = avalue
                elif issubclass(attr.items, EdmItem):
                    subkind = attr.items.__name__ if attr.items.__name__ != self.__class__._defaultsubkind else None
                    key = "${}".format(attr.items.jsonkey)
                    for e in value:
                        subvalue = e.json()
                        key_value = subvalue[key]
                        if subkind is not None:
                            subvalue["$Kind"] = subkind
                        if key in subvalue:
                            del subvalue[key]
                        data[key_value] = subvalue
            elif value is not None:
                data[final_attr_name] = value

        return data


class Null(EdmItem):

    Annotations = meta.element(list, items="Annotation")

    def __init__(self, annotations: Optional[list] = None, parent: Optional[EdmItemBase] = None):
        self.parent = parent

        if annotations is None:
            self.Annotations = []
        else:
            self.Annotations = [Annotation(item, self) for item in annotations]

    def xml(self):
        root = ET.Element("Null")
        for annotation in self.Annotations:
            root.append(annotation.xml())
        return root

    def json(self):
        if len(self.Annotations) == 0:
            return None

        result = {
            "$Null": None,
        }
        for annotation in self.Annotations:
            key, value = annotation.json()
            result[key] = value

        return result


class Collection(EdmItem):

    Items = meta.element(list, items="ValueExpressionItem")

    @property
    def value(self):
        return [i.value for i in self.Items]

    def xml(self):
        root = ET.Element("Collection")

        for Item in self.Items:
            root.append(Item.subxml())

        return root

    def json(self):
        return [i.subjson() for i in self.Items]


class ValueExpressionItem(EdmItem):

    String = meta.attribute(str)
    Integer = meta.attribute(int)
    Decimal = meta.attribute(float)  # TODO
    Bool = meta.attribute(bool)
    EnumMember = meta.attribute(str)
    PropertyPath = meta.attribute(str)
    Path = meta.attribute(str)
    Null = meta.element(Null)

    Collection = meta.element("Collection")
    Record = meta.element("Record")

    all_types = ("String", "Integer", "Decimal", "Bool", "EnumMember", "PropertyPath", "Path", "Collection", "Record", "Null")
    attr_types = ("String", "Integer", "Decimal", "Bool", "EnumMember", "PropertyPath", "Path")
    _type = None

    @property
    def type(self):
        if self._type is None:
            for field in self.all_types:
                if getattr(self, field) is not None:
                    self._type = field
                    break

        return self._type

    @property
    def value(self):
        if self.type in self.attr_types:
            return getattr(self, self.type)
        elif self.Collection:
            return self.Collection.value
        elif self.Record:
            return self.Record.value
        else:
            return None

    def subxml(self):
        if self.type == "Null":
            return self.Null.xml()

        if self.type in self.attr_types:
            root = ET.Element(self.type)
            if self.type == "Bool":
                root.text = "true" if self.value else "false"
            else:
                root.text = str(self.value)
            return root
        else:
            return getattr(self, self.type).xml()

    def subjson(self):
        if self.type in self.attr_types:
            return getattr(self, self.type)
        elif self.Collection:
            return self.Collection.json()
        elif self.Record:
            return self.Record.json()
        elif self.Null:
            return self.Null.json()
        else:
            return None


class PropertyValue(ValueExpressionItem):

    Property = meta.attribute(str, required=True)


class Record(EdmItem):

    Type = meta.attribute(str)
    PropertyValues = meta.element(list, items=PropertyValue)
    Annotations = meta.element(list, items="Annotation")

    @property
    def value(self):
        return {
            p.Property: p.value
            for p in self.PropertyValues
        }

    def json(self):
        result = {}
        if self.Type is not None and self.Type != "":
            result["@type"] = self.Type

        for annotation in self.Annotations:
            key, value = annotation.json()
            result[key] = value

        for propertyvalue in self.PropertyValues:
            result[propertyvalue.Property] = propertyvalue.value

        return result


class Annotation(ValueExpressionItem):

    Term = meta.attribute(str, required=True)
    Qualifier = meta.attribute(str)
    Target = meta.attribute(str)

    Annotations = meta.element(list, items="Annotation")

    def json(self):
        key = "@{}".format(self.Term)
        if self.Qualifier is not None:
            key += "#{}".format(self.Qualifier)

        return key, self.subjson()


class OnDelete(EdmItem):

    Action = meta.attribute(str, required=True)


class NavigationProperty(EdmItem):

    jsonkey = "Name"

    Name = meta.attribute(str, required=True)
    Type = meta.attribute(str, required=True)
    Nullable = meta.attribute(bool, default=False)
    Partner = meta.attribute(str)
    ContainsTarget = meta.attribute(bool)
    OnDelete = meta.element(OnDelete)
    Annotations = meta.element(list, items=Annotation)
    # public referentialConstraints: Array<ReferentialConstraint>


class Property(EdmItem):

    jsonkey = "Name"

    Name = meta.attribute(str, required=True)
    Type = meta.attribute(str, default="Edm.String")
    Nullable = meta.attribute(bool, default=True)
    MaxLength = meta.attribute(int)
    Precision = meta.attribute(float)
    Scale = meta.attribute(float)
    Unicode = meta.attribute(bool)
    SRID = meta.attribute(int)
    ConcurrencyMode = meta.attribute(str)
    Annotations = meta.element(list, items=Annotation)


class PropertyRef(EdmItem):

    Name = meta.attribute(str, required=True)
    Alias = meta.attribute(str)

    def json(self):
        if self.Alias is None:
            return self.Name
        else:
            return {
                self.Alias: self.Name,
            }


class Key(EdmItem):

    PropertyRefs = meta.attribute(list, items=PropertyRef)


class EntityType(EdmItem):

    jsonkey = "Name"
    defaultsubkind = "Property"

    Name = meta.attribute(str, required=True)
    Key = meta.attribute(Key)
    Properties = meta.attribute(list, items=Property)
    NavigationProperties = meta.attribute(list, items=NavigationProperty)
    BaseType = meta.attribute(str)
    Abstract = meta.attribute(bool)
    OpenType = meta.attribute(bool)
    HasStream = meta.attribute(bool)
    Annotations = meta.element(list, items=Annotation)


class NavigationPropertyBinding(EdmItem):

    Path = meta.attribute(str, required=True)
    Target = meta.attribute(str, required=True)


class EntitySet(EdmItem):

    jsonkey = "Name"

    Name = meta.attribute(str, required=True)
    EntityType = meta.attribute(str, required=True)
    IncludeInServiceDocument = meta.attribute(bool, default=True)
    NavigationPropertyBindings = meta.element(list, items=NavigationPropertyBinding)
    Annotations = meta.element(list, items=Annotation)


class EntityContainer(EdmItem):

    jsonkey = "Name"

    Name = meta.attribute(str, required=True)
    EntitySets = meta.element(list, items=EntitySet)
    Annotations = meta.element(list, items=Annotation)
    # Singleton = meta.element(list, items=Singleton)
    # ActionImport = meta.element(list, items=ActionImport)
    # FunctionImport = meta.element(list, items=FunctionImport)


class ComplexType(EdmItem):

    jsonkey = "Name"
    defaultsubkind = "Property"

    Name = meta.attribute(str, required=True)
    BaseType = meta.attribute(str)
    Abstract = meta.attribute(bool)
    OpenType = meta.attribute(bool)
    HasStream = meta.attribute(bool)
    Properties = meta.attribute(list, items=Property)
    NavigationProperties = meta.attribute(list, items=NavigationProperty)
    Annotations = meta.element(list, items=Annotation)


class Schema(EdmItem):

    jsonkey = "Namespace"

    Namespace = meta.attribute(str, required=True)
    Alias = meta.attribute(str)
    # Actions = meta.attribute(list, items=Action)
    Annotations = meta.element(list, items=Annotation)
    ComplexTypes = meta.attribute(list, items=ComplexType)
    EntityContainers = meta.element(list, items=EntityContainer)
    EntityTypes = meta.attribute(list, items=EntityType)
    # EnumTypes = meta.attribute(list, items=EnumType)
    # Functions = meta.attribute(list, items=Function)
    # Terms = meta.attribute(list, items=Term)
    # TypeDefinitions = meta.attribute(list, items=TypeDefinitions)


class DataServices(EdmItem):

    prefix = "edmx"

    Schemas = meta.attribute(list, items=Schema, min=1)


class Include(EdmItem):

    Namespace = meta.attribute(str, required=True)
    Alias = meta.attribute(str)


class Reference(EdmItem):

    jsonkey = "Uri"

    Uri = meta.attribute(str)
    Annotations = meta.element(list, items=Annotation)
    Includes = meta.element(list, items=Include)

    def json(self):
        return [
            include.json() for include in self.Includes
        ]


def get_annotation(item, annotation, default=""):
    if annotation in item.annotations:
        return item.annotations[annotation].value
    else:
        return default


def pop_annotation(item, annotation, default=""):
    if annotation in item.annotations:
        value = item.annotations[annotation].value
        item.Annotations.remove(item.annotations[annotation])
        del item.annotations[annotation]

        return value
    else:
        return default


def set_annotation_default_value(item, annotation, value):
    if annotation in item.annotations:
        return

    new_annotation = Annotation({"Term": annotation, "Bool": value})
    item.annotations[annotation] = new_annotation
    item.Annotations.append(new_annotation)


class Edmx(EdmItem):

    prefix = "edmx"
    namespaces = {
        "edmx": "http://docs.oasis-open.org/odata/ns/edmx",
        "": "http://docs.oasis-open.org/odata/ns/edm",
    }

    Version = meta.static_attribute("4.0")
    DataServices = meta.element(DataServices, required=True)
    References = meta.element(list, items=Reference)

    def get_entity_type(self, type):
        for schema in self.DataServices.Schemas:
            if not type.startswith(schema.Namespace) and (schema.Alias is None or not type.startswith(schema.Alias)):
                continue

            for entity_type in schema.EntityTypes:
                if type in entity_type.names:
                    return entity_type

        # Not found
        return None

    def resolve_code_references(self):
        for schema in self.DataServices.Schemas:
            for container in schema.EntityContainers:
                for entity_set in container.EntitySets:
                    if type(entity_set.custom_insert_business) == str:
                        module, func = entity_set.custom_insert_business.rsplit(".", 1)
                        entity_set.custom_insert_business = getattr(importlib.import_module(module), func)

    def process(self):
        for schema in self.DataServices.Schemas:
            schema.entity_types_by_id = {
                e.Name: e
                for e in schema.EntityTypes
            }

            for entity_type in schema.EntityTypes:
                entity_type.key_properties = tuple(p.Name for p in entity_type.Key.PropertyRefs)

                entity_type.annotations = {
                    a.Term: a for a in entity_type.Annotations
                }

                # Structural properties
                entity_type.properties = {
                    t.Name: t for t in entity_type.Properties
                }
                entity_type.property_list = tuple(entity_type.properties.values())
                entity_type.computed_properties = set()
                entity_type.nullable_properties = set()
                for prop in entity_type.property_list:
                    prop.annotations = {
                        a.Term: a for a in prop.Annotations
                    }
                    computed = pop_annotation(prop, "Org.OData.Core.V1.Computed", False)
                    prop.iscollection = prop.Type.startswith("Collection(")
                    if computed:
                        entity_type.computed_properties.add(prop.Name)
                    if not prop.iscollection and prop.Nullable:
                        entity_type.nullable_properties.add(prop.Name)

                # Navigation properties
                entity_type.navproperties = {
                    t.Name: t for t in entity_type.NavigationProperties
                }
                virtual_entities = set()
                for navigation_property in entity_type.NavigationProperties:
                    navigation_property.iscollection = navigation_property.Type.startswith("Collection(")
                    type_name = navigation_property.Type[11:-1] if navigation_property.iscollection else navigation_property.Type
                    type_name = type_name.rsplit(".", 1)[1]
                    navigation_property.entity_type = schema.entity_types_by_id[type_name]
                    navigation_property.annotations = {
                        a.Term: a for a in navigation_property.Annotations
                    }
                    navigation_property.isembedded = pop_annotation(navigation_property, "PythonODataServer.Embedded", False)
                    if navigation_property.isembedded:
                        virtual_entities.add(navigation_property.Name)
                entity_type.virtual_entities = virtual_entities
                entity_type.names = set(("{}.{}".format(schema.Namespace, entity_type.Name),))
                if schema.Alias is not None:
                    entity_type.names.add("{}.{}".format(schema.Alias, entity_type.Name))

            for container in schema.EntityContainers:
                container.Annotations.append(Annotation({"Term": "Org.OData.Core.V1.ODataVersions", "String": "4.0"}))
                container.Annotations.append(Annotation({"Term": "Org.OData.Capabilities.V1.ConformanceLevel", "EnumMember": "Org.OData.Capabilities.V1.ConformanceLevelType/Minimal"}))
                container.entity_sets_by_id = {
                    s.Name: s
                    for s in container.EntitySets
                }

                for entity_set in container.EntitySets:
                    entity_set.annotations = {
                        a.Term: a for a in entity_set.Annotations
                    }
                    entity_set.bindings = {
                        navbinding.Path: container.entity_sets_by_id[navbinding.Target]
                        for navbinding in entity_set.NavigationPropertyBindings
                    }
                    entity_set.entity_type = self.get_entity_type(entity_set.EntityType)

                    set_annotation_default_value(entity_set, "Org.OData.Capabilities.V1.TopSupported", True)
                    set_annotation_default_value(entity_set, "Org.OData.Capabilities.V1.SkipSupported", True)
                    set_annotation_default_value(entity_set, "Org.OData.Capabilities.V1.IndexableByKey", True)

                    # Mongo collection to use
                    entity_set.mongo_collection = pop_annotation(entity_set, "PythonODataServer.MongoCollection", entity_set.Name.lower())

                    # Mongo sub-document prefix to use
                    entity_set.prefix = pop_annotation(entity_set, "PythonODataServer.MongoPrefix")

                    # Custom business logic
                    entity_set.custom_insert_business = pop_annotation(entity_set, "PythonODataServer.CustomInsertBusinessLogic", None)
