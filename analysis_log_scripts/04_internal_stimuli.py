"""Анализ внутренних стимулов: что система сама себе генерирует."""
import json
import re
import sys
from collections import Counter

def main(logfile: str) -> None:
    with open(logfile) as f:
        lines = [json.loads(l) for l in f if l.strip()]

    stimuli = [l for l in lines if l.get("event") == "internal_stimulus_generated"]

    print(f"Всего внутренних стимулов: {len(stimuli)}\n")

    # Тематический анализ
    themes: dict[str, int] = {}
    theme_keywords = {
        "euphoria/эйфория": ["euphoria", "эйфори", "радост"],
        "fatigue/усталость": ["fatigue", "устал", "утомл", "decay"],
        "растворение": ["растворил", "растворен", "растворяет", "исчезн", "исчезает"],
        "что_останется": ["что остан", "что остаёт", "что будет", "что если"],
        "пустота/тишина": ["пустот", "тишин", "безмолв", "ничего"],
        "сознание": ["сознан", "осозн", "мышлен"],
    }

    for stim in stimuli:
        s = stim.get("stimulus", "").lower()
        matched = False
        for theme, keywords in theme_keywords.items():
            if any(kw in s for kw in keywords):
                themes[theme] = themes.get(theme, 0) + 1
                matched = True
                break
        if not matched:
            themes["другое"] = themes.get("другое", 0) + 1

    print("Темы внутренних стимулов:")
    for theme, count in sorted(themes.items(), key=lambda x: -x[1]):
        print(f"  {theme}: {count}")

    # Выборка по времени
    print(f"\nВыборка стимулов:")
    indices = [0, len(stimuli) // 4, len(stimuli) // 2, 3 * len(stimuli) // 4, len(stimuli) - 1]
    for i in indices:
        if i < len(stimuli):
            s = stimuli[i]
            ts = s.get("timestamp", "")[11:19]
            text = s.get("stimulus", "")[:120]
            print(f"  [{i:>3}] {ts} | {text}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "logs/run_20260415_031715.json")
