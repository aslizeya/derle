from __future__ import annotations

from fastapi import HTTPException, status


def not_found(code: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": code})


def conflict(code: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, detail={"code": code})


def from_code(code: str) -> HTTPException:
    """Map a service error code to an HTTP error: ``*_not_found`` → 404, everything else 409."""
    return not_found(code) if code.endswith("_not_found") else conflict(code)
