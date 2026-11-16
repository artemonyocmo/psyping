import sqlite3
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

DB_FILE = Path(__file__).resolve().parent.parent / "psyping.db"

def get_db():
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Global System / Admin Config
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS global_config (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """)
        
        # 2. Multi-user Profiles
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT DEFAULT 'Гость',
            created_at TEXT NOT NULL,
            quiet_hours_start TEXT DEFAULT '22:00',
            quiet_hours_end TEXT DEFAULT '09:00',
            daily_target_count INTEGER DEFAULT 4,
            is_paused INTEGER DEFAULT 0,
            telegram_chat_id TEXT DEFAULT '',
            telegram_username TEXT DEFAULT '',
            ntfy_topic TEXT DEFAULT '',
            webhook_url TEXT DEFAULT '',
            tts_voice TEXT DEFAULT 'ru-RU-SvetlanaNeural',
            next_run_at TEXT,
            last_run_at TEXT
        );
        """)

        # Ensure default primary user exists
        cursor.execute("SELECT id FROM users WHERE id = 'default';")
        if not cursor.fetchone():
            now_iso = datetime.now(timezone.utc).isoformat()
            cursor.execute("""
            INSERT INTO users (id, name, created_at, quiet_hours_start, quiet_hours_end, daily_target_count, is_paused, ntfy_topic)
            VALUES ('default', 'Основной профиль', ?, '22:00', '09:00', 4, 0, 'psyping_alerts');
            """, (now_iso,))

        # 3. Channels per user
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_channels (
            user_id TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            weight REAL DEFAULT 1.0,
            effective_weight REAL DEFAULT 1.0,
            last_used_at TEXT,
            consecutive_unacknowledged INTEGER DEFAULT 0,
            total_sent INTEGER DEFAULT 0,
            total_acknowledged INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, channel_id)
        );
        """)

        # 4. Prompts (both system/shared and user-custom)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS prompts (
            id TEXT PRIMARY KEY,
            user_id TEXT DEFAULT 'system',
            category TEXT NOT NULL,
            base_text TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            last_used_at TEXT,
            use_count INTEGER DEFAULT 0
        );
        """)

        # 5. Delivery Logs
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS delivery_logs (
            id TEXT PRIMARY KEY,
            user_id TEXT DEFAULT 'default',
            sent_at TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            prompt_id TEXT,
            base_prompt TEXT,
            generated_text TEXT NOT NULL,
            media_type TEXT DEFAULT 'text',
            acknowledged_at TEXT,
            status TEXT DEFAULT 'sent',
            error_message TEXT
        );
        """)

        # Automatic Schema Migrations
        try:
            cursor.execute("ALTER TABLE prompts ADD COLUMN user_id TEXT DEFAULT 'system';")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE delivery_logs ADD COLUMN user_id TEXT DEFAULT 'default';")
        except Exception:
            pass

        conn.commit()

# Global config helpers
def get_global_config() -> Dict[str, str]:
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM global_config;").fetchall()
        return {r["key"]: r["value"] for r in rows}

def set_global_config(key: str, value: str):
    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO global_config (key, value) VALUES (?, ?);", (key, value))
        conn.commit()

# User helpers
def get_or_create_user(user_id: str = "default") -> Dict[str, Any]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?;", (user_id,)).fetchone()
        if row:
            return dict(row)
        
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute("""
        INSERT INTO users (id, name, created_at, quiet_hours_start, quiet_hours_end, daily_target_count, is_paused, ntfy_topic)
        VALUES (?, 'Новый участник', ?, '22:00', '09:00', 4, 0, ?);
        """, (user_id, now_iso, f"psyping_{user_id[:8]}"))
        conn.commit()
        
        row = conn.execute("SELECT * FROM users WHERE id = ?;", (user_id,)).fetchone()
        init_user_channels(user_id)
        return dict(row)

def update_user(user_id: str, updates: Dict[str, Any]):
    fields = []
    values = []
    for k, v in updates.items():
        if k != "id" and k != "created_at":
            fields.append(f"{k} = ?")
            values.append(v)
    if not fields:
        return
    values.append(user_id)
    with get_db() as conn:
        conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?;", values)
        conn.commit()

def get_all_active_users() -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM users WHERE is_paused = 0;").fetchall()
        return [dict(r) for r in rows]

# User channels
DEFAULT_CHANNEL_DEFS = [
    ("desktop_toast", "Windows Toast Уведомление", "Всплывающее окно в углу экрана (только при локальном запуске на Windows)", 0, 1.0),
    ("telegram_text", "Telegram (Текст + Кнопки)", "Сообщение в боте с кнопкой [Сделал ✓]", 1, 1.2),
    ("telegram_voice", "Telegram (Голос / Voice)", "Реалистичное голосовое сообщение в Telegram", 1, 0.9),
    ("ntfy", "ntfy.sh (Мгновенный Push)", "Push на смартфон (Android/iOS) и ПК через ntfy.sh", 1, 1.1),
    ("browser_push", "Web Dashboard Alert", "Звук тибетской чаши и баннер в открытом браузере", 1, 0.8),
    ("webhook", "Custom Webhook", "HTTP POST на умный дом (Home Assistant / Алиса / MacroDroid)", 0, 0.5),
]

def init_user_channels(user_id: str):
    with get_db() as conn:
        for cid, name, desc, en, w in DEFAULT_CHANNEL_DEFS:
            conn.execute("""
            INSERT OR IGNORE INTO user_channels (user_id, channel_id, enabled, weight, effective_weight)
            VALUES (?, ?, ?, ?, ?);
            """, (user_id, cid, en, w, w))
        conn.commit()

def get_user_channels(user_id: str) -> List[Dict[str, Any]]:
    init_user_channels(user_id)
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM user_channels WHERE user_id = ? ORDER BY channel_id;", (user_id,)).fetchall()
        result = []
        c_map = {cid: (name, desc) for cid, name, desc, _, _ in DEFAULT_CHANNEL_DEFS}
        for r in rows:
            d = dict(r)
            d["id"] = d["channel_id"]
            d["name"], d["description"] = c_map.get(d["channel_id"], (d["channel_id"], ""))
            result.append(d)
        return result

def update_user_channel(user_id: str, channel_id: str, updates: Dict[str, Any]):
    fields = []
    values = []
    for k, v in updates.items():
        if k not in ("user_id", "channel_id"):
            fields.append(f"{k} = ?")
            values.append(v)
    if not fields:
        return
    values.extend([user_id, channel_id])
    with get_db() as conn:
        conn.execute(f"UPDATE user_channels SET {', '.join(fields)} WHERE user_id = ? AND channel_id = ?;", values)
        conn.commit()

# Prompts helpers
def get_prompts_for_user(user_id: str, category: Optional[str] = None, enabled_only: bool = False) -> List[Dict[str, Any]]:
    with get_db() as conn:
        query = "SELECT * FROM prompts WHERE (user_id = 'system' OR user_id = ?)"
        params = [user_id]
        if category:
            query += " AND category = ?"
            params.append(category)
        if enabled_only:
            query += " AND enabled = 1"
        query += " ORDER BY last_used_at ASC, use_count ASC;"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

def insert_prompt(prompt_id: str, category: str, base_text: str, user_id: str = "system", enabled: int = 1):
    with get_db() as conn:
        conn.execute("""
        INSERT INTO prompts (id, user_id, category, base_text, enabled, use_count)
        VALUES (?, ?, ?, ?, ?, 0);
        """, (prompt_id, user_id, category, base_text, enabled))
        conn.commit()

# Delivery logging
def log_delivery(log_id: str, user_id: str, channel_id: str, prompt_id: Optional[str],
                 base_prompt: Optional[str], generated_text: str, media_type: str = 'text',
                 status: str = 'sent', error_message: Optional[str] = None) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute("""
        INSERT INTO delivery_logs (id, user_id, sent_at, channel_id, prompt_id, base_prompt, generated_text, media_type, status, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (log_id, user_id, now_iso, channel_id, prompt_id, base_prompt, generated_text, media_type, status, error_message))
        
        if status == 'sent':
            conn.execute("""
            UPDATE user_channels 
            SET total_sent = total_sent + 1,
                last_used_at = ?
            WHERE user_id = ? AND channel_id = ?;
            """, (now_iso, user_id, channel_id))
            
        if prompt_id:
            conn.execute("""
            UPDATE prompts
            SET use_count = use_count + 1,
                last_used_at = ?
            WHERE id = ?;
            """, (now_iso, prompt_id))
            
        conn.commit()
        return {
            "id": log_id,
            "user_id": user_id,
            "sent_at": now_iso,
            "channel_id": channel_id,
            "prompt_id": prompt_id,
            "generated_text": generated_text,
            "status": status
        }

def acknowledge_delivery(log_id: str) -> bool:
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        log = conn.execute("SELECT * FROM delivery_logs WHERE id = ?;", (log_id,)).fetchone()
        if not log:
            return False
        conn.execute("""
        UPDATE delivery_logs 
        SET acknowledged_at = ?, status = 'acknowledged'
        WHERE id = ?;
        """, (now_iso, log_id))
        
        user_id = log["user_id"]
        channel_id = log["channel_id"]
        conn.execute("""
        UPDATE user_channels
        SET total_acknowledged = total_acknowledged + 1,
            consecutive_unacknowledged = 0
        WHERE user_id = ? AND channel_id = ?;
        """, (user_id, channel_id))
        conn.commit()
        return True

def get_recent_logs(user_id: str = "default", limit: int = 50) -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("""
        SELECT l.* 
        FROM delivery_logs l
        WHERE l.user_id = ?
        ORDER BY l.sent_at DESC
        LIMIT ?;
        """, (user_id, limit)).fetchall()
        return [dict(r) for r in rows]

# Backward compatibility aliases
def get_settings():
    u = get_or_create_user("default")
    cfg = get_global_config()
    res = dict(u)
    res.update(cfg)
    return res

def update_settings(updates: Dict[str, Any]):
    user_keys = {"quiet_hours_start", "quiet_hours_end", "daily_target_count", "is_paused",
                 "telegram_chat_id", "ntfy_topic", "webhook_url", "tts_voice", "next_run_at", "last_run_at"}
    u_up = {k: v for k, v in updates.items() if k in user_keys}
    if u_up:
        update_user("default", u_up)
    g_up = {k: v for k, v in updates.items() if k not in user_keys}
    for k, v in g_up.items():
        set_global_config(k, str(v))

def get_channels():
    return get_user_channels("default")

def update_channel(channel_id: str, updates: Dict[str, Any]):
    update_user_channel("default", channel_id, updates)

def get_prompts(category: Optional[str] = None, enabled_only: bool = False):
    return get_prompts_for_user("default", category, enabled_only)
