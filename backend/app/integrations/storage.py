"""Pluggable object storage.

One `save`/`delete`/`url_for` interface, three backends selected by
`STORAGE_BACKEND`: local disk (default, zero-config), AWS S3, or Cloudinary.
The files router calls these functions and never needs to know which is active,
so switching to the cloud in production is a pure env change.
"""
import os
import uuid

from ..config import settings
from ..logging_conf import get_logger

log = get_logger("storage")

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads")
_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
        "video/mp4": ".mp4", "video/quicktime": ".mov"}


def backend() -> str:
    return (settings.STORAGE_BACKEND or "local").lower()


def _key(kind: str, content_type: str) -> str:
    return f"{kind}/{uuid.uuid4().hex}{_EXT.get(content_type, '')}"


async def save(kind: str, content_type: str, data: bytes) -> dict:
    """Persist bytes and return {backend, key, url}. `url` is None for local
    (served through the authenticated /files/{id} route instead)."""
    key = _key(kind, content_type)
    b = backend()

    if b == "s3":
        import boto3  # optional dependency
        s3 = boto3.client(
            "s3",
            region_name=settings.AWS_S3_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        s3.put_object(Bucket=settings.AWS_S3_BUCKET, Key=key, Body=data, ContentType=content_type)
        url = f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_S3_REGION}.amazonaws.com/{key}"
        return {"backend": "s3", "key": key, "url": url}

    if b == "cloudinary":
        import cloudinary  # optional dependency
        import cloudinary.uploader
        cloudinary.config(cloudinary_url=settings.CLOUDINARY_URL)
        res = cloudinary.uploader.upload(data, public_id=key, resource_type="auto")
        return {"backend": "cloudinary", "key": res["public_id"], "url": res["secure_url"]}

    # local
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    name = key.replace("/", "_")
    with open(os.path.join(UPLOAD_DIR, name), "wb") as f:
        f.write(data)
    return {"backend": "local", "key": name, "url": None}


async def delete(meta: dict) -> None:
    b = meta.get("backend", "local")
    key = meta.get("key", "")
    try:
        if b == "s3":
            import boto3
            boto3.client("s3", region_name=settings.AWS_S3_REGION,
                         aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                         aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
                         ).delete_object(Bucket=settings.AWS_S3_BUCKET, Key=key)
        elif b == "cloudinary":
            import cloudinary.uploader
            cloudinary.uploader.destroy(key, resource_type="image")
        else:
            os.remove(os.path.join(UPLOAD_DIR, os.path.basename(key)))
    except Exception as e:
        log.warning("storage delete failed (%s): %s", b, e)


def local_path(key: str) -> str:
    return os.path.join(UPLOAD_DIR, os.path.basename(key))
