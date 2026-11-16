import base64
import urllib.parse
import httpx
from typing import Dict, Any, Tuple, Optional
from .base import BaseChannel

class NtfyChannel(BaseChannel):
    @property
    def channel_id(self) -> str:
        return "ntfy"

    async def deliver(self, log_id: str, text: str, category: str, settings: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        topic = settings.get("ntfy_topic", "psyping_alerts").strip()
        if not topic:
            return False, "ntfy.sh topic не указан в настройках"

        url = f"https://ntfy.sh/{topic}"
        
        category_tags = {
            "body": "muscle,bell",
            "modes_schemas": "brain,thought_balloon",
            "emotion": "ocean,heart",
            "grounding": "anchor,earth_africa",
            "values": "compass,star2",
            "micro_break": "coffee,sparkles"
        }
        tags = category_tags.get(category, "bell,brain")
        raw_title = f"PsyPing: {category.capitalize()}"
        # RFC 2047 MIME Header B-Encoding for non-ASCII safety in HTTP headers
        b64_title = base64.b64encode(raw_title.encode("utf-8")).decode("ascii")
        encoded_title = f"=?UTF-8?B?{b64_title}?="
        
        headers = {
            "Title": encoded_title,
            "Priority": "default",
            "Tags": tags,
            "Actions": f"view, Done, http://localhost:8000/api/acknowledge/{log_id}"
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, content=text.encode("utf-8"), headers=headers)
                if resp.status_code in (200, 201, 204):
                    return True, None
                else:
                    return False, f"ntfy.sh error {resp.status_code}: {resp.text}"
        except Exception as e:
            return False, f"ntfy.sh HTTP error: {str(e)}"
