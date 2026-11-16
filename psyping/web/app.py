import asyncio
import json
import uuid
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request, Response, Cookie
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..database import (
    init_db, get_or_create_user, update_user, get_user_channels, update_user_channel,
    get_prompts_for_user, insert_prompt, acknowledge_delivery, get_recent_logs, get_db,
    get_global_config, set_global_config
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

def resolve_user_id(request: Request) -> str:
    # 1. Query parameter ?u=...
    u = request.query_params.get("u")
    if u and len(u) <= 64:
        return u.strip()
    # 2. Header X-User-Id
    h = request.headers.get("x-user-id")
    if h and len(h) <= 64:
        return h.strip()
    # 3. Cookie psyping_uid
    c = request.cookies.get("psyping_uid")
    if c and len(c) <= 64:
        return c.strip()
    # Default fallback
    return "default"

@app.on_event("startup")
async def on_startup():
    init_db()
    seed_prompts_if_empty()
    u = get_or_create_user("default")
    if not u.get("next_run_at"):
        schedule_next_ping("default")

@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request, response: Response):
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>PsyPing UI Loading...</h1>")
        
    uid = resolve_user_id(request)
    if uid == "default" and "psyping_uid" not in request.cookies and "u" not in request.query_params:
        # Generate clean new user id for fresh visitor
        new_uid = f"usr_{uuid.uuid4().hex[:8]}"
        get_or_create_user(new_uid)
        schedule_next_ping(new_uid)
        resp = RedirectResponse(url=f"/?u={new_uid}")
        resp.set_cookie(key="psyping_uid", value=new_uid, max_age=31536000)
        return resp
        
    with open(index_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    resp = HTMLResponse(content)
    if uid != "default" and request.cookies.get("psyping_uid") != uid:
        resp.set_cookie(key="psyping_uid", value=uid, max_age=31536000)
    return resp

@app.get("/api/status")
async def get_status(request: Request):
    user_id = resolve_user_id(request)
    user = get_or_create_user(user_id)
    global_cfg = get_global_config()
    channels = get_user_channels(user_id)
    prompts = get_prompts_for_user(user_id)
    recent = get_recent_logs(user_id=user_id, limit=10)
    
    active_channels = [c for c in channels if c.get("enabled")]
    active_prompts = [p for p in prompts if p.get("enabled")]
    
    with get_db() as conn:
        total_pings = conn.execute("SELECT COUNT(*) FROM delivery_logs WHERE user_id = ? AND status != 'failed';", (user_id,)).fetchone()[0]
        acked_pings = conn.execute("SELECT COUNT(*) FROM delivery_logs WHERE user_id = ? AND acknowledged_at IS NOT NULL;", (user_id,)).fetchone()[0]
        
    ack_rate = round((acked_pings / total_pings * 100), 1) if total_pings > 0 else 0.0

    # Combine user settings + global admin config for display
    combined = dict(user)
    combined.update(global_cfg)

    return {
        "user_id": user_id,
        "user_name": user.get("name", "Пользователь"),
        "settings": combined,
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
    name: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    ntfy_topic: Optional[str] = None
    webhook_url: Optional[str] = None
    llm_provider: Optional[str] = None
    tts_voice: Optional[str] = None

@app.post("/api/settings")
async def save_settings(payload: SettingsUpdate, request: Request):
    user_id = resolve_user_id(request)
    data = payload.dict(exclude_unset=True)
    
    user_fields = {"quiet_hours_start", "quiet_hours_end", "daily_target_count", "is_paused",
                   "name", "telegram_chat_id", "ntfy_topic", "webhook_url", "tts_voice"}
    u_updates = {k: v for k, v in data.items() if k in user_fields}
    if u_updates:
        update_user(user_id, u_updates)
        schedule_next_ping(user_id)
        
    # Global admin keys (LLM keys, Telegram Bot Token)
    global_fields = {"telegram_bot_token", "gemini_api_key", "openai_api_key", "llm_provider"}
    for k in global_fields:
        if k in data and data[k] is not None:
            set_global_config(k, str(data[k]))
            
    return {"success": True, "user_id": user_id}

@app.get("/api/channels")
async def list_channels(request: Request):
    user_id = resolve_user_id(request)
    return {"channels": get_user_channels(user_id)}

class ChannelUpdate(BaseModel):
    enabled: Optional[int] = None
    weight: Optional[float] = None

@app.post("/api/channels/{channel_id}")
async def save_channel(channel_id: str, payload: ChannelUpdate, request: Request):
    user_id = resolve_user_id(request)
    updates = {k: v for k, v in payload.dict().items() if v is not None}
    update_user_channel(user_id, channel_id, updates)
    return {"success": True}

@app.get("/api/prompts")
async def list_prompts(request: Request, category: Optional[str] = None):
    user_id = resolve_user_id(request)
    return {"prompts": get_prompts_for_user(user_id, category=category)}

class PromptCreate(BaseModel):
    category: str
    base_text: str
    enabled: int = 1

@app.post("/api/prompts")
async def create_prompt(payload: PromptCreate, request: Request):
    user_id = resolve_user_id(request)
    pid = f"usr_{uuid.uuid4().hex[:8]}"
    insert_prompt(pid, payload.category, payload.base_text, user_id=user_id, enabled=payload.enabled)
    return {"success": True, "id": pid}

@app.delete("/api/prompts/{prompt_id}")
async def delete_prompt(prompt_id: str, request: Request):
    user_id = resolve_user_id(request)
    with get_db() as conn:
        conn.execute("DELETE FROM prompts WHERE id = ? AND user_id = ?;", (prompt_id, user_id))
        conn.commit()
    return {"success": True}

class TriggerRequest(BaseModel):
    channel_id: Optional[str] = None
    prompt_id: Optional[str] = None
    custom_text: Optional[str] = None

@app.post("/api/trigger")
async def trigger_ping(payload: TriggerRequest, request: Request):
    user_id = resolve_user_id(request)
    res = await dispatch_reminder(
        user_id=user_id,
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
async def list_logs(request: Request, limit: int = 50):
    user_id = resolve_user_id(request)
    return {"logs": get_recent_logs(user_id=user_id, limit=limit)}

@app.api_route("/api/acknowledge/{log_id}", methods=["GET", "POST"])
async def acknowledge(log_id: str):
    ok = acknowledge_delivery(log_id)
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>PsyPing | Зафиксировано</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-950 text-slate-100 flex items-center justify-center min-h-screen p-4">
        <div class="max-w-md w-full bg-slate-900 rounded-2xl p-8 border border-emerald-500/30 text-center shadow-2xl">
            <div class="w-16 h-16 bg-emerald-500/20 text-emerald-400 rounded-full flex items-center justify-center mx-auto mb-4 text-3xl font-bold">✓</div>
            <h1 class="text-2xl font-bold mb-2">Отлично! Зафиксировано.</h1>
            <p class="text-slate-400 mb-6">Факт осознанности отмечен. Следующее напоминание придет в неожиданный момент.</p>
            <a href="/" class="inline-block px-5 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl font-medium transition">Вернуться в PsyPing</a>
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
                    yield ": keep-alive\n\n"
        finally:
            unsubscribe_browser(queue)
    return StreamingResponse(event_generator(), media_type="text/event-stream")

# Shared Telegram Bot Webhook (Multi-user registration & inline button callbacks)
@app.post("/api/telegram-webhook")
async def telegram_webhook(req: Request):
    try:
        data = await req.json()
        cfg = get_global_config()
        bot_token = cfg.get("telegram_bot_token", "")
        
        # 1. Handle /start command from any new or existing user
        if "message" in data:
            msg = data["message"]
            text = msg.get("text", "")
            chat_id = str(msg.get("chat", {}).get("id"))
            username = msg.get("from", {}).get("username", "")
            first_name = msg.get("from", {}).get("first_name", "Участник")
            
            if text.startswith("/start"):
                user_id = f"tg_{chat_id}"
                user = get_or_create_user(user_id)
                update_user(user_id, {
                    "name": first_name,
                    "telegram_chat_id": chat_id,
                    "telegram_username": username
                })
                # Enable telegram channels for this user
                update_user_channel(user_id, "telegram_text", {"enabled": 1})
                update_user_channel(user_id, "telegram_voice", {"enabled": 1})
                schedule_next_ping(user_id)
                
                welcome_text = (
                    f"👋 <b>Привет, {first_name}!</b>\n\n"
                    f"Я бот психологических напоминаний <b>PsyPing</b>.\n"
                    f"Моя цель — разрушать <i>баннерную слепоту</i> и выдергивать тебя из автопилота.\n\n"
                    f"✨ Я буду присылать короткие вопросы для саморефлексии, проверки тела, режимов и заземления в <b>случайные моменты времени</b>, чередуя текст и голосовые сообщения.\n\n"
                    f"👉 Твой персональный веб-дашборд с настройками тихих часов и темами:\n"
                    f"https://{req.headers.get('host', 'localhost:8000')}/?u={user_id}\n\n"
                    f"Первый импульс уже запланирован!"
                )
                if bot_token:
                    import httpx
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            f"https://api.telegram.org/bot{bot_token}/sendMessage",
                            json={"chat_id": chat_id, "text": welcome_text, "parse_mode": "HTML"}
                        )
                        
        # 2. Handle callback queries (Сделал ✓)
        elif "callback_query" in data:
            cq = data["callback_query"]
            cb_data = cq.get("data", "")
            cq_id = cq.get("id")
            
            if cb_data.startswith("ack:"):
                log_id = cb_data.split(":", 1)[1]
                acknowledge_delivery(log_id)
                if bot_token and cq_id:
                    import httpx
                    async with httpx.AsyncClient() as client:
                        await client.post(
                            f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery",
                            json={"callback_query_id": cq_id, "text": "Зафиксировано! Молодец ✓"}
                        )
    except Exception as e:
        print(f"[Telegram Webhook Error] {e}")
    return {"ok": True}
