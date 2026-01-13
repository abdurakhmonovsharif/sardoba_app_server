class ServiceError(Exception):
    """Base exception for service-level errors."""


class RateLimitExceeded(ServiceError):
    pass


class SMSDeliveryError(ServiceError):
    pass


class OTPExpired(ServiceError):
    pass


class OTPInvalid(ServiceError):
    pass


class OTPDeliveryFailed(ServiceError):
    pass


class AuthenticationError(ServiceError):
    pass


class AuthorizationError(ServiceError):
    pass


class ExternalServiceBadRequest(ServiceError):
    """Raised when an external service rejects a payload with Bad Request (400)."""


class NotFoundError(ServiceError):
    pass


class ConflictError(ServiceError):
    pass
