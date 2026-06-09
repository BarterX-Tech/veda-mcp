from __future__ import annotations


class VedaError(Exception):
    """Base error for caller-visible veda failures."""

    code = "veda_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


class Blocked(VedaError):
    code = "blocked"


class NotFound(VedaError):
    code = "not_found"


class ParseError(VedaError):
    code = "parse_error"
