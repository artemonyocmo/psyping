import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from ..database import (
    get_or_create_user, update_user, get_prompts_for_user, get_user_channels,
    log_delivery, update_user_channel, get_global_config
)
from .roulette import pick_channel_anti_fatigue
from .mutator import mutate_prompt
from .scheduler import schedule_next_ping
from ..channels.desktop_toast import DesktopToastChannel
from ..channels.telegram_text import TelegramTextChannel
from ..channels.telegram_voice import TelegramVoiceChannel
from ..channels.ntfy import NtfyChannel
from ..channels.browser_push import BrowserPushChannel
from ..channels.webhook import WebhookChannel

CHANNELS = {
    "desktop_toast": DesktopToastChannel(),
    "telegram_text": TelegramTextChannel(),
    "telegram_voice": TelegramVoiceChannel(),
    "ntfy": NtfyChannel(),
    "browser_push": BrowserPushChannel(),
    "webhook": WebhookChannel()
}

async def dispatch_reminder(
    user_id: str = "default",
    force_channel_id: Optional[str] = None,
    force_prompt_id: Optional[str] = None,
    custom_text: Optional[str] = None
) -> Dict[str, Any]:
    user = get_or_create_user(user_id)
    global_cfg = get_global_config()
    
    # Combined settings for channel deliverers
    merged_settings = dict(user)
    merged_settings.update(global_cfg)
    
    # 1. Pick prompt
    prompts = get_prompts_for_user(user_id, enabled_only=True)
    if not prompts:
        return {"success": False, "error": "Нет активных тем для напоминаний в библиотеке"}
        
    chosen_prompt = None
    if force_prompt_id:
        for p in prompts:
            if p["id"] == force_prompt_id:
                chosen_prompt = p
                break
    if not chosen_prompt:
        chosen_prompt = prompts[0]
        
    base_text = custom_text or chosen_prompt["base_text"]
    category = chosen_prompt.get("category", "body")
    
    # 2. Mutate text to defeat habituation
    if custom_text:
        mutated_text = custom_text
    else:
        mutated_text = await mutate_prompt(base_text, category)
        
    # 3. Pick channel
    if force_channel_id and force_channel_id in CHANNELS:
        chosen_channel_id = force_channel_id
        chosen_channel_name = force_channel_id
    else:
        channel_info = pick_channel_anti_fatigue(user_id)
        if not channel_info:
            return {"success": False, "error": "Нет активных каналов доставки для данного профиля"}
        chosen_channel_id = channel_info["channel_id"]
        chosen_channel_name = channel_info.get("name", chosen_channel_id)

    channel_handler = CHANNELS.get(chosen_channel_id)
    if not channel_handler:
        return {"success": False, "error": f"Канал {chosen_channel_id} не реализован"}
        
    # 4. Generate unique log_id and deliver
    log_id = str(uuid.uuid4())[:8]
    media_type = "voice" if chosen_channel_id == "telegram_voice" else "text"
    
    success, err_msg = await channel_handler.deliver(log_id, mutated_text, category, merged_settings)
    
    # 5. Log result
    status = "sent" if success else "failed"
    delivery_rec = log_delivery(
        log_id=log_id,
        user_id=user_id,
        channel_id=chosen_channel_id,
        prompt_id=chosen_prompt["id"] if not custom_text else None,
        base_prompt=base_text,
        generated_text=mutated_text,
        media_type=media_type,
        status=status,
        error_message=err_msg
    )
    
    # If failed, penalize channel fatigue counter
    if not success:
        channels = get_user_channels(user_id)
        for c in channels:
            if c["channel_id"] == chosen_channel_id:
                update_user_channel(user_id, chosen_channel_id, {
                    "consecutive_unacknowledged": c.get("consecutive_unacknowledged", 0) + 1
                })
                break
                
    # 6. Schedule next ping
    now_iso = datetime.now(timezone.utc).isoformat()
    update_user(user_id, {"last_run_at": now_iso})
    next_time = schedule_next_ping(user_id)
    
    return {
        "success": success,
        "user_id": user_id,
        "log_id": log_id,
        "channel_id": chosen_channel_id,
        "channel_name": chosen_channel_name,
        "category": category,
        "base_text": base_text,
        "mutated_text": mutated_text,
        "next_run_at": next_time,
        "error": err_msg
    }
