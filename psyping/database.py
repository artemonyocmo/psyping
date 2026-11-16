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
        
        # 1. Settings (Singleton row)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            quiet_hours_start TEXT DEFAULT '22:00',
            quiet_hours_end TEXT DEFAULT '09:00',
            daily_target_count INTEGER DEFAULT 4,
            is_paused INTEGER DEFAULT 0,
            telegram_bot_token TEXT DEFAULT '',
            telegram_chat_id TEXT DEFAULT '',
            gemini_api_key TEXT DEFAULT '',
            openai_api_key TEXT DEFAULT '',
            ntfy_topic TEXT DEFAULT 'psyping_alerts',
            webhook_url TEXT DEFAULT '',
            llm_provider TEXT DEFAULT 'fallback',
            tts_voice TEXT DEFAULT 'ru-RU-DmitryNeural',
            next_run_at TEXT,
            last_run_at TEXT
        );
        """)

        # Ensure default settings row exists
        cursor.execute("SELECT id FROM settings WHERE id = 1;")
        if not cursor.fetchone():
            cursor.execute("""
            INSERT INTO settings (id, quiet_hours_start, quiet_hours_end, daily_target_count, is_paused, ntfy_topic, llm_provider)
            VALUES (1, '22:00', '09:00', 4, 0, 'psyping_alerts', 'fallback');
            """)

        # 2. Channels
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            enabled INTEGER DEFAULT 1,
            weight REAL DEFAULT 1.0,
            effective_weight REAL DEFAULT 1.0,
            last_used_at TEXT,
            consecutive_unacknowledged INTEGER DEFAULT 0,
            total_sent INTEGER DEFAULT 0,
            total_acknowledged INTEGER DEFAULT 0
        );
        """)

        # Seed default channels
        default_channels = [
            ("desktop_toast", "Windows Toast Уведомление", "Всплывающая карточка в углу экрана Windows с кнопками действия", 1, 1.2),
            ("telegram_text", "Telegram (Текст + Кнопки)", "Сообщение в Telegram-бот с inline-кнопками подтверждения", 1, 1.0),
            ("telegram_voice", "Telegram (Голосовое / Voice)", "Сгенерированная реалистичная аудиозапись в Telegram через TTS", 1, 0.8),
            ("ntfy", "ntfy.sh (Мгновенный Push)", "Push на телефон и ПК через ntfy.sh (Android, iOS, Web)", 1, 1.0),
            ("browser_push", "Web Dashboard Alert", "Звуковой сигнал и баннер прямо в открытом дашборде", 1, 0.7),
            ("webhook", "Custom Webhook", "HTTP POST на умный дом (Home Assistant / Алиса / MacroDroid)", 0, 0.5),
        ]
        for cid, name, desc, en, w in default_channels:
            cursor.execute("""
            INSERT OR IGNORE INTO channels (id, name, description, enabled, weight, effective_weight)
            VALUES (?, ?, ?, ?, ?, ?);
            """, (cid, name, desc, en, w, w))

        # 3. Prompts
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS prompts (
            id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            base_text TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            last_used_at TEXT,
            use_count INTEGER DEFAULT 0
        );
        """)

        # 4. Delivery logs
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS delivery_logs (
            id TEXT PRIMARY KEY,
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

        conn.commit()

# Helper queries
def get_settings() -> Dict[str, Any]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM settings WHERE id = 1;").fetchone()
        return dict(row) if row else {}

def update_settings(updates: Dict[str, Any]):
    fields = []
    values = []
    for k, v in updates.items():
        if k != "id":
            fields.append(f"{k} = ?")
            values.append(v)
    if not fields:
        return
    values.append(1)
    with get_db() as conn:
        conn.execute(f"UPDATE settings SET {', '.join(fields)} WHERE id = ?;", values)
        conn.commit()

def get_channels() -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM channels ORDER BY id;").fetchall()
        return [dict(r) for r in rows]

def update_channel(channel_id: str, updates: Dict[str, Any]):
    fields = []
    values = []
    for k, v in updates.items():
        if k != "id":
            fields.append(f"{k} = ?")
            values.append(v)
    if not fields:
        return
    values.append(channel_id)
    with get_db() as conn:
        conn.execute(f"UPDATE channels SET {', '.join(fields)} WHERE id = ?;", values)
        conn.commit()

def get_prompts(category: Optional[str] = None, enabled_only: bool = False) -> List[Dict[str, Any]]:
    with get_db() as conn:
        query = "SELECT * FROM prompts WHERE 1=1"
        params = []
        if category:
            query += " AND category = ?"
            params.append(category)
        if enabled_only:
            query += " AND enabled = 1"
        query += " ORDER BY last_used_at ASC, use_count ASC;"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

def insert_prompt(prompt_id: str, category: str, base_text: str, enabled: int = 1):
    with get_db() as conn:
        conn.execute("""
        INSERT INTO prompts (id, category, base_text, enabled, use_count)
        VALUES (?, ?, ?, ?, 0);
        """, (prompt_id, category, base_text, enabled))
        conn.commit()

def log_delivery(log_id: str, channel_id: str, prompt_id: Optional[str], base_prompt: Optional[str],
                 generated_text: str, media_type: str = 'text', status: str = 'sent',
                 error_message: Optional[str] = None) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute("""
        INSERT INTO delivery_logs (id, sent_at, channel_id, prompt_id, base_prompt, generated_text, media_type, status, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (log_id, now_iso, channel_id, prompt_id, base_prompt, generated_text, media_type, status, error_message))
        
        # update channel stats
        if status == 'sent':
            conn.execute("""
            UPDATE channels 
            SET total_sent = total_sent + 1,
                last_used_at = ?
            WHERE id = ?;
            """, (now_iso, channel_id))
        
        # update prompt stats
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
            "sent_at": now_iso,
            "channel_id": channel_id,
            "prompt_id": prompt_id,
            "generated_text": generated_text,
            "status": status
        }

def acknowledge_delivery(log_id: str):
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
        
        # reward channel weight and reset unacknowledged streak
        channel_id = log["channel_id"]
        conn.execute("""
        UPDATE channels
        SET total_acknowledged = total_acknowledged + 1,
            consecutive_unacknowledged = 0
        WHERE id = ?;
        """, (channel_id,))
        conn.commit()
        return True

def get_recent_logs(limit: int = 50) -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("""
        SELECT l.*, c.name as channel_name 
        FROM delivery_logs l
        LEFT JOIN channels c ON l.channel_id = c.id
        ORDER BY l.sent_at DESC
        LIMIT ?;
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]
