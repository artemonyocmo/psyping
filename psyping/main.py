import asyncio
import os
import sys
from datetime import datetime, timezone
import uvicorn
from .web.app import app
from .database import init_db, get_settings, update_settings
from .seed_data import seed_prompts_if_empty
from .engine.dispatcher import dispatch_reminder
from .engine.scheduler import schedule_next_ping

async def background_scheduler_loop():
    print("[PsyPing Scheduler] Background loop started...")
    while True:
        try:
            await asyncio.sleep(15) # Check every 15 seconds
            settings = get_settings()
            
            if settings.get("is_paused"):
                continue
                
            next_run_iso = settings.get("next_run_at")
            if not next_run_iso:
                schedule_next_ping()
                continue
                
            next_run_dt = datetime.fromisoformat(next_run_iso)
            now_dt = datetime.now() if next_run_dt.tzinfo is None else datetime.now(timezone.utc)
            
            if now_dt >= next_run_dt:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Triggering scheduled random psychological ping...")
                res = await dispatch_reminder()
                print(f"[PsyPing Scheduler] Dispatched: channel={res.get('channel_id')}, success={res.get('success')}, next={res.get('next_run_at')}")
                
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[PsyPing Scheduler Error] {e}")

@app.on_event("startup")
async def start_background_tasks():
    init_db()
    seed_prompts_if_empty()
    # Schedule initial ping if not scheduled
    settings = get_settings()
    if not settings.get("next_run_at"):
        schedule_next_ping()
    # Spawn background scheduler worker
    asyncio.create_task(background_scheduler_loop())

def main():
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    print("=" * 60)
    print("  Ψ PsyPing — Omnichannel Random Reminder Service")
    print(f"  Dashboard available at: http://localhost:{port}")
    print("=" * 60)
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    main()
