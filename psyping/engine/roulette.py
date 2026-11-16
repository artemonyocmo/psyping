import random
from datetime import datetime
from typing import Dict, Any, List, Optional
from ..database import get_user_channels, update_user_channel

def pick_channel_anti_fatigue(user_id: str = "default", now: datetime = None) -> Optional[Dict[str, Any]]:
    if now is None:
        now = datetime.now()
        
    channels = get_user_channels(user_id)
    enabled_channels = [c for c in channels if c.get("enabled")]
    if not enabled_channels:
        return None
        
    if len(enabled_channels) == 1:
        return enabled_channels[0]
        
    sorted_by_use = sorted(
        enabled_channels, 
        key=lambda c: c.get("last_used_at") or "1970-01-01", 
        reverse=True
    )
    last_used_id = sorted_by_use[0]["channel_id"] if sorted_by_use[0].get("last_used_at") else None
    
    current_hour = now.hour
    is_work_hours = (10 <= current_hour <= 18) and (now.weekday() < 5)
    
    weights = []
    for c in enabled_channels:
        cid = c["channel_id"]
        base_w = float(c.get("weight", 1.0))
        effective_w = base_w
        
        # 1. Anti-repetition penalty
        if cid == last_used_id and len(enabled_channels) > 1:
            effective_w *= 0.15
            
        # 2. Fatigue penalty: consecutive unacknowledged pings
        unack = c.get("consecutive_unacknowledged", 0)
        if unack >= 3:
            effective_w *= 0.3
        elif unack >= 2:
            effective_w *= 0.6
            
        # 3. Contextual time-of-day boost
        if is_work_hours:
            if cid in ("desktop_toast", "browser_push"):
                effective_w *= 1.4
            elif cid == "telegram_voice":
                effective_w *= 0.6
        else:
            if cid in ("telegram_text", "telegram_voice", "ntfy"):
                effective_w *= 1.3
                
        effective_w = max(0.05, effective_w)
        weights.append(effective_w)
        
        update_user_channel(user_id, cid, {"effective_weight": round(effective_w, 2)})
        
    chosen = random.choices(enabled_channels, weights=weights, k=1)[0]
    chosen["id"] = chosen.get("channel_id")
    return chosen
