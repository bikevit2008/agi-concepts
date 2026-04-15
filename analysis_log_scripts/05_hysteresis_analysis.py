"""Анализ гистерезиса: стимуляция каналов, самостимуляция, спираль смерти."""
import json
import sys
from collections import Counter

def main(logfile: str) -> None:
    with open(logfile) as f:
        lines = [json.loads(l) for l in f if l.strip()]

    # Emotion agent stimulation
    emotion_stim = [l for l in lines if l.get("event") == "hysteresis_stimulated"]
    emotion_channels = Counter()
    for l in emotion_stim:
        for ch in l.get("stimuli", {}):
            emotion_channels[ch] += 1

    print(f"=== Стимуляция от Emotion-агента ({len(emotion_stim)} событий) ===")
    for ch, cnt in emotion_channels.most_common():
        print(f"  {ch}: {cnt}")

    # Self-stimulation from Reflection
    self_stim = [l for l in lines if l.get("event") == "reflection_self_stimulated"]
    pos_channels = Counter()
    neg_channels = Counter()
    for l in self_stim:
        for ch, val in l.get("stimuli", {}).items():
            if val > 0:
                pos_channels[ch] += 1
            else:
                neg_channels[ch] += 1

    print(f"\n=== Самостимуляция от Reflection ({len(self_stim)} событий) ===")
    print("Положительная (накрутка):")
    for ch, cnt in pos_channels.most_common():
        print(f"  {ch}: {cnt}")
    print("Отрицательная (успокоение):")
    for ch, cnt in neg_channels.most_common():
        print(f"  {ch}: {cnt}")

    # Death spiral detection
    ticks = [l for l in lines if l.get("event") == "tick_complete"]
    stuck_start = None
    stuck_periods = []
    for l in ticks:
        ac = l.get("active_channels", {})
        tick = l.get("tick", 0)
        if ac.get("stress", 0) >= 0.99 and ac.get("fatigue", 0) >= 0.99:
            if stuck_start is None:
                stuck_start = tick
        else:
            if stuck_start is not None:
                stuck_periods.append((stuck_start, tick - 1))
                stuck_start = None
    if stuck_start:
        stuck_periods.append((stuck_start, ticks[-1]["tick"]))

    print(f"\n=== Спираль смерти (stress+fatigue=1.0) ===")
    print(f"Количество периодов залипания: {len(stuck_periods)}")
    long_periods = [(s, e) for s, e in stuck_periods if e - s >= 10]
    if long_periods:
        print(f"Длинные периоды (>= 10 тиков):")
        for s, e in long_periods:
            dur = e - s + 1
            print(f"  T{s:>5}-{e:>5} ({dur} тиков, ~{dur*2/60:.1f} мин)")
    total_stuck = sum(e - s + 1 for s, e in stuck_periods)
    total_ticks = len(ticks)
    print(f"\nОбщее время в спирали: {total_stuck} тиков из {total_ticks} ({100*total_stuck/total_ticks:.1f}%)")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "logs/run_20260415_031715.json")
