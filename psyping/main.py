import asyncio
import os
import sys
from datetime import datetime, timezone
import uvicorn
from .web.app import app
from .database import init_db, get_all_active_users, update_user
from .seed_data import seed_prompts_if_empty
from .engine.dispatcher import dispatch_reminder
from .engine.scheduler import schedule_next_ping

async def background_scheduler_loop():
    print("[PsyPing Multi-Tenant Scheduler] Background worker loop started...")
    while True:
        try:
            await asyncio.sleep(15) # Check every 15 seconds
            users = get_all_active_users()
            now_dt = datetime.now(timezone.utc)
            
            for u in users:
                user_id = u["id"]
                next_run_iso = u.get("next_run_at")
                if not next_run_iso:
                    schedule_next_ping(user_id)
                    continue
                    
                next_run_dt = datetime.fromisoformat(next_run_iso)
                if next_run_dt.tzinfo is None:
                    next_run_dt = next_run_dt.replace(tzinfo=timezone.utc)
                    
                if now_dt >= next_run_dt:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Pinging user '{user_id}'...")
                    res = await dispatch_reminder(user_id=user_id)
                    print(f"[PsyPing Scheduler] Result for {user_id}: channel={res.get('channel_id')}, success={res.get('success')}")
                    
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[PsyPing Scheduler Error] {e}")

@app.on_event("startup")
async def start_background_tasks():
    init_db()
    seed_prompts_if_empty()
    schedule_next_ping("default")
    asyncio.create_task(background_scheduler_loop())

def main():
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    print("=" * 60)
    print("  Ψ PsyPing — Omnichannel Psychological Reminder Service")
    print(f"  Multi-user service running on: http://{host}:{port}")
    print("=" * 60)
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    main()
