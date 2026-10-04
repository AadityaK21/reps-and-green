"""Resend transactional email. Mock-logs when key absent."""
import httpx
from ..config import settings

def configured() -> bool:
    return bool(settings.RESEND_API_KEY)

async def send_email(to: str, subject: str, html: str) -> dict:
    if not configured():
        print(f"[resend mock] to {to} :: {subject}")
        return {"mock": True}
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post("https://api.resend.com/emails",
                         headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                         json={"from": settings.EMAIL_FROM, "to": [to], "subject": subject, "html": html})
        r.raise_for_status()
        return r.json()
