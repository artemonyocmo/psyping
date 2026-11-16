import random
from datetime import datetime, time, timedelta, timezone
from typing import Tuple
from ..database import get_settings, update_settings

def parse_time_str(t_str: str) -> time:
    try:
        parts = t_str.split(":")
        return time(int(parts[0]), int(parts[1]))
    except Exception:
        return time(22, 0)

def is_in_quiet_hours(dt: datetime, quiet_start: time, quiet_end: time) -> bool:
    t = dt.time()
    if quiet_start <= quiet_end:
        # e.g. 01:00 to 07:00
        return quiet_start <= t <= quiet_end
    else:
        # e.g. 22:00 to 09:00 (crosses midnight)
        return t >= quiet_start or t <= quiet_end

def calculate_next_run(now: datetime = None) -> datetime:
    if now is None:
        now = datetime.now()
    
    settings = get_settings()
    quiet_start = parse_time_str(settings.get("quiet_hours_start", "22:00"))
    quiet_end = parse_time_str(settings.get("quiet_hours_end", "09:00"))
    daily_count = max(1, int(settings.get("daily_target_count", 4)))
    
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
        # Find next morning after quiet_end
        if candidate.time() >= quiet_start:
            target_date = (candidate + timedelta(days=1)).date()
        else:
            target_date = candidate.date()
            
        base_wake = datetime.combine(target_date, quiet_end)
        # Add random morning delay (15 to 90 minutes)
        morning_offset = random.uniform(15, 90)
        candidate = base_wake + timedelta(minutes=morning_offset)
        
    return candidate

def schedule_next_ping(now: datetime = None) -> str:
    next_dt = calculate_next_run(now)
    iso_str = next_dt.isoformat()
    update_settings({"next_run_at": iso_str})
    return iso_str
