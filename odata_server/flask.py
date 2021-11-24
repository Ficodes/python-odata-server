# Copyright (c) 2021 Future Internet Consulting and Development Solutions S.L.

import json
from urllib.parse import parse_qs
import xml.etree.cElementTree as ET

import abnf
from flask import abort, Blueprint, request, Response, url_for

from odata_server import edm
from odata_server.utils import add_odata_annotations, build_initial_projection, build_response_headers, expand_result, format_key_predicate, get_collection, ODataGrammar, make_response, parse_key_predicate, process_collection_filters, process_expand_fields


class ODataBluePrint(Blueprint):

    def make_setup_state(self, app, options, first_registration=False):
        state = super().make_setup_state(app, options, first_registration=first_registration)
        edmx = edm.Edmx(options["options"].get("edmx"))
        mongo = options["options"].get("mongo")

        state.add_url_rule("/", view_func=get_service_document, methods=("GET",), endpoint="root", defaults={"edmx": edmx})
        state.add_url_rule("/$metadata", view_func=get_metadata, methods=("GET",), endpoint="$metadata", defaults={"edmx": edmx})

        for schema in edmx.DataServices.Schemas:
            schema.entity_types_by_id = {
                e.Name: e
                for e in schema.EntityTypes
            }
            for entity_type in schema.EntityTypes:
                virtual_entities = set()
                for navigation_property in entity_type.NavigationProperties:
                    navigation_property.iscollection = navigation_property.Type.startswith("Collection(")
                    type_name = navigation_property.Type[11:-1] if navigation_property.iscollection else navigation_property.Type
                    type_name = type_name.rsplit(".", 1)[1]
                    navigation_property.entity_type = schema.entity_types_by_id[type_name]
                    navigation_property.annotations = {
                        a.Term: a for a in navigation_property.Annotations
                    }
                    if "PythonODataServer.Embedded" in navigation_property.annotations:
                        # TODO check annotation value
                        navigation_property.isembedded = True
                        virtual_entities.add(navigation_property.Name)
                        navigation_property.Annotations.remove(navigation_property.annotations["PythonODataServer.Embedded"])
                        del navigation_property.annotations["PythonODataServer.Embedded"]
                    else:
                        navigation_property.isembedded = False
                entity_type.virtual_entities = virtual_entities
                entity_type.key_properties = tuple(p.Name for p in entity_type.Key.PropertyRefs)

                entity_type.annotations = {
                    a.Term: a for a in entity_type.Annotations
                }
                entity_type.properties = {
                    t.Name: t for t in entity_type.Properties
                }
                entity_type.navproperties = {
                    t.Name: t for t in entity_type.NavigationProperties
                }
                entity_type.property_list = tuple(entity_type.properties.values())

            for container in schema.EntityContainers:
                container.Annotations.append(edm.Annotation({"Term": "Org.OData.Core.V1.ODataVersions", "String": "4.0"}))
                container.Annotations.append(edm.Annotation({"Term": "Org.OData.Capabilities.V1.ConformanceLevel", "EnumMember": "Org.OData.Capabilities.V1.ConformanceLevelType/Minimal"}))
                entity_sets_by_id = {
                    s.Name: s
                    for s in container.EntitySets
                }
                for entity_set in container.EntitySets:
                    entity_set.annotations = {
                        a.Term: a for a in entity_set.Annotations
                    }
                    entity_set.bindings = {
                        navbinding.Path: entity_sets_by_id[navbinding.Target]
                        for navbinding in entity_set.NavigationPropertyBindings
                    }
                    entity_set.entity_type = get_entity_type(edmx, entity_set.EntityType)
                    # Mongo collection to use
                    if "PythonODataServer.MongoCollection" in entity_set.annotations:
                        entity_set.mongo_collection = entity_set.annotations["PythonODataServer.MongoCollection"].String
                        entity_set.Annotations.remove(entity_set.annotations["PythonODataServer.MongoCollection"])
                        del entity_set.annotations["PythonODataServer.MongoCollection"]
                    else:
                        entity_set.mongo_collection = entity_set.Name.lower()

                    # Field inside mongo to use as container
                    if "PythonODataServer.MongoPrefix" in entity_set.annotations:
                        entity_set.prefix = entity_set.annotations["PythonODataServer.MongoPrefix"].String
                        entity_set.Annotations.remove(entity_set.annotations["PythonODataServer.MongoPrefix"])
                        del entity_set.annotations["PythonODataServer.MongoPrefix"]
                    else:
                        entity_set.prefix = ""

                    state.add_url_rule(
                        "/{}".format(entity_set.Name),
                        view_func=get_entity_set,
                        methods=("GET",),
                        endpoint=entity_set.Name,
                        defaults={
                            "edmx": edmx,
                            "mongo": mongo,
                            "RootEntitySet": entity_set,
                        }
                    )
                    state.add_url_rule(
                        "/{}/$count".format(entity_set.Name),
                        view_func=get_collection_count,
                        methods=("GET",),
                        endpoint="{}.count".format(entity_set.Name),
                        defaults={
                            "edmx": edmx,
                            "mongo": mongo,
                            "EntitySet": entity_set,
                        }
                    )
                    state.add_url_rule(
                        "/{}<path:navigation>".format(entity_set.Name),
                        view_func=get_entity_set,
                        methods=("GET",),
                        endpoint="{}#nav".format(entity_set.Name),
                        defaults={
                            "edmx": edmx,
                            "mongo": mongo,
                            "RootEntitySet": entity_set,
                        }
                    )

        return state


odata_bp = ODataBluePrint("odata", __name__, url_prefix='/odata')


def get_service_document(edmx):
    format = request.args.get("$format")

    context = url_for("odata.$metadata", _external=True).replace("%24", "$")
    headers = {
        "OData-Version": "4.0"
    }
    assets = []
    for schema in edmx.DataServices.Schemas:
        for container in schema.EntityContainers:
            for entity_set in container.EntitySets:
                if entity_set.IncludeInServiceDocument:
                    assets.append(entity_set)

    if format in (None, "application/json", "json"):
        document = {
            "@odata.context": context,
            "value": [{
                "name": asset.Name,
                "kind": asset.__class__.__name__,
                "url": asset.Name,
            } for asset in assets
            ]
        }
        headers["Content-Type"] = "application/json;charset=utf-8"
        return Response(json.dumps(document, ensure_ascii=False).encode("utf-8"), status=200, headers=headers)
    # elif format in ("application/xml", "xml"):
    #     headers["Content-Type"] = "application/xml;charset=utf-8"
    #     return Response(ET.tostring(edmx.xml(), encoding="UTF-8", xml_declaration=True), status=200, headers=headers)
    else:
        return Response(status=415)


def get_metadata(edmx):
    format = request.args.get("$format")

    headers = {
        "OData-Version": "4.0"
    }
    if format in (None, "application/xml", "xml"):
        headers["Content-Type"] = "application/xml;charset=utf-8"
        return Response(ET.tostring(edmx.xml(), encoding="utf-8", xml_declaration=True), status=200, headers=headers)
    elif format in (None, "application/json", "json"):
        headers["Content-Type"] = "application/json;charset=utf-8"
        return Response(json.dumps(edmx.json(), ensure_ascii=False).encode("utf-8"), status=200, headers=headers)
    else:
        return Response(status=415)


def parse_prefer_header(value, version="4.0"):
    data = parse_qs(value, separator=",")
    if version == "4.0" and "maxpagesize" in data:
        del data["maxpagesize"]

    if "odata.maxpagesize" in data:
        data.setdefault("maxpagesize", data["odata.maxpagesize"])
        del data["odata.maxpagesize"]

    data["maxpagesize"] = int(data.get("maxpagesize", "25"))
    if data["maxpagesize"] < 1:
        data["maxpagesize"] = 25
    elif data["maxpagesize"] > 100:
        data["maxpagesize"] = 100

    return data


def get_mongo_prefix(RootEntitySet, subject):
    if isinstance(subject, edm.NavigationProperty):
        prefix = subject.Name if subject.isembedded and subject.entity_type != RootEntitySet.entity_type else ""
        if RootEntitySet.prefix != "" and prefix != "":
            return "{}.{}".format(RootEntitySet.prefix, prefix)
        elif RootEntitySet.prefix != "" and prefix == "":
            return RootEntitySet.prefix
        else:
            return prefix

    return subject.prefix


def get_entity_type(edmx, type):
    for schema in edmx.DataServices.Schemas:
        if not type.startswith(schema.Namespace) and (schema.Alias is None or not type.startswith(schema.Alias)):
            continue

        for entity_type in schema.EntityTypes:
            if type in ("{}.{}".format(schema.Namespace, entity_type.Name), "{}.{}".format(schema.Alias, entity_type.Name)):
                return entity_type

    # Not found
    return None


def get(mongo, RootEntitySet, subject, id_value, prefers):
    EntityType = subject.entity_type

    mongo_collection = mongo.get_collection(RootEntitySet.mongo_collection)

    # Check if we need to apply a prefix to mongodb fields
    prefix = get_mongo_prefix(RootEntitySet, subject)

    select = request.args.get("$select", "")
    projection = build_initial_projection(EntityType, select, prefix=prefix)

    # Process expand fields
    expand_details = process_expand_fields(RootEntitySet, subject.entity_type, request.args.get("$expand", ""), projection, prefix=prefix)

    if prefix == "":
        data = mongo_collection.find_one(id_value, projection)
        if data is None:
            abort(404)
    elif prefix != "":
        seq = id_value.pop("Seq") if "Seq" in id_value else None

        pipeline = [
            {"$match": id_value},
            {"$project": projection},
        ]
        if seq is not None:
            pipeline.extend([
                {
                    "$unwind": {
                        "path": "${}".format(prefix),
                        "includeArrayIndex": "Seq"
                    }
                },
                {
                    "$match": {
                        "Seq": seq
                    }
                }
            ])
        else:
            pipeline.append({"$unwind": "${}".format(prefix)})

        pipeline.append({"$limit": 1})
        results = tuple(mongo_collection.aggregate(pipeline))
        if len(results) == 0:
            abort(404)
        data = results[0]
        data.update(data[prefix])
        del data[prefix]

    etag = str(data["uuid"])
    if isinstance(subject, edm.EntitySet):
        data = add_odata_annotations(expand_result(RootEntitySet, expand_details, data), RootEntitySet)
    else:
        del data["uuid"]
        data = expand_result(RootEntitySet, expand_details, data)

    anchor = "{}/$entity".format("{}/{}".format(RootEntitySet.Name, prefix) if prefix != "" else RootEntitySet.Name)
    data["@odata.context"] = "{}#{}".format(url_for("odata.$metadata", _external=True).replace("%24", "$"), anchor)
    headers = build_response_headers()
    return make_response(data, status=200, etag=etag, headers=headers)


def get_property(mongo, EntitySet, id_value, prefers, Property, raw=False):
    mongo_collection = mongo.get_collection(EntitySet.mongo_collection)
    data = mongo_collection.find_one(id_value, {Property.Name: 1})
    if raw:
        data = data[Property.Name]
    else:
        keyPredicate = format_key_predicate(id_value)
        anchor = "{}({})/{}".format(EntitySet.Name, keyPredicate, Property.Name)
        data = {
            "@odata.context": "{}#{}".format(url_for("odata.$metadata", _external=True).replace("%24", "$"), anchor),
            "value": data[Property.Name]
        }
    headers = build_response_headers()
    return make_response(data, status=200, headers=headers)


def get_collection_count(edmx, mongo, EntitySet, filters=None):
    mongo_collection = mongo.get_collection(EntitySet.mongo_collection)

    # Process filters
    if filters is None:
        filters = {
            "uuid": {"$exists": True}
        }

    filter_arg = request.args.get("$filter", "").strip()
    filters = process_collection_filters(filter_arg, filters, EntitySet.entity_type)
    count = mongo_collection.count_documents(filters)

    headers = build_response_headers()
    return make_response(count, status=200, headers=headers)


def get_entity_set(mongo, edmx, RootEntitySet, navigation=""):
    prefers = parse_prefer_header(request.headers.get("Prefer", ""))

    if navigation != "":
        try:
            tree = ODataGrammar("collectionNavPath").parse_all(navigation)
        except abnf.parser.ParseError:
            abort(404)

        id_value = None
        subject = RootEntitySet
        count = raw = False
        nav = tree
        id_value = None
        filters = {}
        if nav.children[0].name == "keyPredicate":
            id_value = parse_key_predicate(RootEntitySet.entity_type, nav.children[0])
            if nav.children[1].value != "":
                path = nav.children[1].children[1].value
                if isinstance(subject, edm.EntitySet):
                    if path in subject.entity_type.navproperties:
                        # Navigate through navigation properties
                        target = subject.entity_type.navproperties[path]
                        # if not target.isembedded:
                        #     # TODO the code in this block assumes a 1-N relationship, our side is the 1
                        #     ref = mongo.get_collection(RootEntitySet.mongo_collection).find_one(id_value, projection={subject.Name: 1})
                        #     if ref is None:
                        #         abort(404)
                        #     key_property = target.parent.key_properties[0]
                        #     id_value = {
                        #         key_property: ref[subject.Name]
                        #     }

                        # Navigate to the new node
                        subject = target
                        if subject.entity_type.Name in RootEntitySet.bindings:
                            RootEntitySet = RootEntitySet.bindings[subject.entity_type.Name]

                        count = len(nav.children[1].children) == 3 and nav.children[1].children[2].name == "count"
                    elif path in subject.entity_type.properties:
                        # Navigate through structural properties
                        subject = subject.entity_type.properties[path]
                        raw = len(nav.children[1].children) == 3 and nav.children[1].children[2].name == "value"
                    else:
                        abort(404)

                else:
                    abort(404)

        if isinstance(subject, edm.NavigationProperty):
            if subject.iscollection:
                count = request.args.get("$count", "false").strip().lower() == "true"
                filters = {
                    key_property: {"$eq": key_value}
                    for key_property, key_value in id_value.items()
                }
                return get_collection(mongo, RootEntitySet, subject, prefers, filters=filters, count=count)
            else:
                return get(mongo, RootEntitySet, subject, id_value, prefers)

        elif isinstance(subject, edm.EntitySet):
            if id_value is not None:
                return get(mongo, RootEntitySet, subject, id_value, prefers)
            else:
                count = request.args.get("$count", "false").strip().lower() == "true"
                return get_collection(mongo, RootEntitySet, subject, prefers, count=count)
        elif isinstance(subject, edm.Property):
            if id_value is None or count:
                abort(404)
            return get_property(mongo, RootEntitySet, id_value, prefers, subject, raw=raw)
        else:
            abort(404)
    else:
        count = request.args.get("$count", "false").strip().lower() == "true"
        return get_collection(mongo, RootEntitySet, RootEntitySet, prefers, count=count)
