# Copyright (c) 2021 Future Internet Consulting and Development Solutions S.L.

import json
import logging
from urllib.parse import parse_qs as urllib_parse_qs
import xml.etree.cElementTree as ET

import abnf
from flask import abort, Blueprint, request, Response, url_for
import pymongo
import uuid
import werkzeug

from odata_server import edm
from odata_server.utils import add_odata_annotations, build_initial_projection, build_response_headers, expand_result, extract_id_value, format_key_predicate, get_collection, make_response, process_collection_filters, process_expand_fields
from odata_server.utils.mongo import get_mongo_prefix
from odata_server.utils.parse import ODataGrammar, parse_key_predicate, parse_qs


logger = logging.getLogger(__name__)


class ODataBluePrint(Blueprint):

    def make_setup_state(self, app, options, first_registration=False):
        state = super().make_setup_state(app, options, first_registration=first_registration)
        edmx = edm.Edmx(options["options"].get("edmx"))
        mongo = options["options"].get("mongo")

        state.add_url_rule("/", view_func=get_service_document, methods=("GET",), endpoint="root", defaults={"edmx": edmx})
        state.add_url_rule("/$metadata", view_func=get_metadata, methods=("GET",), endpoint="$metadata", defaults={"edmx": edmx})

        edmx.process()
        edmx.resolve_code_references()
        for schema in edmx.DataServices.Schemas:
            for container in schema.EntityContainers:
                for entity_set in container.EntitySets:
                    entity_type = entity_set.entity_type
                    collection_methods = ["GET"]
                    entry_methods = ["GET"]

                    # Check insert configuration
                    insert_restrictions = edm.get_annotation(
                        entity_set,
                        "Org.OData.Capabilities.V1.InsertRestrictions",
                        {
                            "Insertable": True,
                            "NonInsertableProperties": [],
                            "NonInsertableNavigationProperties": [],
                            "RequiredProperties": []
                        }
                    )

                    if len(entity_type.computed_properties) > 0 and entity_set.custom_insert_business is None:
                        raise Exception("EntitySet {} is managing an entity type that contains computed properties. The logic for initializaing those computed properties has to be configured".format(entity_set.Name))

                    if insert_restrictions["Insertable"]:
                        collection_methods.append("POST")

                    # Check update configuration
                    update_restrictions = edm.get_annotation(
                        entity_set,
                        "Org.OData.Capabilities.V1.UpdateRestrictions",
                        {
                            "Updatable": True,
                            "NonUpdatableProperties": [],
                            "NonUpdatableNavigationProperties": [],
                            "RequiredProperties": [],
                        }
                    )

                    if update_restrictions["Updatable"]:
                        entry_methods.append("PATCH")

                    # Check delete configuration
                    delete_restrictions = edm.get_annotation(
                        entity_set,
                        "Org.OData.Capabilities.V1.DeleteRestrictions",
                        {
                            "Deletable": True,
                            "NonDeletableNavigationProperties": [],
                        }
                    )

                    if delete_restrictions["Deletable"]:
                        entry_methods.append("DELETE")

                    # Main configuration
                    if "Org.OData.Core.V1.ResourcePath" not in entity_set.annotations:
                        entity_set.Annotations.append(edm.Annotation({
                            "Term": "Org.OData.Core.V1.ResourcePath",
                            "String": entity_set.Name
                        }))
                        entity_set.annotations["Org.OData.Core.V1.ResourcePath"] = entity_set.Annotations[-1]
                    resource_path = edm.get_annotation(entity_set, "Org.OData.Core.V1.ResourcePath")

                    # URL rules
                    state.add_url_rule(
                        "/{}".format(resource_path),
                        view_func=entity_set_endpoint,
                        methods=collection_methods,
                        endpoint=entity_set.Name,
                        defaults={
                            "edmx": edmx,
                            "mongo": mongo,
                            "RootEntitySet": entity_set,
                        }
                    )
                    state.add_url_rule(
                        "/{}(<key_predicate>)".format(entity_set.Name),
                        view_func=entity_set_entity_endpoint,
                        methods=entry_methods,
                        endpoint="{}$entity".format(entity_set.Name),
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
                        methods=("GET", "PATCH"),
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
    data = {
        key: values[-1]
        for key, values in urllib_parse_qs(value, separator=",").items()
    }

    # maxpagesize
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

    # return
    data.setdefault("return", "representation")

    return data


def get(mongo, RootEntitySet, subject, id_value, prefers, session=None):
    qs = parse_qs(request.query_string)
    EntityType = subject.entity_type

    mongo_collection = mongo.get_collection(RootEntitySet.mongo_collection)

    # Check if we need to apply a prefix to mongodb fields
    prefix = get_mongo_prefix(RootEntitySet, subject)

    select_arg = qs.get("$select", "")
    projection = build_initial_projection(EntityType, select_arg, prefix=prefix)

    # Process expand fields
    expand_arg = qs.get("$expand", "")
    expand_details = process_expand_fields(RootEntitySet, subject.entity_type, expand_arg, projection, prefix=prefix)

    filters = id_value
    filters["uuid"] = {"$exists": True}

    if prefix == "":
        data = mongo_collection.find_one(filters, projection, session=session)
        if data is None:
            abort(404)
    elif prefix != "":
        seq = filters.pop("Seq") if "Seq" in id_value else None

        pipeline = [
            {"$match": filters},
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
        results = tuple(mongo_collection.aggregate(pipeline, session=session))
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


def deref_multi(data, keys):
    return deref_multi(data[keys[0]], keys[1:]) \
        if keys else data


def get_property(mongo, RootEntitySet, id_value, prefers, Property, raw=False):
    mongo_collection = mongo.get_collection(RootEntitySet.mongo_collection)
    prefix = get_mongo_prefix(RootEntitySet, Property)

    mongo_field = Property.Name if prefix == "" else "{}.{}".format(prefix, Property.Name)
    filters = id_value.copy()
    filters["uuid"] = {"$exists": True}
    if prefix != "":
        filters[prefix] = {"$exists": True}

    data = mongo_collection.find_one(filters, {mongo_field: 1})
    if data is None:
        abort(404)

    data = deref_multi(data, mongo_field.split("."))
    if not raw:
        keyPredicate = format_key_predicate(id_value)
        anchor = "{}({})/{}".format(RootEntitySet.Name, keyPredicate, Property.Name)
        data = {
            "@odata.context": "{}#{}".format(url_for("odata.$metadata", _external=True).replace("%24", "$"), anchor),
            "value": data
        }
    headers = build_response_headers()
    return make_response(data, status=200, headers=headers)


def get_collection_count(edmx, mongo, EntitySet, filters=None):
    qs = parse_qs(request.query_string)

    # Process filters
    if filters is None:
        filters = {
            "uuid": {"$exists": True}
        }

    filter_arg = qs.get("$filter", "")
    search_arg = qs.get("$search", "")
    filters = process_collection_filters(filter_arg, search_arg, filters, EntitySet.entity_type)

    mongo_collection = mongo.get_collection(EntitySet.mongo_collection)
    count = mongo_collection.count_documents(filters)

    headers = build_response_headers()
    return make_response(count, status=200, headers=headers)


def entity_set_endpoint(mongo, edmx, RootEntitySet):
    if request.method == "GET":
        return get_entity_set(mongo, edmx, RootEntitySet)
    else:  # request.method == "POST":
        return post_entity_set(mongo, edmx, RootEntitySet, request.json)


def entity_set_entity_endpoint(mongo, edmx, RootEntitySet, key_predicate):
    try:
        key_predicate = ODataGrammar("keyPredicate").parse_all("({})".format(key_predicate))
    except abnf.parser.ParseError:
        abort(404)

    id_value = parse_key_predicate(RootEntitySet.entity_type, key_predicate)
    if request.method == "GET":
        prefers = parse_prefer_header(request.headers.get("Prefer", ""))
        return get(mongo, RootEntitySet, RootEntitySet, id_value, prefers)
    else:  # request.method in ("PATCH", "POST"):
        return patch_entity_set(mongo, edmx, RootEntitySet, id_value, request.json)


def validate_insert_payload(body, EntityType, deepinsert=False):
    for prop in EntityType.computed_properties:
        if prop in body:
            del body[prop]

    for prop in EntityType.nullable_properties:
        body.setdefault(prop, None)

    required_properties = set(p.Name for p in EntityType.properties.values()) - EntityType.computed_properties - EntityType.nullable_properties
    for prop in required_properties:
        if prop not in body:
            abort(400)

    # Deep insert support
    for navprop in EntityType.navproperties.values():
        if navprop.Name in body:
            validate_insert_payload(body[navprop.Name], navprop.entity_type)

    return deepinsert


def patch_entity_set(mongo, edmx, EntitySet, id_value, body):
    logger.debug("If-Match: {}".format(request.headers.get("If-Match", "")))
    logger.debug(json.dumps(body, indent=4))

    prefers = parse_prefer_header(request.headers.get("Prefer", ""))
    prefix = get_mongo_prefix(EntitySet, EntitySet, seq=id_value.get("Seq"))

    filters = id_value.copy()
    if "Seq" in filters:
        del filters["Seq"]

    filters["uuid"] = {"$exists": True}
    if prefix != "":
        filters[prefix] = {"$exists": True}
        body = {"{}.{}".format(prefix, field): value for field, value in body.items()}

    # Check return format
    qs = parse_qs(request.query_string)
    expand_arg = qs.get("$expand", "")
    select_arg = qs.get("$select", "")
    response_presentation = "minimal" if prefers.get("return", "representation") == "minimal" and expand_arg == "" and select_arg == "" else "representation"

    # Perform the operation
    mongo_collection = mongo.get_collection(EntitySet.mongo_collection)
    with mongo.client.start_session() as session:
        result = mongo_collection.update_one(filters, {"$set": body}, session=session)
        if result.matched_count == 0:
            abort(404)

        if response_presentation == "representation":
            # TODO split get method to allow using custom headers and so on
            return get(mongo, EntitySet, EntitySet, id_value, prefers, session=session)

    headers = build_response_headers(_return=response_presentation)
    return make_response(status=200, headers=headers)


def post_entity_set(mongo, edmx, EntitySet, body):
    prefers = parse_prefer_header(request.headers.get("Prefer", ""))
    EntityType = EntitySet.entity_type

    # Validation and normalization
    odata_type = body.pop("@odata.type", None)
    if odata_type is not None:
        odata_type = odata_type.rsplit("#", 1)[1]
        # TODO, for now, we don't support inheritance
        if odata_type not in EntityType.names:
            abort(403)

    validate_insert_payload(body, EntityType)

    # Custon validation and processing
    persisted = False
    if EntitySet.custom_insert_business:
        try:
            result = EntitySet.custom_insert_business(EntitySet, body)
        except werkzeug.exceptions.HTTPException as e:
            if e.code not in (403, 409, 422):
                raise Exception("Invalid error response from custom_insert_business")
            else:
                raise e

        # custom_insert_business function can return a new object or filling
        # computed fields on the provided one
        if result is not None:
            body = result
            persisted = True

        # TODO Disable this validation in production mode
        properties = set(body.keys())
        missing_computed_properties = EntityType.computed_properties - properties
        if len(missing_computed_properties) > 0:
            raise Exception("The following computed property have not been filled by the custom insert code: {}".format(missing_computed_properties))

    if not persisted:
        # Persistence
        prefix = get_mongo_prefix(EntitySet, EntitySet)
        mongo_collection = mongo.get_collection(EntitySet.mongo_collection)
        if prefix == "":
            body["uuid"] = uuid.uuid4()
            try:
                mongo_collection.insert_one(body)
            except pymongo.errors.DuplicateKeyError:
                abort(409)
        else:
            id_value = extract_id_value(EntityType, body)
            if prefix != "":
                payload = {"{}.{}".format(prefix, field): value for field, value in body.items()}
            else:
                payload = body
            payload["uuid"] = body["uuid"] = uuid.uuid4()
            filters = id_value.copy()
            filters[prefix] = {"$exists": False}
            result = mongo_collection.update_one(filters, {"$set": payload})
            if result.matched_count == 0:
                abort(409)

    qs = parse_qs(request.query_string)
    expand_arg = qs.get("$expand", "")
    select_arg = qs.get("$select", "")
    response_presentation = "minimal" if prefers.get("return", "representation") == "minimal" and expand_arg == "" and select_arg == "" else "representation"
    response_body = None if response_presentation == "minimal" else add_odata_annotations(body, EntitySet)
    status = 204 if response_presentation == "minimal" else 201

    headers = build_response_headers(_return=response_presentation)
    headers["Location"] = "{}({})".format(
        url_for("odata.{}".format(EntitySet.Name), _external=True),
        format_key_predicate(extract_id_value(EntitySet.entity_type, body))
    )

    return make_response(response_body, status=status, headers=headers)


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
