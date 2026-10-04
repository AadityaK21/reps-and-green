"""Small shared helpers used across routers."""
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException


def oid(value: str, what: str = "id") -> ObjectId:
    """Parse an ObjectId or fail with a clean 400 instead of a 500."""
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(400, f"Invalid {what}")


def clamp_page(limit: int, skip: int, max_limit: int = 100) -> tuple[int, int]:
    """Clamp pagination params to sane bounds."""
    return max(1, min(limit, max_limit)), max(0, skip)
