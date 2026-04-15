"""Фазы состояния: хронология активных каналов гистерезиса."""
import json
import sys

def main(logfile: str, min_duration: int = 10) -> None:
    with open(logfile) as f:
        lines = [json.loads(l) for l in f if l.strip()]

    ticks = [l for l in lines if l.get("event") == "tick_complete"]

    phases = []
    prev_phase = ""
    start_tick = 1
    for l in ticks:
        tick = l.get("tick", 0)
        ac = l.get("active_channels", {})
        keys = sorted(ac.keys())
        phase = "+".join(keys) if keys else "calm"
        if phase != prev_phase:
            if prev_phase:
                phases.append((start_tick, tick - 1, prev_phase))
            start_tick = tick
            prev_phase = phase
    if prev_phase:
        phases.append((start_tick, ticks[-1]["tick"], prev_phase))

    # Merge adjacent same phases
    merged = []
    for s, e, p in phases:
        if merged and merged[-1][2] == p:
            merged[-1] = (merged[-1][0], e, p)
        else:
            merged.append((s, e, p))

    print(f"Фазы состояния (>= {min_duration} тиков):\n")
    for s, e, p in merged:
        dur = e - s + 1
        if dur >= min_duration:
            minutes = dur * 2 / 60
            print(f"  T{s:>5}-{e:>5} ({dur:>5} тиков, ~{minutes:.1f}мин) | {p}")

    print(f"\nВсего переходов: {len(phases)}")
    print(f"После объединения: {len(merged)}")

if __name__ == "__main__":
    logfile = sys.argv[1] if len(sys.argv) > 1 else "logs/run_20260415_031715.json"
    min_dur = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    main(logfile, min_dur)
