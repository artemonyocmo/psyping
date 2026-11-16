import uuid
from typing import List, Tuple
from .database import get_db

SEED_PROMPTS: List[Tuple[str, str, str]] = [
    # (id, category, base_text)
    # 1. Body & Somatics
    ("body_jaw_shoulders", "body", "Опусти плечи, разомкни челюсти и сделай один длинный медленный выдох через рот."),
    ("body_feet_ground", "body", "Почувствуй опору под ногами и вес своего тела в кресле. Где сейчас главное напряжение?"),
    ("body_eyes_horizon", "body", "Оторви взгляд от экрана на 20 секунд. Посмотри в самую дальнюю точку за окном."),
    ("body_belly_breath", "body", "Положи ладонь на живот. Сделай 3 вдоха животом, удлиняя выдох в два раза."),
    ("body_posture_reset", "body", "Выпрями спину без напряжения, сделай круговое движение плечами назад и расслабь лоб."),

    # 2. Schema Therapy & Ego Modes
    ("schema_active_mode", "modes_schemas", "В каком режиме ты сейчас? Требовательный критик, Уязвимый ребенок или Здоровый взрослый?"),
    ("schema_critic_filter", "modes_schemas", "Мысль, которая сейчас крутится в голове — это факт или голос внутреннего Критика?"),
    ("schema_healthy_adult", "modes_schemas", "Что прямо сейчас сказал бы тебе твой Здоровый Взрослый, чтобы поддержать?"),
    ("schema_coping_check", "modes_schemas", "Не включился ли сейчас режим 'Избегающего защитника' или прокрастинации? От чего ты прячешься?"),

    # 3. Emotions & Mindfulness
    ("emotion_name_it", "emotion", "Что ты чувствуешь прямо в эту секунду? Назови эмоцию одним точным словом без осуждения."),
    ("emotion_body_signal", "emotion", "Где в теле сейчас отзывается твоё текущее состояние (в груди, горле, животе)?"),
    ("emotion_allow_space", "emotion", "Позволь текущему чувству просто побыть 10 секунд. Тебе не нужно срочно его исправлять."),
    ("emotion_defusion", "emotion", "Заметь свои мысли как облака на небе: 'Я замечаю мысль, что...'. Ты не равен своим мыслям."),

    # 4. Grounding (5-4-3-2-1 / Sensory)
    ("grounding_three_colors", "grounding", "Найди глазами 3 предмета синего или зеленого цвета вокруг себя прямо сейчас."),
    ("grounding_sounds", "grounding", "Закрой глаза на 5 секунд. Выдели 2 самых тихих звука в пространстве вокруг тебя."),
    ("grounding_tactile", "grounding", "Потрогай текстуру стола, одежды или кружки. Насколько она теплая, гладкая или шершавая?"),
    ("grounding_here_now", "grounding", "Сверка с реальностью: год, месяц, день недели, комната, в которой ты находишься. Ты в безопасности."),

    # 5. Values & Intentionality (ACT)
    ("values_compass", "values", "То, чем ты занят прямо сейчас — это движение к твоим ценностям или избегание дискомфорта?"),
    ("values_gentle_choice", "values", "Какой один крошечный добрый шаг по отношению к себе ты можешь сделать в ближайшие 10 минут?"),
    ("values_important_today", "values", "Если бы день закончился сейчас, за что одно ты мог бы искренне поблагодарить себя?"),
    ("values_energy_drain", "values", "Где сейчас утекает твоя энергия? Стоит ли это твоих сил?"),

    # 6. Micro-Break & Pause
    ("break_drink_water", "micro_break", "Сделай медленный глоток воды. Почувствуй прохладу и температуру."),
    ("break_hand_stretch", "micro_break", "Потяни пальцы и запястья в замок, сбрось напряжение с кистей рук."),
    ("break_silence_30s", "micro_break", "Посиди ровно 30 секунд в полной тишине, не трогая клавиатуру и телефон.")
]

def seed_prompts_if_empty():
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM prompts;").fetchone()[0]
        if count == 0:
            for pid, cat, text in SEED_PROMPTS:
                conn.execute("""
                INSERT OR IGNORE INTO prompts (id, category, base_text, enabled, use_count)
                VALUES (?, ?, ?, 1, 0);
                """, (pid, cat, text))
            conn.commit()
