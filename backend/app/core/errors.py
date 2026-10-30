"""Consistent error type; rendered as {"error": {"code","message","request_id"}}."""
class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, headers: dict[str, str] | None = None, extra: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.headers, self.extra = status, code, message, headers or {}, extra or {}
