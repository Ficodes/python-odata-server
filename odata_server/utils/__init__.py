# Copyright (c) 2021-2022 Future Internet Consulting and Development Solutions S.L.

import re

import abnf
import pymongo.database
import pymongo.errors
from bson.son import SON
from flask import abort, request, url_for

from odata_server import edm, settings

from .common import crop_result, format_key_predicate
from .flask import add_odata_annotations
from .http import build_response_headers, make_response
from .json import generate_collection_response
from .mongo import build_initial_projection, get_mongo_prefix
from .parse import (
    ODataGrammar,
    parse_array_or_object,
    parse_orderby,
    parse_primitive_literal,
    parse_qs,
)

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


def process_common_expr(tree, filters, entity_type, prefix, joinop="andExpr"):
    if joinop == "orExpr":
        filters.append({})

    if tree.children[0].name == "parenExpr":
        if len(tree.children) == 1:
            tree = tree.children[0].children[2]
        elif len(tree.children) == 2 and tree.children[1].name in ("orExpr", "andExpr"):
            process_common_expr(
                tree.children[0].children[2], filters, entity_type, prefix
            )

            if tree.children[1].name == "andExpr" and len(filters) > 1:
                or_filters = filters.copy()
                filters.clear()
                filters.append({"$or": or_filters})

            return process_common_expr(
                tree.children[1].children[3].children[0],
                filters,
                entity_type,
                prefix,
                tree.children[1].name,
            )
        else:
            abort(501)

    expresion_name = tree.children[0].name
    if expresion_name == "firstMemberExpr":
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

            if expr.children[0].name == "arrayOrObject":
                value = parse_array_or_object(expr.children[0])
            else:
                value = parse_primitive_literal(expr.children[0].children[0])

        prop_name = tree.children[0].value
        if prefix != "" and prop_name not in entity_type.key_properties:
            field = f"{prefix}.{prop_name}"
        else:
            field = prop_name

        expr_type = tree.children[1].name
        current_filter = filters[-1].setdefault(field, {})
        mongo_op = EXPR_MAPPING[expr_type]
        if mongo_op in current_filter:
            # Resolve conflict
            if expr_type in ("gtExpr", "geExpr"):
                current_filter[mongo_op] = max(value, current_filter[mongo_op])
            elif expr_type in ("ltExpr", "leExpr"):
                current_filter[mongo_op] = min(value, current_filter[mongo_op])
            elif expr_type in ("eqExpr", "neExpr"):
                if current_filter[mongo_op] == value:
                    # Ignore this clasule as is the same than the current one
                    pass
                else:
                    # TODO this case will return no results as it is impossible to be
                    # equal to two values at the same time
                    abort(501)
            else:  # elif expr_type == "inExpr"
                current_filter[mongo_op] = list(
                    set(current_filter[mongo_op]).intersection(set(value))
                )
        elif expr_type == "inExpr":
            current_filter[mongo_op] = list(dict.fromkeys(value))
        else:
            current_filter[mongo_op] = value

        lastNode = expr.children[-1]
    elif (
        expresion_name == "methodCallExpr"
        and tree.children[0].children[0].name == "boolMethodCallExpr"
    ):
        methodExpr = tree.children[0].children[0].children[0]
        args = [
            node.children[0]
            for node in methodExpr.children[2:-1]
            if node.name == "commonExpr"
        ]
        prop_name = args[0].value
        if prefix != "" and prop_name not in entity_type.key_properties:
            field = "{}.{}".format(prefix, prop_name)
        else:
            field = prop_name

        negation = False
        if len(tree.children) > 1 and tree.children[1].name == "eqExpr":
            # Move tree to skip the eqExpr node
            tree = tree.children[1].children[3]
            if tree.name == "primitiveLiteral":
                negation = tree.value != "true"
            else:  # if tree.name = "commonExpr":
                negation = tree.children[0].value != "true"

        if methodExpr.name in (
            "containsMethodCallExpr",
            "startsWithMethodCallExpr",
            "endsWithMethodCallExpr",
        ):
            regex_literal = re.escape(parse_primitive_literal(args[1].children[0]))
            if methodExpr.name == "containsMethodCallExpr":
                filters[-1][field] = {
                    "$regex": (
                        "(?!{})".format(regex_literal) if negation else regex_literal
                    )
                }
            elif methodExpr.name == "startsWithMethodCallExpr":
                filters[-1][field] = {
                    "$regex": ("^(?!{})" if negation else "^{}").format(regex_literal)
                }
            elif methodExpr.name == "endsWithMethodCallExpr":
                filters[-1][field] = {
                    "$regex": ("(?<!{})$" if negation else "{}$").format(regex_literal)
                }
        elif methodExpr.name == "hasSubsetMethodCallExpr":
            # args[1] is always a commonExpr node
            second_argument = args[1]
            if (
                second_argument.name != "arrayOrObject"
                or second_argument.children[0].name != "array"
            ):
                abort(400, "hasubset: Second argument must be a collection")

            subset = parse_array_or_object(second_argument)
            filters[-1][field] = {
                "$all": subset,
            }
        else:
            abort(501)
        lastNode = tree.children[-1]
    else:
        abort(501)

    if lastNode.name in ("orExpr", "andExpr"):
        process_common_expr(
            lastNode.children[3].children[0],
            filters,
            entity_type,
            prefix,
            lastNode.name,
        )


def process_collection_filters(filter_arg, search_arg, filters, entity_type, prefix=""):
    if filter_arg != "":
        try:
            tree = ODataGrammar("commonExpr").parse_all(filter_arg)
        except abnf.parser.ParseError:
            abort(400)

        new_filters = [{}]
        process_common_expr(tree, new_filters, entity_type, prefix, "andExpr")

        if len(new_filters) > 1:
            filters["$or"] = new_filters
        else:
            filters.update(new_filters[0])

    if search_arg != "":
        filters["$text"] = {"$search": search_arg}

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
            expand_properties.update(
                {np: None for np in EntityType.navproperties.keys()}
            )
        elif item.children[0].name == "streamProperty":
            navprop = item.children[0].value
            if navprop not in EntityType.navproperties:
                abort(400)

            expand_properties[navprop] = None
        elif item.children[0].name == "navigationProperty":
            if (
                len(item.children) != 4
                or item.children[2].name != "expandOption"
                or item.children[2].children[0].name != "expand"
            ):
                abort(501)

            navprop = item.children[0].value
            if navprop not in EntityType.navproperties:
                abort(400)

            refEntityType = EntityType.navproperties[navprop].entity_type
            expand_properties[navprop] = process_expand_tree(
                refEntityType, item.children[2].children[0].children[2:]
            )
        else:
            abort(501)

    return tuple(expand_properties.items())


def process_expand_fields(EntitySet, EntityType, expand_value, projection, prefix=""):
    expand_arg = expand_value.strip()

    if expand_arg != "":
        try:
            expand_tree = ODataGrammar("expand").parse_all(
                "$expand={}".format(expand_arg)
            )
        except abnf.parser.ParseError:
            abort(400)

        expand_properties = process_expand_tree(EntityType, expand_tree.children[2:])
    else:
        expand_properties = ()

    return process_expand_details(
        EntitySet, EntityType, expand_properties, projection, prefix=prefix
    )


def process_expand_details(
    EntitySet, EntityType, expand_properties, projection, prefix=""
):
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
        extra_details = (
            process_expand_details(
                binding if binding is not None else EntitySet,
                subtype,
                extra,
                projection,
                path if prop in virtual_entities else "",
            )
            if extra
            else None
        )

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
                expand_details["virtual"]["collection"].append(
                    (prop, binding, extra_details)
                )
            else:
                expand_details["virtual"]["single"].append(
                    (prop, binding, extra_details)
                )
        else:
            expand_details["entities_to_query"].add((prop, binding, extra_details))

    return expand_details


def expand_result(EntitySet, expand_details, result, prefix=""):
    main_id = {
        key_prop: result[key_prop]
        for key_prop in expand_details["key_props"]
        if key_prop != "Seq"
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
            result["{}@odata.context".format(prop)] = "{}#{}".format(
                url_for("odata.$metadata", _external=True).replace("%24", "$"), anchor
            )
            if extra:
                expand_result(EntitySet, extra, result[prop], prefix=path)

    for prop, binding, extra in expand_details["virtual"]["collection"]:
        if result.get(prop) is None:
            result[prop] = []

        path = "{}.{}".format(prefix, prop) if prefix != "" else prop
        if binding is None:
            keyPredicate = format_key_predicate(main_id)
            anchor = "{}({})/{}".format(EntitySet.Name, keyPredicate, path)
            result["{}@odata.context".format(prop)] = "{}#{}".format(
                url_for("odata.$metadata", _external=True).replace("%24", "$"), anchor
            )

        for i, e in enumerate(result[prop]):
            if binding is not None:
                add_odata_annotations(e, binding)
                if extra:
                    expand_result(binding, extra, e)
            elif extra:
                expand_result(EntitySet, extra, e, prefix=path)

            e.update(main_id)

    return result


def prepare_entity_set_result(
    result, RootEntitySet, expand_details, prefix, fields_to_remove
):
    croped_result = crop_result(result, prefix)
    expanded_result = expand_result(
        RootEntitySet, expand_details, croped_result, prefix=prefix
    )
    annotated_result = add_odata_annotations(expanded_result, RootEntitySet)
    for field in fields_to_remove:
        del annotated_result[field]

    return annotated_result


def prepare_anonymous_result(result, RootEntitySet, expand_details, prefix):
    croped_result = crop_result(result, prefix)
    return expand_result(RootEntitySet, expand_details, croped_result, prefix=prefix)


def get_collection(
    db: pymongo.database.Database,
    RootEntitySet,
    subject,
    prefers,
    filters=None,
    count=False,
):
    qs = parse_qs(request.query_string)
    anonymous = not isinstance(subject, edm.EntitySet)

    # Parse basic options
    if filters is None:
        # TODO allow to customize this filter
        filters = {"uuid": {"$exists": True}}

    top = qs.get("$top")
    page_limit = int(top) if top is not None else prefers["maxpagesize"]
    limit = page_limit if top is not None else page_limit + 1
    offset = int(qs.get("$skip", "0"))

    # Check if we need to apply a prefix to mongodb fields
    prefix = get_mongo_prefix(RootEntitySet, subject)

    select = qs.get("$select", "")
    projection, fields_to_remove = build_initial_projection(
        subject.entity_type, select, prefix=prefix, anonymous=anonymous
    )

    # Process filters
    filter_arg = qs.get("$filter", "")
    search_arg = qs.get("$search", "")
    filters = process_collection_filters(
        filter_arg, search_arg, filters, subject.entity_type, prefix=prefix
    )

    # Process expand fields
    expand_details = process_expand_fields(
        RootEntitySet,
        subject.entity_type,
        qs.get("$expand", ""),
        projection,
        prefix=prefix,
    )

    # Process orderby
    orderby = parse_orderby(qs.get("$orderby", ""))

    # Get the results
    mongo_collection = db.get_collection(
        RootEntitySet.mongo_collection,
    ).with_options(
        read_preference=pymongo.ReadPreference.SECONDARY_PREFERRED,
    )
    if prefix:
        seq_filter = {"Seq": filters.pop("Seq")} if "Seq" in filters else None
        pipeline = [
            {"$match": filters},
        ]
        if "Seq" in subject.entity_type.key_properties:
            pipeline.append(
                {"$unwind": {"path": "${}".format(prefix), "includeArrayIndex": "Seq"}}
            )
        else:
            pipeline.append({"$unwind": "${}".format(prefix)})

        if seq_filter is not None:
            pipeline.append({"$match": seq_filter})

        # Save a version of the pipeline without the sort, project, skip and
        # limit stages
        basepipeline = pipeline.copy()
        if len(orderby) > 0:
            pipeline.append({"$sort": SON(orderby)})
        pipeline.append({"$project": projection})
        pipeline.append({"$skip": offset})
        pipeline.append({"$limit": limit})
        results = mongo_collection.aggregate(
            pipeline, maxTimeMS=settings.MONGO_SEARCH_MAX_TIME_MS
        )
    else:
        cursor = mongo_collection.find(filters, projection).max_time_ms(
            settings.MONGO_SEARCH_MAX_TIME_MS
        )
        if len(orderby) > 0:
            cursor = cursor.sort(orderby)
        results = cursor.skip(offset).limit(limit)

    if count:
        if prefix == "":
            try:
                count = mongo_collection.count_documents(
                    filters, maxTimeMS=settings.MONGO_COUNT_MAX_TIME_MS
                )
            except pymongo.errors.ExecutionTimeout:
                abort(503)
        else:
            basepipeline.append({"$count": "count"})
            result = tuple(
                mongo_collection.aggregate(
                    basepipeline, maxTimeMS=settings.MONGO_COUNT_MAX_TIME_MS
                )
            )
            count = 0 if len(result) == 0 else result[0]["count"]
        odata_count = count
    else:
        odata_count = None

    odata_context = "{}#{}".format(
        url_for("odata.$metadata", _external=True).replace("%24", "$"),
        RootEntitySet.Name,
    )
    prepare_kwargs = {
        "RootEntitySet": RootEntitySet,
        "expand_details": expand_details,
        "prefix": prefix,
        "fields_to_remove": fields_to_remove,
    }
    data = generate_collection_response(
        results,
        offset,
        page_limit,
        prepare_anonymous_result if anonymous else prepare_entity_set_result,
        odata_context,
        odata_count=odata_count,
        prepare_kwargs=prepare_kwargs,
    )
    headers = build_response_headers(
        streaming=True, maxpagesize=page_limit if top is None else None
    )
    return make_response(data, status=200, headers=headers)
