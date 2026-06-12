"""AtlasError hierarchy rendered as the D-014 error envelope by handlers in app.main."""

from typing import Any


class AtlasError(Exception):
    """Base for every error the API surfaces deliberately. Codes are machine-readable
    and dot-namespaced (generic: common.*; domain rules: e.g. finance.period_closed)."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class NotFoundError(AtlasError):
    def __init__(
        self,
        message: str = "Resource not found",
        code: str = "common.not_found",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=404, details=details)


class ValidationFailedError(AtlasError):
    def __init__(
        self,
        message: str = "Validation failed",
        code: str = "common.validation_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=422, details=details)


class ConflictError(AtlasError):
    def __init__(
        self,
        message: str = "Conflict with existing state",
        code: str = "common.conflict",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=409, details=details)


class AuthError(AtlasError):
    def __init__(
        self,
        message: str = "Invalid credentials",
        code: str = "auth.invalid_credentials",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=401, details=details)


class PermissionDeniedError(AtlasError):
    def __init__(
        self,
        message: str = "Permission denied",
        code: str = "common.permission_denied",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=403, details=details)


class TenancyError(AtlasError):
    def __init__(
        self,
        message: str = "Tenant context missing or mismatched",
        code: str = "tenancy.context_missing",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code=code, message=message, status_code=403, details=details)
