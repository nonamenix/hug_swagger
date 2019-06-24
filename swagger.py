def response(response_code, schema=None, description=None):
    """A decorator that add swagger response"""

    def decorator(handler):
        responses = getattr(handler, 'swagger_responses', {})

        responses[response_code] = {}
        if schema is not None:
            responses[response_code]['schema'] = schema
        if description is not None:
            responses[response_code]['description'] = description
        handler.swagger_responses = responses
        return handler

    return decorator


def response_codes(*codes):
    def decorator(handler):
        responses = getattr(handler, 'swagger_responses', {})
        for code in codes:
            responses[code] = {}
        handler.swagger_responses = responses
        return handler

    return decorator


def exclude():
    def decorator(handler):
        handler.swagger_excluded = True
        return handler

    return decorator
