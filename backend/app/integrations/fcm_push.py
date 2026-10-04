"""Firebase Cloud Messaging push. Mock-logs when no server key is configured.

Uses the legacy HTTP API (simple server-key auth) for portability; swap the
transport for the HTTP v1 API + service-account JWT in production if required.
The public `send_push` signature stays the same either way.
"""
import httpx

from ..config import settings
from ..logging_conf import get_logger

log = get_logger("fcm")


def configured() -> bool:
    return bool(settings.FCM_SERVER_KEY)


async def send_push(tokens: list[str], title: str, body: str, data: dict | None = None) -> dict:
    """Deliver a notification to one or more device tokens."""
    tokens = [t for t in tokens if t]
    if not tokens:
        return {"sent": 0, "skipped": "no tokens"}
    if not configured():
        log.info("[fcm mock] %d device(s) :: %s", len(tokens), title)
        return {"mock": True, "sent": len(tokens)}
    payload = {
        "registration_ids": tokens,
        "notification": {"title": title, "body": body},
        "data": data or {},
    }
    headers = {"Authorization": f"key={settings.FCM_SERVER_KEY}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post("https://fcm.googleapis.com/fcm/send", json=payload, headers=headers)
        r.raise_for_status()
        out = r.json()
    return {"sent": out.get("success", len(tokens)), "failure": out.get("failure", 0)}
