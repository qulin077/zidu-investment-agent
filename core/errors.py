"""产品错误分类。不要把所有失败都变成裸 Exception。"""
from __future__ import annotations


class ProductError(Exception):
    code = "EXCEPTION"

    def __init__(self, message: str = "", code: str = "") -> None:
        super().__init__(message)
        if code:
            self.code = code


class ValidationError(ProductError):
    code = "VALIDATION_ERROR"


class DataStale(ProductError):
    code = "DATA_STALE"


class DataMissing(ProductError):
    code = "DATA_MISSING"


class ProviderFailed(ProductError):
    code = "PROVIDER_FAILED"


class GroundingFailed(ProductError):
    code = "GROUNDING_FAILED"


class WriteBlocked(ProductError):
    code = "WRITE_BLOCKED"


class IllegalTransition(ProductError):
    code = "ILLEGAL_TRANSITION"


class AuditInconsistency(ProductError):
    code = "AUDIT_INCONSISTENCY"


CODES = (
    "VALIDATION_ERROR",
    "DATA_STALE",
    "DATA_MISSING",
    "PROVIDER_FAILED",
    "GROUNDING_FAILED",
    "WRITE_BLOCKED",
    "ILLEGAL_TRANSITION",
    "AUDIT_INCONSISTENCY",
)
