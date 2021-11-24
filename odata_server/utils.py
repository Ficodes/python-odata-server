# Copyright (c) 2021 Future Internet Consulting and Development Solutions S.L.

import datetime
import json
import os
import re
from urllib.parse import unquote, urlencode

import abnf
import arrow
from bson.son import SON
from flask import abort, request, Response, url_for
import uuid

from odata_server import edm


EXPR_MAPPING = {
    "eqExpr": "$eq",
    "neExpr": "$ne",
    "ltExpr": "$lt",
    "leExpr": "$lte",
    "gtExpr": "$gt",
    "geExpr": "$gte",
    "inExpr": "$in",
}
SUPPORTED_EXPRESSIONS = tuple(EXPR_MAPPING.keys())


class ODataGrammar(abnf.Rule):
    pass


ODataGrammar.from_file(os.path.join(os.path.dirname(__file__), "data", "odata.abnf"))


class JSONEncoder(json.JSONEncoder):
    """JSON encoder that handles extra types compared to the
    built-in :class:`json.JSONEncoder`.

    -   :class:`datetime.datetime` and :class:`datetime.date` are
        serialized to :rfc:`822` strings. This is the same as the HTTP
        date format.
    -   :class:`uuid.UUID` is serialized to a string.
    """

    def default(self, o):
        if isinstance(o, datetime.datetime):
            if o.tzinfo:
                # eg: '2015-09-25T23:14:42.588601+00:00'
                return o.isoformat('T')
            else:
                # No timezone present - assume UTC.
                # eg: '2015-09-25T23:14:42.588601Z'
                return o.isoformat('T') + 'Z'

        if isinstance(o, datetime.date):
            return o.isoformat()

        if isinstance(o, uuid.UUID):
            return str(o)

        return json.JSONEncoder.default(self, o)


def build_response_headers(maxpagesize=None, metadata="full", version="4.0"):
    preferences = {}

    if maxpagesize:
        preferences["odata.maxpagesize"] = maxpagesize

    headers = {
        "Content-Type": "application/json;odata.metadata={};charset=utf-8".format(metadata),
        "OData-Version": "4.0",
        "Preference-Applied": ",".join(["{}={}".format(key, value) for key, value in preferences.items()])
    }
    return headers


def parse_key_value(key_value_node):
    if key_value_node.name == "keyPropertyValue":
        # keyPropertyValue are always a primitiveLiteral node
        value_node = key_value_node.children[0].children[0]
        return parse_primitive_literal(value_node)
    else:  # key_value_node == "parameterAlias"
        raise Exception("Not supported")


def parse_key_predicate(EntityType, key_predicate):
    key_properties = set(EntityType.key_properties)
    single_key = len(key_properties) == 1
    if key_predicate.children[0].name == "simpleKey":
        if not single_key:
            abort(400, "{} uses a compound key".format(EntityType.Name))

        key = tuple(key_properties)[0]
        id_value = parse_key_value(key_predicate.children[0].children[1])
        return {key: id_value}
    elif key_predicate.children[0].name == "compoundKey":
        keypairs = key_predicate.children[0].children[1:-1]
        key = {}
        for keypair in keypairs:
            if keypair.value == ",":
                continue

            key_id = keypair.children[0].value
            try:
                key_properties.remove(key_id)
            except KeyError:
                if key_id in EntityType.key_properties:
                    abort(400, "Duplicated key value for {}".format(key_id))
                else:
                    abort(400, "{} does not use {} as key property".format(EntityType.Name, key_id))

            key[key_id] = parse_key_value(keypair.children[2])

        if len(key_properties) > 0:
            abort(400, "The following key properties are missing: {}".format(key_properties))

        return key
    else:
        abort(501)


def parse_primitive_literal(node):
    value_type = node.name
    value = node.value
    if value_type == "string":
        return unquote(value)[1:-1].replace("''", "'")
    elif value_type in ("booleanValue", "decimalValue", "int16Value", "int32Value", "int64Value", "nullValue"):
        return json.loads(value)
    elif value_type in ("dateValue",):
        return arrow.get(value).datetime
    else:
        abort(501)


def process_common_expr(tree, filters, entity_type, prefix):
    if tree.children[0].name == "firstMemberExpr":
        expr = tree.children[1].children[3]
        if tree.children[1].name not in SUPPORTED_EXPRESSIONS:
            abort(501)

        if tree.children[1].name == "inExpr":
            value = [
                # First nodes are OPEN and BWS, last nodes are BWS and CLOSE
                parse_primitive_literal(node.children[0])
                for node in expr.children[2:-2]
                if node.name == "primitiveLiteral"
            ]
        else:
            if expr.children[0].name not in ("primitiveLiteral", "arrayOrObject"):
                abort(501)

            value_node = expr.children[0].children[0]
            if expr.children[0].name == "arrayOrObject":
                value = json.loads(expr.children[0].value)
            else:
                value = parse_primitive_literal(value_node)

        prop_name = tree.children[0].value
        if prefix != "" and prop_name not in entity_type.key_properties:
            field = "{}.{}".format(prefix, prop_name)
        else:
            field = prop_name

        expr_type = tree.children[1].name
        filters[field] = {
            EXPR_MAPPING[expr_type]: value
        }

        lastNode = expr.children[-1]
        if lastNode.name == "andExpr":
            process_common_expr(
                lastNode.children[3].children[0],
                filters,
                entity_type,
                prefix
            )
        elif lastNode.name == "orExpr":
            second_filter_exp = {}
            process_common_expr(
                lastNode.children[3].children[0],
                second_filter_exp,
                entity_type,
                prefix
            )
            filters["$or"] = [
                {field: filters[field]},
                second_filter_exp
            ]
            del filters[field]

    else:
        abort(501)


def parse_qs(qs):
    asdict = {}
    aslist = []
    for name_value in qs.split(b"&"):
        if not name_value:
            continue
        nv = name_value.split(b"=", 1)
        if len(nv) != 2:
            nv.append("")

        name = unquote(nv[0].replace(b"+", b" ").decode("utf-8"))
        value = nv[1].replace(b"+", b" ").decode("utf-8")
        aslist.append((name, value))
        asdict[name] = value

    return asdict


STRIP_WHITESPACE_FROM_URLENCODED_RE = re.compile(r"(?:^(?:\s|%20|%09|%0A|%0D|%0B|%0C)+|(?:\s|%20|%09|%0A|%0D|%0B|%0C)+$)")


def process_collection_filters(filter_arg, filters, entity_type, prefix=""):
    # Extra feature not required by OData spec: strip whitespace
    filter_arg = STRIP_WHITESPACE_FROM_URLENCODED_RE.sub("", filter_arg)
    if filter_arg != "":
        try:
            tree = ODataGrammar("commonExpr").parse_all(filter_arg)
        except abnf.parser.ParseError:
            abort(400)

        if tree.children[0].name == "parenExpr":
            tree = tree.children[0].children[2]

        process_common_expr(tree, filters, entity_type, prefix=prefix)

    return filters


def process_expand_tree(EntityType, nodes):
    expand_properties = {}
    for child in nodes:
        if child.name != "expandItem":
            continue

        item = child.children[0]
        if item.name != "expandPath":
            abort(501)

        if item.value == "*":
            expand_properties.update({np: None for np in EntityType.navproperties.keys()})
        elif item.children[0].name == "streamProperty":
            navprop = item.children[0].value
            if navprop not in EntityType.navproperties:
                abort(400)

            expand_properties[navprop] = None
        elif item.children[0].name == "navigationProperty":
            if len(item.children) != 4 or item.children[2].name != "expandOption" or item.children[2].children[0].name != "expand":
                abort(501)

            navprop = item.children[0].value
            if navprop not in EntityType.navproperties:
                abort(400)

            refEntityType = EntityType.navproperties[navprop].entity_type
            expand_properties[navprop] = process_expand_tree(
                refEntityType,
                item.children[2].children[0].children[2:]
            )
        else:
            abort(501)

    return tuple(expand_properties.items())


def process_expand_fields(EntitySet, EntityType, expand_value, projection, prefix=""):
    expand_arg = expand_value.strip()

    if expand_arg != "":
        try:
            expand_tree = ODataGrammar("expand").parse_all("$expand={}".format(expand_arg))
        except abnf.parser.ParseError:
            abort(400)

        expand_properties = process_expand_tree(EntityType, expand_tree.children[2:])
    else:
        expand_properties = ()

    return process_expand_details(EntitySet, EntityType, expand_properties, projection, prefix=prefix)


def process_expand_details(EntitySet, EntityType, expand_properties, projection, prefix=""):
    virtual_entities = EntityType.virtual_entities
    expand_details = {
        "key_props": EntityType.key_properties,
        "virtual": {
            "single": [],
            "collection": [],
        },
        "entities_to_query": set(),
    }

    for prop, extra in expand_properties:
        binding = EntitySet.bindings.get(prop)
        subtype = EntityType.navproperties[prop].entity_type
        path = "{}.{}".format(prefix, prop) if prefix != "" else prop
        extra_details = process_expand_details(
            binding if binding is not None else EntitySet,
            subtype,
            extra,
            projection,
            path if prop in virtual_entities else ""
        ) if extra else None

        if prop in virtual_entities:
            subproperties = subtype.Properties
            extrapropexpanded = set(prop for prop, _ in extra) if extra else set()

            if len(subtype.virtual_entities - extrapropexpanded) == 0:
                projection[path] = 1
                for subprop in extrapropexpanded:
                    subprop_path = "{}.{}".format(path, subprop)
                    if subprop_path in projection:
                        del projection[subprop_path]
            else:
                for subprop in subproperties:
                    if subprop.Name not in subtype.key_properties:
                        projection["{}.{}".format(path, subprop.Name)] = 1

            if EntityType.navproperties[prop].iscollection:
                expand_details["virtual"]["collection"].append((prop, binding, extra_details))
            else:
                expand_details["virtual"]["single"].append((prop, binding, extra_details))
        else:
            expand_details["entities_to_query"].add((prop, binding, extra_details))

    return expand_details


def format_literal(value):
    if type(value) == str:
        return "'{}'".format(value)
    else:
        return value


def format_key_predicate(id_value):
    if len(id_value) == 1:
        return format_literal(tuple(id_value.values())[0])
    else:
        return ",".join("{}={}".format(key, format_literal(value)) for key, value in id_value.items())


def expand_result(EntitySet, expand_details, result, prefix=""):
    main_id = {
        key_prop: result[key_prop]
        for key_prop in expand_details["key_props"] if key_prop != "Seq"
    }
    for prop, binding, extra in expand_details["virtual"]["single"]:
        if result.get(prop) is None:
            continue
        path = "{}.{}".format(prefix, prop) if prefix != "" else prop
        result[prop].update(main_id)
        if binding is not None:
            add_odata_annotations(result[prop], binding)
            if extra:
                expand_result(binding, extra, result[prop])
        else:
            keyPredicate = format_key_predicate(main_id)
            anchor = "{}({})/{}".format(EntitySet.Name, keyPredicate, path)
            result["{}@odata.context".format(prop)] = "{}#{}".format(url_for("odata.$metadata", _external=True).replace("%24", "$"), anchor)
            if extra:
                expand_result(EntitySet, extra, result[prop], prefix=path)

    for prop, binding, extra in expand_details["virtual"]["collection"]:
        if result.get(prop) is None:
            result[prop] = []

        path = "{}.{}".format(prefix, prop) if prefix != "" else prop
        if binding is None:
            keyPredicate = format_key_predicate(main_id)
            anchor = "{}({})/{}".format(EntitySet.Name, keyPredicate, path)
            result["{}@odata.context".format(prop)] = "{}#{}".format(url_for("odata.$metadata", _external=True).replace("%24", "$"), anchor)

        for i, e in enumerate(result[prop]):
            if binding is not None:
                add_odata_annotations(e, binding)
                if extra:
                    expand_result(binding, extra, e)
            elif extra:
                expand_result(EntitySet, extra, e, prefix=path)

            e.update(main_id)

    return result


def add_odata_annotations(data, entity_set):
    id_value = {
        prop: data[prop]
        for prop in entity_set.entity_type.key_properties
    }
    key_predicate = format_key_predicate(id_value)
    data["@odata.id"] = "{}({})".format(url_for("odata.{}".format(entity_set.Name), _external=True), key_predicate)
    data["@odata.etag"] = 'W/"{}"'.format(data["uuid"])
    del data["uuid"]

    return data


def build_initial_projection(entity_type, select="", prefix=""):
    projection = {
        "_id": 0,
        "uuid": 1,
    }

    if prefix != "":
        prefix += "."

    if select == "*":
        select = ""

    if select == "":
        select = [p.Name for p in entity_type.property_list]
    else:
        select = select.split(",")

    for p in select:
        if p in entity_type.key_properties:
            projection[p] = 1
        else:
            projection["{}{}".format(prefix, p)] = 1

    return projection


def crop_result(result, prefix):
    if prefix == "":
        return result

    if "." not in prefix:
        paths = [prefix]
    else:
        paths = prefix.split(".")

    root = paths.pop(0)
    if root in result:
        value = result[root]
        for path in paths:
            if path in value:
                value = value[path]
            else:
                value = {}
                break

        result.update(value)
        del result[root]

    return result


def get_collection(mongo, RootEntitySet, subject, prefers, filters=None, count=False):
    qs = parse_qs(request.query_string)

    # Parse basic options
    if filters is None:
        # TODO allow to customize this filter
        filters = {
            "uuid": {"$exists": True}
        }

    top = request.args.get("$top")
    page_limit = int(top) if top is not None else prefers["maxpagesize"]
    limit = page_limit if top is not None else page_limit + 1
    offset = int(request.args.get("$skip", "0"))

    # Check if we need to apply a prefix to mongodb fields
    if isinstance(subject, edm.NavigationProperty):
        prefix = subject.Name if subject.isembedded and subject.entity_type != RootEntitySet.entity_type else ""
        if RootEntitySet.prefix != "" and prefix != "":
            prefix = "{}.{}".format(RootEntitySet.prefix, prefix)
        elif RootEntitySet.prefix != "" and prefix == "":
            prefix = RootEntitySet.prefix
    else:
        prefix = subject.prefix

    select = request.args.get("$select", "")
    projection = build_initial_projection(subject.entity_type, select, prefix=prefix)

    # Process filters
    filter_arg = qs.get("$filter", "").strip()
    filters = process_collection_filters(filter_arg, filters, subject.entity_type, prefix=prefix)

    # Process expand fields
    expand_details = process_expand_fields(RootEntitySet, subject.entity_type, request.args.get("$expand", ""), projection, prefix=prefix)

    # Process orderby
    orderby = []
    orderby_arg = request.args.get("$orderby", "").strip()
    if orderby_arg != "":
        try:
            tree = ODataGrammar("orderbyExpr").parse_all(orderby_arg)
        except abnf.parser.ParseError:
            abort(400)

        orderbyItem = tree.children[0]
        orderby.append((
            orderbyItem.children[0].value,
            1 if len(orderbyItem.children) == 1 or orderbyItem.children[2].value.lower() == "asc" else -1)
        )

    # Get the results
    # TODO Streaming
    mongo_collection = mongo.get_collection(RootEntitySet.mongo_collection)
    if prefix:
        seq_filter = {"Seq": filters.pop("Seq")} if "Seq" in filters else None
        pipeline = [
            {"$match": filters},
        ]
        if "Seq" in subject.entity_type.key_properties:
            pipeline.append({
                "$unwind": {
                    "path": "${}".format(prefix),
                    "includeArrayIndex": "Seq"
                }
            })
        else:
            pipeline.append({"$unwind": "${}".format(prefix)})

        if seq_filter is not None:
            pipeline.append({"$match": seq_filter})

        basepipeline = pipeline.copy()
        if len(orderby) > 0:
            pipeline.append({"$sort": SON(orderby)})
        pipeline.append({"$project": projection})
        pipeline.append({"$skip": offset})
        pipeline.append({"$limit": limit})
        results = tuple(mongo_collection.aggregate(pipeline))
    else:
        cursor = mongo_collection.find(filters, projection)
        if len(orderby) > 0:
            cursor = cursor.sort(orderby)
        results = tuple(cursor.skip(offset).limit(limit))

    hasnext = top is None and len(results) > page_limit

    if isinstance(subject, edm.EntitySet):
        results = [add_odata_annotations(expand_result(RootEntitySet, expand_details, crop_result(r, prefix), prefix=prefix), RootEntitySet) for r in results[:page_limit]]
    else:
        results = [expand_result(RootEntitySet, expand_details, crop_result(r, prefix), prefix=prefix) for r in results[:page_limit]]

    data = {}

    data["@odata.context"] = "{}#{}".format(
        url_for("odata.$metadata", _external=True).replace("%24", "$"),
        RootEntitySet.Name
    )

    if count:
        if prefix == "":
            count = mongo_collection.count_documents(filters)
        else:
            # Remove skip and limit stages from the pipeline
            basepipeline.append({"$count": "count"})
            result = tuple(mongo_collection.aggregate(basepipeline))
            count = 0 if len(result) == 0 else result[0]["count"]
        data["@odata.count"] = count

    if hasnext:
        query_params = request.args.copy()
        query_params["$skip"] = offset + page_limit

        data["@odata.nextLink"] = "{}?{}".format(
            url_for("odata.{}".format(RootEntitySet.Name), _external=True),
            urlencode(query_params)
        )

    data["value"] = results

    headers = build_response_headers(maxpagesize=page_limit if top is None else None)
    return make_response(data, status=200, headers=headers)


def make_response(data, status=200, etag=None, headers={}):
    body = json.dumps(data, ensure_ascii=False, sort_keys=True, cls=JSONEncoder).encode("utf-8")
    response = Response(body, status, headers=headers)
    if etag is not None:
        response.set_etag(etag, weak=True)
    else:
        response.add_etag(weak=True)
    return response.make_conditional(request)
