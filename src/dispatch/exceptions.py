from pydantic.errors import PydanticValueError


class DispatchException(Exception):
    pass


class InvalidConfiguration(DispatchException):
    pass


class InvalidFilterPolicy(DispatchException):
    pass


class DispatchPluginException(DispatchException):
    pass


class NotFoundError(PydanticValueError):
    code = "not_found"
    msg_template = "{msg}"


class FieldNotFoundError(PydanticValueError):
    code = "not_found.field"
    msg_template = "{msg}"


class InvalidFilterError(PydanticValueError):
    code = "invalid.filter"
    msg_template = "{msg}"
