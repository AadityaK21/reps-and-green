"""File storage: validated uploads (progress photos, avatars, exercise media).

Validation (size + magic-byte signature) happens here; the actual bytes go through
the pluggable storage adapter (`local` | `s3` | `cloudinary`), so switching to the
cloud is an env change with no API change. Progress photos are private — served
only to their owner or a coach.
"""
import time

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from ..config import settings
from ..db import files as files_col
from ..deps import get_current_user
from ..integrations import storage
from ..logging_conf import get_logger
from ..utils import oid

log = get_logger("files")
router = APIRouter(prefix="/files", tags=["files"])

# content-type -> magic-byte signatures (so a renamed file can't lie about its type)
SIGNATURES = {
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/webp": [b"RIFF"],
    "video/mp4": [b"\x00\x00\x00\x18ftyp", b"\x00\x00\x00\x1cftyp", b"\x00\x00\x00\x20ftyp"],
    "video/quicktime": [b"\x00\x00\x00\x14ftyp", b"\x00\x00\x00\x20ftyp"],
}
KIND_TYPES = {
    "progress": {"image/jpeg", "image/png", "image/webp"},
    "avatar": {"image/jpeg", "image/png", "image/webp"},
    "exercise": {"image/jpeg", "image/png", "image/webp"},
    "video": {"video/mp4", "video/quicktime"},
}


def _check_signature(content_type: str, head: bytes) -> bool:
    return any(head.startswith(sig) for sig in SIGNATURES.get(content_type, []))


@router.post("/upload")
async def upload(file: UploadFile, kind: str = "progress", user=Depends(get_current_user)):
    if kind not in KIND_TYPES:
        raise HTTPException(400, f"kind must be one of {', '.join(KIND_TYPES)}")
    # exercise/video are catalog assets — coach only
    if kind in ("exercise", "video") and user.get("role") not in ("coach", "admin"):
        raise HTTPException(403, "Only coaches can upload exercise media")
    if file.content_type not in KIND_TYPES[kind]:
        raise HTTPException(415, f"{kind} accepts: {', '.join(sorted(KIND_TYPES[kind]))}")

    limit_mb = settings.MAX_UPLOAD_MB if kind != "video" else max(settings.MAX_UPLOAD_MB, 64)
    max_bytes = limit_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(413, f"File exceeds {limit_mb}MB limit")
    if len(data) < 12 or not _check_signature(file.content_type, data[:12]):
        raise HTTPException(415, "File content does not match its declared type")

    stored = await storage.save(kind, file.content_type, data)
    doc = {
        "user_id": user["id"], "kind": kind, "content_type": file.content_type,
        "size": len(data), "ts": time.time(),
        "backend": stored["backend"], "storage_key": stored["key"], "public_url": stored["url"],
    }
    res = await files_col.insert_one(doc)
    log.info("upload user=%s kind=%s size=%dB backend=%s", user["id"], kind, len(data), stored["backend"])
    return {"id": str(res.inserted_id), "url": f"/files/{res.inserted_id}",
            "public_url": stored["url"], "size": len(data)}


@router.get("/{file_id}")
async def serve(file_id: str, user=Depends(get_current_user)):
    doc = await files_col.find_one({"_id": oid(file_id, "file id")})
    if not doc:
        raise HTTPException(404, "File not found")
    # owner or coach only — progress photos are private
    if doc["user_id"] != user["id"] and user.get("role") not in ("coach", "admin"):
        raise HTTPException(403, "Not allowed")
    if doc.get("public_url"):
        return RedirectResponse(doc["public_url"])
    path = storage.local_path(doc.get("storage_key", doc.get("name", "")))
    import os
    if not os.path.exists(path):
        raise HTTPException(410, "File no longer available")
    return FileResponse(path, media_type=doc["content_type"])


@router.get("")
async def my_files(kind: Optional[str] = None, user=Depends(get_current_user)):
    q: dict = {"user_id": user["id"]}
    if kind:
        q["kind"] = kind
    out = []
    async for d in files_col.find(q).sort("ts", -1).limit(100):
        out.append({"id": str(d["_id"]), "kind": d["kind"], "size": d["size"], "ts": d["ts"],
                    "url": f"/files/{d['_id']}", "public_url": d.get("public_url")})
    return out


@router.delete("/{file_id}")
async def delete_file(file_id: str, user=Depends(get_current_user)):
    doc = await files_col.find_one({"_id": oid(file_id, "file id"), "user_id": user["id"]})
    if not doc:
        raise HTTPException(404, "File not found")
    await files_col.delete_one({"_id": doc["_id"]})
    await storage.delete({"backend": doc.get("backend", "local"),
                          "key": doc.get("storage_key", doc.get("name", ""))})
    return {"ok": True}
