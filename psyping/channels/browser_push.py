import asyncio
from typing import Dict, Any, Tuple, Optional, List
from .base import BaseChannel

# In-memory broadcaster for browser clients
_subscribers: List[asyncio.Queue] = []

def subscribe_browser() -> asyncio.Queue:
    q = asyncio.Queue()
    _subscribers.append(q)
    return q

def unsubscribe_browser(q: asyncio.Queue):
    if q in _subscribers:
        _subscribers.remove(q)

async def broadcast_to_browsers(event_data: Dict[str, Any]):
    dead = []
    for q in _subscribers:
        try:
            await q.put(event_data)
        except Exception:
            dead.append(q)
    for q in dead:
        unsubscribe_browser(q)

class BrowserPushChannel(BaseChannel):
    @property
    def channel_id(self) -> str:
        return "browser_push"

    async def deliver(self, log_id: str, text: str, category: str, settings: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        event = {
            "type": "ping",
            "log_id": log_id,
            "category": category,
            "text": text,
            "title": f"PsyPing • {category.capitalize()}"
        }
        await broadcast_to_browsers(event)
        return True, None
