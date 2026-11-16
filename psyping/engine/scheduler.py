import random
from datetime import datetime, time, timedelta, timezone
from typing import Dict, Any, Optional
from ..database import get_or_create_user, update_user

def parse_time_str(t_str: str) -> time:
    try:
        parts = t_str.split(":")
        return time(int(parts[0]), int(parts[1]))
    except Exception:
        return time(22, 0)

def is_in_quiet_hours(dt: datetime, quiet_start: time, quiet_end: time) -> bool:
    t = dt.time()
    if quiet_start <= quiet_end:
        return quiet_start <= t <= quiet_end
    else:
        return t >= quiet_start or t <= quiet_end

def calculate_next_run_for_user(user: Dict[str, Any], now: datetime = None) -> datetime:
    if now is None:
        now = datetime.now()
    
    quiet_start = parse_time_str(user.get("quiet_hours_start", "22:00"))
    quiet_end = parse_time_str(user.get("quiet_hours_end", "09:00"))
    daily_count = max(1, int(user.get("daily_target_count", 4)))
    
    # Calculate active hours in day
    if quiet_start > quiet_end:
        quiet_duration_hours = (24 - quiet_start.hour - quiet_start.minute/60) + (quiet_end.hour + quiet_end.minute/60)
    else:
        quiet_duration_hours = (quiet_end.hour + quiet_end.minute/60) - (quiet_start.hour + quiet_start.minute/60)
        
    active_hours = max(4.0, 24.0 - quiet_duration_hours)
    mean_interval_minutes = (active_hours * 60.0) / daily_count
    
    # Jitter factor: between 0.45 and 1.65 (Poisson-like dispersion)
    jitter = random.uniform(0.45, 1.65)
    random_minutes = mean_interval_minutes * jitter
    
    candidate = now + timedelta(minutes=random_minutes)
    
    # If candidate falls into quiet hours, postpone to next morning
    if is_in_quiet_hours(candidate, quiet_start, quiet_end):
        if candidate.time() >= quiet_start:
            target_date = (candidate + timedelta(days=1)).date()
        else:
            target_date = candidate.date()
            
        base_wake = datetime.combine(target_date, quiet_end)
        morning_offset = random.uniform(15, 90)
        candidate = base_wake + timedelta(minutes=morning_offset)
        
    return candidate

def schedule_next_ping(user_id: str = "default", now: datetime = None) -> str:
    user = get_or_create_user(user_id)
    next_dt = calculate_next_run_for_user(user, now)
    iso_str = next_dt.isoformat()
    update_user(user_id, {"next_run_at": iso_str})
    return iso_str

def calculate_next_run(now: datetime = None) -> datetime:
    user = get_or_create_user("default")
    return calculate_next_run_for_user(user, now)
