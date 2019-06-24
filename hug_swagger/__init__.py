import collections
from copy import copy
import inspect
import logging
import importlib

from apispec import APISpec
from apispec.ext.marshmallow.swagger import field2parameter
import hug
from marshmallow import fields, Schema
from marshmallow.schema import SchemaMeta

from yzconfig import YzConfig

from . import swagger

logger = logging.getLogger(__name__)


class Settings(YzConfig):
    HOST = 'localhost:9001'
    SCHEMES = ['http']
    VERSION = '0.1'
    TITLE = 'Swagger Application'
    DEFINITIONS_PATH = None
    TESTING_MODE = False
    USE_DEFAULT_RESPONSE = True
    DESCRIPTION = ''


settings = Settings('SWAGGER_')
del Settings


def get_summary(description):
    return description.split('\n')[0]


def where_is_parameter(name, url):
    # TODO: body, header
    return 'path' if '{%s}' % name in url else 'query'


def get_handler(interface):
    return interface.interface.spec


def get_parameters(url, interface, spec):
    defaults = interface.defaults
    sig = inspect.signature(get_handler(interface))

    parameters = []
    for name in interface.parameters:

        parameter_type = sig.parameters[name].annotation
        if getattr(parameter_type, 'directive', False):
            logger.info('Skip directive: %s for url: %s ', name, url)
            continue

        if parameter_type != inspect.Parameter.empty:
            # path and query
            if isinstance(parameter_type, fields.Field):
                parameter_place = where_is_parameter(name, url)
                parameter_type.metadata = {
                    'location': where_is_parameter(name, url)}
                parameter_type.required = name not in defaults
                parameter = field2parameter(
                    parameter_type, name=name, default_in=parameter_place, use_refs=False)
                if name in defaults:
                    parameter['default'] = defaults[name]
                parameters.append(parameter)
            # body
            elif name == 'body' and (isinstance(parameter_type, Schema) or isinstance(parameter_type, SchemaMeta)):
                if isinstance(parameter_type, Schema):
                    schema_name = parameter_type.__class__.__name__
                    schema = parameter_type
                elif isinstance(parameter_type, SchemaMeta):
                    schema_name = parameter_type.__name__
                    schema = parameter_type()

                spec.definition(schema_name, schema=schema)

                ref_definition = "#/definitions/{}".format(schema_name)
                ref_schema = {"$ref": ref_definition}

                parameters.append({
                    "in": "body",
                    "name": "body",
                    "required": True,
                    "schema": ref_schema
                })

            else:
                logger.error(
                    'Use marshmallow fields in url: %s instead of hug: %s %s', url, name, parameter_type)
        else:
            logger.info(
                'There is no type annotation for %s in url: %s', name, url)
            # pass
    return parameters


def get_operation(interface, spec, use_default_response):
    handler = get_handler(interface)
    sig = inspect.signature(handler)  # type: Signature
    annotated_response_schema = sig.return_annotation
    responses = copy(getattr(handler, 'swagger_responses', {}))

    if annotated_response_schema != inspect.Parameter.empty:
        responses.setdefault(200, {})['schema'] = annotated_response_schema

    if use_default_response:
        responses.setdefault(200, {})  # TODO: get: 200, post: 201

    for code, response in responses.items():
        response = copy(response)
        try:
            schema = response['schema']
            if isinstance(schema, str):  # schema name provided
                name = schema
            elif isinstance(schema, Schema):  # schema instance provided
                name = schema.__class__.__name__
                spec.definition(name, schema=schema)
            elif isinstance(schema, SchemaMeta):  # schema class provided
                name = schema.__name__
                spec.definition(name, schema=schema())
            else:
                logger.error('Wrong response schema %s', schema)
                schema = None
        except KeyError:
            pass
        else:
            if schema is not None:
                ref_name = '#/definitions/{}'.format(name)
                ref_schema = {'$ref': ref_name}
                response["schema"] = ref_schema
            responses[code] = response

    return responses


@hug.get('/swagger.json')
def swagger_json(hug_api):
    spec = APISpec(
        title=settings.TITLE,
        description=settings.DESCRIPTION,
        version=settings.VERSION,
        plugins=(
            'apispec.ext.marshmallow',
        ),
        schemes=settings.SCHEMES,
        host=settings.HOST
    )

    if settings.DEFINITIONS_PATH is not None:
        definitions = importlib.import_module(settings.DEFINITIONS_PATH)

        for name, schema in definitions.__dict__.items():  # type: str, Schema
            if name.endswith('Schema') and len(name) > len('Schema'):
                spec.definition(name, schema=schema)

    routes = hug_api.http.routes['']

    for url, route in routes.items():
        for method, versioned_interfaces in route.items():
            for versions, interface in versioned_interfaces.items():
                methods_data = {}

                documentation = interface.documentation()
                methods_data['content_type'] = documentation['outputs']['content_type']

                try:
                    methods_data['summary'] = get_summary(
                        documentation['usage'])
                    methods_data['description'] = documentation['usage']
                except KeyError:
                    pass

                parameters = get_parameters(url, interface, spec)
                if parameters:
                    methods_data['parameters'] = parameters

                responses = get_operation(
                    interface, spec, settings.USE_DEFAULT_RESPONSE)
                if responses:
                    methods_data['responses'] = responses

                if not isinstance(versions, collections.Iterable):
                    versions = [versions]

                for version in versions:
                    versioned_url = '/v{}{}'.format(version,
                                                    url) if version else url

                    spec.add_path(versioned_url, operations={
                        method.lower(): methods_data
                    })

    return spec.to_dict()
