"""Twilio WhatsApp. Mock-logs when keys absent so dev flow never breaks."""
import httpx
from ..config import settings

def configured() -> bool:
    return bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN)

async def send_whatsapp(to_phone: str, body: str) -> dict:
    if not configured():
        print(f"[twilio mock] WA to {to_phone}: {body[:80]}")
        return {"mock": True}
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json"
    async with httpx.AsyncClient(auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN), timeout=20) as c:
        r = await c.post(url, data={"From": settings.TWILIO_WA_FROM, "To": f"whatsapp:{to_phone}", "Body": body})
        r.raise_for_status()
        return r.json()
