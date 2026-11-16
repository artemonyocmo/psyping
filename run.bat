@echo off
chcp 65001 > nul
echo [PsyPing] Starting Omnichannel Psychological Reminders...
uv run python -m psyping.main
pause
