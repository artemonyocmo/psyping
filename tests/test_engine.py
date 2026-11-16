import asyncio
from datetime import datetime, time, timedelta

from psyping.database import (
    init_db, get_settings, update_settings, get_channels, update_channel,
    get_prompts, log_delivery, acknowledge_delivery, get_recent_logs
)
from psyping.seed_data import seed_prompts_if_empty
from psyping.engine.scheduler import is_in_quiet_hours, calculate_next_run, parse_time_str
from psyping.engine.roulette import pick_channel_anti_fatigue
from psyping.engine.mutator import mutate_prompt_smart_fallback
from psyping.engine.dispatcher import dispatch_reminder

def test_quiet_hours():
    # Quiet hours: 22:00 to 09:00
    q_start = time(22, 0)
    q_end = time(9, 0)
    
    assert is_in_quiet_hours(datetime(2026, 11, 16, 23, 30), q_start, q_end) is True
    assert is_in_quiet_hours(datetime(2026, 11, 16, 3, 15), q_start, q_end) is True
    assert is_in_quiet_hours(datetime(2026, 11, 16, 8, 59), q_start, q_end) is True
    assert is_in_quiet_hours(datetime(2026, 11, 16, 14, 0), q_start, q_end) is False

def test_scheduler_calculation():
    init_db()
    now = datetime(2026, 11, 16, 12, 0) # Daytime
    next_dt = calculate_next_run(now)
    assert next_dt > now
    # Check that it scheduled within realistic interval
    diff = (next_dt - now).total_seconds() / 60
    assert 20 <= diff <= 400

def test_mutator_offline():
    base = "Сделай 3 глубоких вдоха и опусти плечи"
    mutated = mutate_prompt_smart_fallback(base, "body")
    assert len(mutated) > len(base)
    assert "плечи" in mutated

def test_roulette_anti_fatigue():
    init_db()
    channels = get_channels()
    assert len(channels) >= 5
    
    # Simulate high consecutive unacknowledged count on a channel
    update_channel("desktop_toast", {"consecutive_unacknowledged": 5, "last_used_at": datetime.now().isoformat()})
    
    # Pick 50 times - other channels should dominate
    picks = [pick_channel_anti_fatigue()["id"] for _ in range(50)]
    assert picks.count("desktop_toast") < len(picks)

def test_dispatch_and_acknowledge():
    init_db()
    seed_prompts_if_empty()
    
    # Test dispatch via browser_push (which always succeeds in memory)
    res = asyncio.run(dispatch_reminder(force_channel_id="browser_push"))
    assert res["success"] is True
    log_id = res["log_id"]
    assert log_id is not None
    
    # Test acknowledge
    ok = acknowledge_delivery(log_id)
    assert ok is True
    
    # Check log
    logs = get_recent_logs(limit=5)
    matched = [l for l in logs if l["id"] == log_id]
    assert len(matched) == 1
    assert matched[0]["status"] == "acknowledged"
    assert matched[0]["acknowledged_at"] is not None

if __name__ == "__main__":
    print("Running tests...")
    test_quiet_hours()
    print("✓ test_quiet_hours passed")
    test_scheduler_calculation()
    print("✓ test_scheduler_calculation passed")
    test_mutator_offline()
    print("✓ test_mutator_offline passed")
    test_roulette_anti_fatigue()
    print("✓ test_roulette_anti_fatigue passed")
    test_dispatch_and_acknowledge()
    print("✓ test_dispatch_and_acknowledge passed")
    print("ALL TESTS PASSED!")
