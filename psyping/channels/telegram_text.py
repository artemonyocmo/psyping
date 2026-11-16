import httpx
from typing import Dict, Any, Tuple, Optional
from .base import BaseChannel

class TelegramTextChannel(BaseChannel):
    @property
    def channel_id(self) -> str:
        return "telegram_text"

    async def deliver(self, log_id: str, text: str, category: str, settings: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        bot_token = settings.get("telegram_bot_token", "").strip()
        chat_id = settings.get("telegram_chat_id", "").strip()

        if not bot_token or not chat_id:
            return False, "Telegram Bot Token или Chat ID не заполнены в настройках"

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        
        category_emojis = {
            "body": "🧘‍♂️ Тело",
            "modes_schemas": "🧠 Режимы/Схемы",
            "emotion": "🌊 Эмоции",
            "grounding": "⚓ Заземление",
            "values": "🧭 Ценности",
            "micro_break": "☕ Передышка"
        }
        tag = category_emojis.get(category, "✨ Осознанность")
        
        message_body = (
            f"<b>{tag}</b>\n\n"
            f"{text}\n\n"
            f"<i>Нажми кнопку ниже, чтобы мозг зафиксировал факт выполнения:</i>"
        )
        
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "Сделал ✓", "callback_data": f"ack:{log_id}"},
                    {"text": "Отложить (15 мин)", "callback_data": f"snooze:{log_id}"}
                ]
            ]
        }
        
        payload = {
            "chat_id": chat_id,
            "text": message_body,
            "parse_mode": "HTML",
            "reply_markup": keyboard
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    return True, None
                else:
                    return False, f"Telegram API error {resp.status_code}: {resp.text}"
        except Exception as e:
            return False, f"Telegram HTTP error: {str(e)}"
