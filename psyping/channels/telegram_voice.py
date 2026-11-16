import io
import os
import tempfile
import httpx
import edge_tts
from typing import Dict, Any, Tuple, Optional
from .base import BaseChannel

class TelegramVoiceChannel(BaseChannel):
    @property
    def channel_id(self) -> str:
        return "telegram_voice"

    async def generate_audio_edge(self, text: str, preferred_voice: str) -> bytes:
        voices = [preferred_voice, "ru-RU-SvetlanaNeural", "ru-RU-DmitryNeural"]
        last_err = None
        for v in voices:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                communicate = edge_tts.Communicate(text, v)
                await communicate.save(tmp_path)
                with open(tmp_path, "rb") as f:
                    data = f.read()
                if data and len(data) > 200:
                    return data
            except Exception as e:
                last_err = e
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
        raise RuntimeError(f"Все голоса Edge TTS завершились ошибкой: {last_err}")

    async def generate_audio_openai(self, text: str, api_key: str) -> Optional[bytes]:
        url = "https://api.openai.com/v1/audio/speech"
        headers = {"Authorization": f"Bearer {api_key}"}
        payload = {
            "model": "tts-1",
            "voice": "onyx",
            "input": text
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                return resp.content
        return None

    async def deliver(self, log_id: str, text: str, category: str, settings: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        bot_token = settings.get("telegram_bot_token", "").strip()
        chat_id = settings.get("telegram_chat_id", "").strip()

        if not bot_token or not chat_id:
            return False, "Telegram Bot Token или Chat ID не заполнены в настройках"

        voice_name = settings.get("tts_voice", "ru-RU-SvetlanaNeural")
        openai_key = settings.get("openai_api_key", "").strip()

        audio_bytes = None
        try:
            # If OpenAI key provided and set, try OpenAI TTS, otherwise edge-tts
            if settings.get("llm_provider") == "openai" and openai_key:
                audio_bytes = await self.generate_audio_openai(text, openai_key)
            
            if not audio_bytes:
                audio_bytes = await self.generate_audio_edge(text, voice_name)
        except Exception as e:
            return False, f"TTS synthesis error: {str(e)}"

        if not audio_bytes:
            return False, "Failed to synthesize voice audio."

        url = f"https://api.telegram.org/bot{bot_token}/sendVoice"
        
        category_emojis = {
            "body": "🧘‍♂️ Тело (Голос)",
            "modes_schemas": "🧠 Режимы (Голос)",
            "emotion": "🌊 Эмоции (Голос)",
            "grounding": "⚓ Заземление (Голос)",
            "values": "🧭 Ценности (Голос)",
            "micro_break": "☕ Передышка (Голос)"
        }
        tag = category_emojis.get(category, "🎙️ Голосовое напоминание")
        caption = f"<b>{tag}</b>\n{text}"
        
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "Послушал и сделал ✓", "callback_data": f"ack:{log_id}"}
                ]
            ]
        }

        try:
            files = {
                "voice": ("voice.mp3", audio_bytes, "audio/mpeg")
            }
            data = {
                "chat_id": chat_id,
                "caption": caption,
                "parse_mode": "HTML",
                "reply_markup": str(keyboard).replace("'", '"')
            }
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(url, data=data, files=files)
                if resp.status_code == 200:
                    return True, None
                else:
                    return False, f"Telegram API error {resp.status_code}: {resp.text}"
        except Exception as e:
            return False, f"Telegram HTTP error: {str(e)}"
