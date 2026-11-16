import random
import httpx
from typing import Dict, Any, Optional
from ..database import get_settings

VARIATION_HOOKS = {
    "body": [
        "Пауза на тело: {text}",
        "Стоп-кадр. {text}",
        "Сброс автопилота: {text}",
        "Короткий телесный чек: {text}",
        "Где сейчас твоё внимание? {text}",
    ],
    "modes_schemas": [
        "Сверка с реальностью: {text}",
        "Психологический компас: {text}",
        "Взгляд со стороны: {text}",
        "Вопрос Здорового Взрослого: {text}",
        "Заметь свой режим: {text}",
    ],
    "emotion": [
        "Минута честности с собой: {text}",
        "Внутренний барометр: {text}",
        "Останови суету на 10 секунд: {text}",
        "Что происходит внутри? {text}",
    ],
    "grounding": [
        "Возврат в 'Здесь и сейчас': {text}",
        "Заземление: {text}",
        "Ты в физическом мире: {text}",
        "Сенсорный якорь: {text}",
    ],
    "values": [
        "Вопрос на миллион: {text}",
        "Сверка курса: {text}",
        "Ради чего всё это? {text}",
        "Внимание на главное: {text}",
    ],
    "micro_break": [
        "Микро-передышка: {text}",
        "Освежи процессор: {text}",
        "Время выдохнуть: {text}",
    ]
}

OFFLINE_TAILS = [
    "",
    " (сделай вдох прямо сейчас)",
    " [зафиксируй ощущение]",
    " — просто заметь это.",
    " • отметь галочкой, когда сделаешь.",
]

async def mutate_prompt_with_gemini(base_text: str, category: str, api_key: str) -> Optional[str]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    system_instruction = (
        "Ты — лаконичный психологический коуч и ассистент осознанности. "
        "Твоя задача — переформулировать входящее напоминание для саморефлексии. "
        "Правила:\n"
        "1. Максимум 10-14 слов.\n"
        "2. Свежий, живой язык, без заезженных клише, канцелярита и банальностей.\n"
        "3. Сохрани суть и фокус напоминания.\n"
        "4. Верни ТОЛЬКО переформулированный текст без кавычек и пояснений."
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"{system_instruction}\n\nБазовое напоминание: {base_text}"}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.85,
            "maxOutputTokens": 60
        }
    }
    async with httpx.AsyncClient(timeout=8.0) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code == 200:
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts and "text" in parts[0]:
                    return parts[0]["text"].strip().strip('"').strip("'")
    return None

async def mutate_prompt_with_openai(base_text: str, category: str, api_key: str) -> Optional[str]:
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Переформулируй психологическое напоминание для анти-замыливания. "
                    "До 12 слов, живой тон, прямой вопрос или призыв к действию. Без кавычек."
                )
            },
            {"role": "user", "content": base_text}
        ],
        "temperature": 0.85,
        "max_tokens": 50
    }
    async with httpx.AsyncClient(timeout=8.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            choices = data.get("choices", [])
            if choices:
                return choices[0]["message"]["content"].strip().strip('"')
    return None

def mutate_prompt_smart_fallback(base_text: str, category: str) -> str:
    hooks = VARIATION_HOOKS.get(category, VARIATION_HOOKS["body"])
    template = random.choice(hooks)
    tail = random.choice(OFFLINE_TAILS)
    
    # Randomly slightly adjust capitalization or punctuation
    clean_text = base_text.strip()
    if clean_text.endswith("."):
        clean_text = clean_text[:-1]
        
    return template.format(text=clean_text) + tail

async def mutate_prompt(base_text: str, category: str) -> str:
    settings = get_settings()
    provider = settings.get("llm_provider", "fallback")
    
    if provider == "gemini" and settings.get("gemini_api_key"):
        try:
            mutated = await mutate_prompt_with_gemini(base_text, category, settings["gemini_api_key"])
            if mutated:
                return mutated
        except Exception:
            pass # fallback if API call fails
            
    elif provider == "openai" and settings.get("openai_api_key"):
        try:
            mutated = await mutate_prompt_with_openai(base_text, category, settings["openai_api_key"])
            if mutated:
                return mutated
        except Exception:
            pass
            
    # Smart offline fallback
    return mutate_prompt_smart_fallback(base_text, category)
