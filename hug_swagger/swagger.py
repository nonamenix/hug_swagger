import logging
from inspect import signature, Parameter, isclass
from typing import Optional, Tuple

from apispec import APISpec
from apispec.exceptions import DuplicateComponentNameError
from apispec.ext.marshmallow import MarshmallowPlugin, OpenAPIConverter, resolver
from hug import API
from hug.interface import Interface, HTTP
from marshmallow import fields, Schema

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost:8080"
DEFAULT_SCHEMES = ("http",)
DEFAULT_OPENAPI_VERSION = "3.0.2"
DEFAULT_TITLE = "Swagger Documentation for your application"

PARAMETER_IN_PATH = "path"
PARAMETER_IN_QUERY = "query"


def get_summary(doc: Optional[str]) -> Optional[str]:
    if doc is not None:
        return doc.split("\n")[0]


def get_parameter_location(name: str, url: str) -> str:
    return PARAMETER_IN_PATH if "{%s}" % name in url else PARAMETER_IN_QUERY


def get_parameters(converter: OpenAPIConverter, spec: APISpec, interface: Interface, url: str):
    original_handler = interface.interface.spec
    handler_signature = signature(original_handler)

    parameters = []
    for name, handler_parameter in handler_signature.parameters.items():
        parameter_kind = handler_parameter.annotation  # TODO: support `args` argument to routing decorator

        # TODO: do we need to skip anything else?
        if getattr(parameter_kind, "directive", False) or name.startswith("hug_") or name in ("request", "response"):
            # skip directives and helper auto-included arguments
            continue

        if isinstance(parameter_kind, fields.Field):
            parameter_place = get_parameter_location(name, url)
            parameter_kind.metadata = {"location": parameter_place}

            parameter = converter.field2parameter(parameter_kind, name=name, default_in=parameter_place)

            has_default = handler_parameter.default != Parameter.empty
            required = True
            if has_default:
                parameter["default"] = handler_parameter.default
                required = False

            parameter["required"] = required
            parameters.append(parameter)

        elif name == "body":
            is_schema_class = isclass(parameter_kind) and issubclass(parameter_kind, Schema)

            if not isinstance(parameter_kind, Schema) and not is_schema_class:
                # if not Schema class or Schema instance, skip
                continue

            schema = parameter_kind() if is_schema_class else parameter_kind
            schema_name = f"{schema.__module__}.{schema.__class__.__name__}"

            try:
                spec.components.schema(schema_name, schema=schema)
            except DuplicateComponentNameError:  # schemas can be reused, no big deal
                pass

            ref_definition = f"#/components/schemas/{schema_name}"
            ref_schema = {"$ref": ref_definition}

            parameters.append({
                "in": "body", "name": "body", "required": True, "schema": ref_schema
            })

    return parameters

def generate_spec(
    hug_api: API,
    title: str = DEFAULT_TITLE,
    version: Optional[str] = None,
    openapi_version: str = DEFAULT_OPENAPI_VERSION,
    host: str = DEFAULT_HOST,
    schemes: Tuple[str, ...] = DEFAULT_SCHEMES,
    **options,
) -> dict:
    options["host"] = host
    options["schemes"] = schemes

    marshmallow_plugin = MarshmallowPlugin()
    spec = APISpec(
        title=title,
        version=version,
        openapi_version=openapi_version,
        plugins=(marshmallow_plugin,),
        **options,
    )
    converter = OpenAPIConverter(
        openapi_version=openapi_version, schema_name_resolver=resolver, spec=spec
    )

    routes = hug_api.http.routes
    if not routes:
        # no routes in application so just return here
        return spec.to_dict()

    relative_routes = routes[""]  # routes relative to a base url, which is ''
    for url, route in relative_routes.items():
        for method, versioned_interfaces in route.items():
            for versions, interface in versioned_interfaces.items():
                handler_spec = {}

                documentation = interface.documentation()
                handler_spec["content_type"] = documentation["outputs"]["content_type"]
                # documentation["usage"] will contain route handler's docstring
                # or None if it was not present
                usage = documentation.get("usage")
                if usage:
                    handler_spec["summary"] = get_summary(usage)
                    handler_spec["description"] = usage

                parameters = get_parameters(converter, spec, interface, url)
                if parameters:
                    handler_spec["parameters"] = parameters

                spec.path(url, operations={method.lower(): handler_spec})

    return spec.to_dict()
