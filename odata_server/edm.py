# Copyright (c) 2021 Future Internet Consulting and Development Solutions S.L.

from typing import Optional
import xml.etree.cElementTree as ET

from odata_server import meta


class PrimitiveType(object):

    def __init__(self, className: str):
        self.className = className

    def __str__(self):
        return self.className


Binary = PrimitiveType("Edm.Binary")
Boolean = PrimitiveType("Edm.Boolean")
Byte = PrimitiveType("Edm.Byte")
Date = PrimitiveType("Edm.Date")
DateTimeOffset = PrimitiveType("Edm.DateTimeOffset")
Decimal = PrimitiveType("Edm.Decimal")
Double = PrimitiveType("Edm.Double")
Duration = PrimitiveType("Edm.Duration")
Guid = PrimitiveType("Edm.Guid")
Int16 = PrimitiveType("Edm.Int16")
Int32 = PrimitiveType("Edm.Int32")
Int64 = PrimitiveType("Edm.Int64")
SByte = PrimitiveType("Edm.SByte")
Single = PrimitiveType("Edm.Single")
Stream = PrimitiveType("Edm.Stream")
String = PrimitiveType("Edm.String")
TimeOfDay = PrimitiveType("Edm.TimeOfDay")
Geography = PrimitiveType("Edm.Geography")
GeographyPoint = PrimitiveType("Edm.GeographyPoint")
GeographyLineString = PrimitiveType("Edm.GeographyLineString")
GeographyPolygon = PrimitiveType("Edm.GeographyPolygon")
GeographyMultiPoint = PrimitiveType("Edm.GeographyMultiPoint")
GeographyMultiLineString = PrimitiveType("Edm.GeographyMultiLineString")
GeographyMultiPolygon = PrimitiveType("Edm.GeographyMultiPolygon")
GeographyCollection = PrimitiveType("Edm.GeographyCollection")
Geometry = PrimitiveType("Edm.Geometry")
GeometryPoint = PrimitiveType("Edm.GeometryPoint")
GeometryLineString = PrimitiveType("Edm.GeometryLineString")
GeometryPolygon = PrimitiveType("Edm.GeometryPolygon")
GeometryMultiPoint = PrimitiveType("Edm.GeometryMultiPoint")
GeometryMultiLineString = PrimitiveType("Edm.GeometryMultiLineString")
GeometryMultiPolygon = PrimitiveType("Edm.GeometryMultiPolygon")
GeometryCollection = PrimitiveType("Edm.GeometryCollection")


class EdmItemBase(type):

    def __new__(cls, name, bases, attrs, **kwargs):
        prefix = attrs.pop("prefix", None)
        defaultsubkind = attrs.pop("defaultsubkind", None)
        namespaces = attrs.pop("namespaces", {})

        new_class = super().__new__(cls, name, bases, attrs, **kwargs)
        class_name = new_class.__name__

        new_class._attrs = {attr_name: attr for attr_name, attr in attrs.items() if isinstance(attr, meta.attribute)}
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
            else:
                setattr(self, attr_name, value)

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


class Annotation(EdmItem):

    Term = meta.attribute(str, required=True)
    Path = meta.attribute(str)
    Qualifier = meta.attribute(str)
    Target = meta.attribute(str)

    Decimal = meta.attribute(str)
    Bool = meta.attribute(str)
    String = meta.attribute(str)
    EnumMember = meta.attribute(str)

    def json(self):
        key = "@{}".format(self.Term)
        if self.Qualifier is not None:
            key += "#{}".format(self.Qualifier)

        if self.String:
            value = self.String
        elif self.Decimal is not None:
            value = self.Decimal
        elif self.Bool:
            value = self.Bool
        elif self.EnumMember:
            value = self.EnumMember
        else:
            value = None

        return key, value


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
    Nullable = meta.attribute(bool, default=False)
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


class Edmx(EdmItem):

    prefix = "edmx"
    namespaces = {
        "edmx": "http://docs.oasis-open.org/odata/ns/edmx",
        "": "http://docs.oasis-open.org/odata/ns/edm",
    }

    Version = meta.static_attribute("4.0")
    DataServices = meta.element(DataServices, required=True)
    References = meta.element(list, items=Reference)
