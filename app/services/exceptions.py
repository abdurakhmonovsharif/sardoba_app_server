class ServiceError(Exception):
    """Base exception for service-level errors."""


class TransientServiceError(ServiceError):
    """Retryable external/transient service failure."""

    def __init__(self, message: str, *, retry_after_seconds: float | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


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
