"""Общий обзор лога: тики, длительность, кол-во событий по типам."""
import json
import sys
from collections import Counter

def main(logfile: str) -> None:
    with open(logfile) as f:
        lines = [json.loads(l) for l in f if l.strip()]

    events = Counter(l.get("event", "unknown") for l in lines)

    ticks = [l for l in lines if l.get("event") == "tick_complete"]
    first_ts = lines[0].get("timestamp", "")
    last_ts = lines[-1].get("timestamp", "")

    print(f"Файл: {logfile}")
    print(f"Строк: {len(lines)}")
    print(f"Тиков: {len(ticks)}")
    print(f"Начало: {first_ts}")
    print(f"Конец:  {last_ts}")
    print(f"\nСобытия по типам:")
    for event, count in events.most_common(20):
        print(f"  {event}: {count}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "logs/run_20260415_031715.json")
