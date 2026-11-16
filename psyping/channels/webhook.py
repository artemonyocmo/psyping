import httpx
from typing import Dict, Any, Tuple, Optional
from .base import BaseChannel

class WebhookChannel(BaseChannel):
    @property
    def channel_id(self) -> str:
        return "webhook"

    async def deliver(self, log_id: str, text: str, category: str, settings: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        webhook_url = settings.get("webhook_url", "").strip()
        if not webhook_url:
            return False, "Webhook URL не указан в настройках"

        payload = {
            "source": "psyping",
            "log_id": log_id,
            "category": category,
            "message": text
        }

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(webhook_url, json=payload)
                if 200 <= resp.status_code < 300:
                    return True, None
                else:
                    return False, f"Webhook response status {resp.status_code}"
        except Exception as e:
            return False, f"Webhook HTTP error: {str(e)}"
