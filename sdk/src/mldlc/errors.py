class MLDLCError(Exception):
    """Base SDK exception."""


class APIError(MLDLCError):
    """Raised for unexpected API responses."""


class AuthenticationError(APIError):
    """Raised when JWT minting with an API key fails."""


class UnauthorizedError(APIError):
    """Raised when an authenticated request still fails after token refresh."""


class NotFoundError(APIError):
    """Raised when the requested resource does not exist."""


class ConflictError(APIError):
    """Raised when a state transition or resource conflicts with server state."""


class ValidationError(APIError):
    """Raised when the request payload violates server-side validation."""


class SerializationError(MLDLCError):
    """Raised when local data cannot be serialized or deserialized."""


class DatasetReadyTimeoutError(MLDLCError):
    """Raised when dataset upload finishes but readiness confirmation does not arrive in time."""

