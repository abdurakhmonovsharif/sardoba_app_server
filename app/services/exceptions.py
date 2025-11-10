class ServiceError(Exception):
    """Base exception for service-level errors."""


class RateLimitExceeded(ServiceError):
    pass


class OTPExpired(ServiceError):
    pass


class OTPInvalid(ServiceError):
    pass


class AuthenticationError(ServiceError):
    pass


class AuthorizationError(ServiceError):
    pass


class NotFoundError(ServiceError):
    pass


class ConflictError(ServiceError):
    pass
