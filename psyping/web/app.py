import asyncio
import json
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..database import (
    init_db, get_settings, update_settings, get_channels, update_channel,
    get_prompts, insert_prompt, acknowledge_delivery, get_recent_logs, get_db
)
from ..seed_data import seed_prompts_if_empty
from ..engine.dispatcher import dispatch_reminder
from ..engine.mutator import mutate_prompt
from ..engine.scheduler import schedule_next_ping
from ..channels.browser_push import subscribe_browser, unsubscribe_browser

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="PsyPing API", description="Omnichannel Psychological Reminder Service")

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.on_event("startup")
async def on_startup():
    init_db()
    seed_prompts_if_empty()
    settings = get_settings()
    if not settings.get("next_run_at"):
        schedule_next_ping()

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>PsyPing UI Loading...</h1>")
    with open(index_file, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/api/status")
async def get_status():
    settings = get_settings()
    channels = get_channels()
    prompts = get_prompts()
    recent = get_recent_logs(limit=10)
    
    active_channels = [c for c in channels if c.get("enabled")]
    active_prompts = [p for p in prompts if p.get("enabled")]
    
    # Calculate acknowledgment rate
    with get_db() as conn:
        total_pings = conn.execute("SELECT COUNT(*) FROM delivery_logs WHERE status != 'failed';").fetchone()[0]
        acked_pings = conn.execute("SELECT COUNT(*) FROM delivery_logs WHERE acknowledged_at IS NOT NULL;").fetchone()[0]
        
    ack_rate = round((acked_pings / total_pings * 100), 1) if total_pings > 0 else 0.0

    return {
        "settings": settings,
        "active_channels_count": len(active_channels),
        "total_channels_count": len(channels),
        "active_prompts_count": len(active_prompts),
        "total_prompts_count": len(prompts),
        "total_pings": total_pings,
        "acked_pings": acked_pings,
        "ack_rate_percent": ack_rate,
        "recent_logs": recent
    }

class SettingsUpdate(BaseModel):
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    daily_target_count: Optional[int] = None
    is_paused: Optional[int] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    ntfy_topic: Optional[str] = None
    webhook_url: Optional[str] = None
    llm_provider: Optional[str] = None
    tts_voice: Optional[str] = None

@app.post("/api/settings")
async def save_settings(payload: SettingsUpdate):
    updates = {k: v for k, v in payload.dict().items() if v is not None}
    update_settings(updates)
    # Recalculate schedule if daily count or quiet hours changed
    schedule_next_ping()
    return {"success": True, "settings": get_settings()}

@app.get("/api/channels")
async def list_channels():
    return {"channels": get_channels()}

class ChannelUpdate(BaseModel):
    enabled: Optional[int] = None
    weight: Optional[float] = None

@app.post("/api/channels/{channel_id}")
async def save_channel(channel_id: str, payload: ChannelUpdate):
    updates = {k: v for k, v in payload.dict().items() if v is not None}
    update_channel(channel_id, updates)
    return {"success": True}

@app.get("/api/prompts")
async def list_prompts(category: Optional[str] = None):
    return {"prompts": get_prompts(category=category)}

class PromptCreate(BaseModel):
    id: Optional[str] = None
    category: str
    base_text: str
    enabled: int = 1

@app.post("/api/prompts")
async def create_prompt(payload: PromptCreate):
    import uuid
    pid = payload.id or f"user_{str(uuid.uuid4())[:8]}"
    insert_prompt(pid, payload.category, payload.base_text, payload.enabled)
    return {"success": True, "id": pid}

@app.delete("/api/prompts/{prompt_id}")
async def delete_prompt(prompt_id: str):
    with get_db() as conn:
        conn.execute("DELETE FROM prompts WHERE id = ?;", (prompt_id,))
        conn.commit()
    return {"success": True}

class TriggerRequest(BaseModel):
    channel_id: Optional[str] = None
    prompt_id: Optional[str] = None
    custom_text: Optional[str] = None

@app.post("/api/trigger")
async def trigger_ping(payload: TriggerRequest):
    res = await dispatch_reminder(
        force_channel_id=payload.channel_id,
        force_prompt_id=payload.prompt_id,
        custom_text=payload.custom_text
    )
    return res

class PreviewRequest(BaseModel):
    text: str
    category: str

@app.post("/api/preview-mutation")
async def preview_mutation(payload: PreviewRequest):
    mutated = await mutate_prompt(payload.text, payload.category)
    return {"original": payload.text, "mutated": mutated}

@app.get("/api/logs")
async def list_logs(limit: int = 50):
    return {"logs": get_recent_logs(limit=limit)}

@app.api_route("/api/acknowledge/{log_id}", methods=["GET", "POST"])
async def acknowledge(log_id: str):
    ok = acknowledge_delivery(log_id)
    # Simple friendly confirmation page if opened in browser
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>PsyPing | Зафиксировано</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-900 text-slate-100 flex items-center justify-center min-h-screen p-4">
        <div class="max-w-md w-full bg-slate-800 rounded-2xl p-8 border border-emerald-500/30 text-center shadow-2xl">
            <div class="w-16 h-16 bg-emerald-500/20 text-emerald-400 rounded-full flex items-center justify-center mx-auto mb-4 text-3xl font-bold">✓</div>
            <h1 class="text-2xl font-bold mb-2">Отлично! Зафиксировано.</h1>
            <p class="text-slate-400 mb-6">Факт осознанности отмечен. Следующее напоминание придет в неожиданный момент.</p>
            <a href="/" class="inline-block px-5 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl font-medium transition">В дашборд PsyPing</a>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/api/events")
async def sse_events(request: Request):
    queue = subscribe_browser()
    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat ping
                    yield ": keep-alive\n\n"
        finally:
            unsubscribe_browser(queue)
    return StreamingResponse(event_generator(), media_type="text/event-stream")

# Telegram Webhook receiver (for inline button callback queries)
@app.post("/api/telegram-webhook")
async def telegram_webhook(req: Request):
    try:
        data = await req.json()
        if "callback_query" in data:
            cq = data["callback_query"]
            cb_data = cq.get("data", "")
            cq_id = cq.get("id")
            
            if cb_data.startswith("ack:"):
                log_id = cb_data.split(":", 1)[1]
                acknowledge_delivery(log_id)
                # Answer callback
                settings = get_settings()
                bot_token = settings.get("telegram_bot_token")
                if bot_token and cq_id:
                    import httpx
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery",
                            json={"callback_query_id": cq_id, "text": "Зафиксировано! Молодец ✓"}
                        )
    except Exception:
        pass
    return {"ok": True}
