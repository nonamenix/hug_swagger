import pytest
from hug import API, route, directive
from hug.directives import Timer
from marshmallow import fields, Schema

from hug_swagger.swagger import (
    generate_spec,
    DEFAULT_TITLE,
    DEFAULT_OPENAPI_VERSION,
    DEFAULT_HOST,
    DEFAULT_SCHEMES,
)


@pytest.fixture()
def test_api():
    api = API(__name__)
    yield api
    api.http.routes.clear()


def _generate_spec(api: API, **options):
    filled_options = {
        name: option for name, option in options.items() if option is not None
    }
    return generate_spec(api, **filled_options)


def test_summary_and_description(test_api):
    @route.get("/")
    def with_documentation():
        """
        Handler summary.
        Handler detailed information.
        """
        return "text"

    spec = _generate_spec(test_api)
    handler_spec = spec["paths"]["/"]["get"]
    assert handler_spec["summary"] == "Handler summary."
    assert handler_spec["description"] == "Handler detailed information."


@pytest.mark.parametrize("title,spec_title", ((None, DEFAULT_TITLE), ("foo", "foo")))
def test_title(test_api, title, spec_title):
    spec = _generate_spec(test_api, title=title)
    assert spec["info"]["title"] == spec_title


@pytest.mark.parametrize("version,spec_version", ((None, None), ("1.0", "1.0")))
def test_version(test_api, version, spec_version):
    spec = _generate_spec(test_api, version=version)
    assert spec["info"]["version"] == spec_version


@pytest.mark.parametrize(
    "openapi_version,spec_openapi_version",
    ((None, DEFAULT_OPENAPI_VERSION), ("2.1", "2.1"), ("3.1", "3.1")),
)
def test_openapi_version(test_api, openapi_version, spec_openapi_version):
    spec = _generate_spec(test_api, openapi_version=openapi_version)
    if openapi_version and openapi_version[0] == "2":
        assert spec["swagger"] == spec_openapi_version
    else:
        assert spec["openapi"] == spec_openapi_version


@pytest.mark.parametrize("host,spec_host", ((None, DEFAULT_HOST), ("foo", "foo")))
def test_host(test_api, host, spec_host):
    spec = _generate_spec(test_api, host=host)
    assert spec["host"] == spec_host


@pytest.mark.parametrize(
    "schemes,spec_schemes",
    ((None, DEFAULT_SCHEMES), (("http", "https"), ("http", "https"))),
)
def test_schemes(test_api, schemes, spec_schemes):
    spec = _generate_spec(test_api, schemes=schemes)
    assert spec["schemes"] == spec_schemes


def test_with_special_parameters(test_api):
    @route.get("/with_request")
    def with_request_parameter(request):
        return "foo"

    @route.get("/with_response")
    def with_response_parameter(response):
        return "bar"

    spec = generate_spec(test_api)
    assert "parameters" not in spec["paths"]["/with_request"]["get"]
    assert "parameters" not in spec["paths"]["/with_response"]["get"]


def test_directives(test_api):
    @directive
    def my_directive(**kwargs):
        return "foo"

    @route.get("/with_custom_directive")
    def with_custom_directive(my_directive):
        return "foo"

    @route.get("/with_annotated_directive")
    def with_annotated_directive(timer: Timer):
        return "foo"

    @route.get("/with_prefixed_directive")
    def with_prefixed_directive(hug_timer):
        return "foo"

    spec = generate_spec(test_api)
    assert "parameters" not in spec["paths"]["/with_custom_directive"]["get"]
    assert "parameters" not in spec["paths"]["/with_annotated_directive"]["get"]
    assert "parameters" not in spec["paths"]["/with_prefixed_directive"]["get"]


def test_wrong_body_type(test_api):
    class A:
        pass

    @route.get("/with_class")
    def with_class(body: A):
        return "foo"

    @route.get("/with_instance")
    def with_instance(body: A()):
        return "foo"

    spec = generate_spec(test_api)
    assert "parameters" not in spec["paths"]["/with_class"]["get"]
    assert "parameters" not in spec["paths"]["/with_instance"]["get"]


def test_with_validated_parameter(test_api):
    @route.get("/foo")
    def with_validated_int_parameter(foo: fields.Integer()):
        return "foo"

    @route.get("/bar")
    def with_validated_string_parameter(bar: fields.String()):
        return "bar"

    spec = generate_spec(test_api)

    foo_parameter = spec["paths"]["/foo"]["get"]["parameters"][0]

    assert foo_parameter["in"] == "query"
    assert foo_parameter["name"] == "foo"
    assert foo_parameter["required"]
    assert foo_parameter["schema"] == {"format": "int32", "type": "integer"}

    bar_parameter = spec["paths"]["/bar"]["get"]["parameters"][0]

    assert bar_parameter["in"] == "query"
    assert bar_parameter["name"] == "bar"
    assert bar_parameter["schema"] == {"type": "string"}


def test_with_default_parameter(test_api):
    @route.get("/")
    def with_default_parameter(foo: fields.Integer() = 5):
        return "foo"

    spec = generate_spec(test_api)

    parameter = spec["paths"]["/"]["get"]["parameters"][0]

    assert parameter["in"] == "query"
    assert parameter["name"] == "foo"
    assert not parameter["required"]
    assert parameter["schema"] == {"format": "int32", "type": "integer"}


def test_with_body_schema(test_api):
    class BodySchema(Schema):
        a = fields.Integer(required=True)
        b = fields.String()

    @route.post("/foo")
    def with_body_schema_class(body: BodySchema):
        return ""

    @route.post("/bar")
    def with_body_schema_instance(body: BodySchema()):
        return ""

    spec = generate_spec(test_api)

    schema_name = f"{BodySchema.__module__}.BodySchema"

    foo_parameter = spec["paths"]["/foo"]["post"]["parameters"][0]
    assert foo_parameter["in"] == "body"
    assert foo_parameter["name"] == "body"
    assert foo_parameter["required"]
    assert foo_parameter["schema"] == {"$ref": f"#/components/schemas/{schema_name}"}

    bar_parameter = spec["paths"]["/bar"]["post"]["parameters"][0]

    assert bar_parameter["in"] == "body"
    assert bar_parameter["name"] == "body"
    assert bar_parameter["required"]
    assert bar_parameter["schema"] == {"$ref": f"#/components/schemas/{schema_name}"}

    schema = spec["components"]["schemas"][schema_name]

    assert schema == {
        "properties": {
            "a": {"format": "int32", "type": "integer"},
            "b": {"type": "string"},
        },
        "required": ["a"],
        "type": "object",
    }
