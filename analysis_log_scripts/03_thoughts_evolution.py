"""Эволюция мыслей: выборка спонтанных мыслей и рефлексий по времени."""
import json
import sys

def main(logfile: str, sample_count: int = 15) -> None:
    with open(logfile) as f:
        lines = [json.loads(l) for l in f if l.strip()]

    thoughts = [l for l in lines if l.get("event") == "spontaneous_thought"]
    reflections = [l for l in lines if l.get("event") == "reflection_complete"]

    print(f"=== Спонтанные мысли ({len(thoughts)} всего) ===\n")
    indices = _sample_indices(len(thoughts), sample_count)
    for i in indices:
        t = thoughts[i]
        ts = t.get("timestamp", "")[11:19]
        text = t.get("thought", "")[:150]
        print(f"[{i:>4}/{len(thoughts)}] {ts} | {text}")

    print(f"\n=== Рефлексии ({len(reflections)} всего) ===\n")
    indices = _sample_indices(len(reflections), sample_count)
    for i in indices:
        r = reflections[i]
        ts = r.get("timestamp", "")[11:19]
        text = r.get("thought", "")[:150]
        print(f"[{i:>4}/{len(reflections)}] {ts} | {text}")

def _sample_indices(total: int, count: int) -> list[int]:
    if total <= count:
        return list(range(total))
    step = total / count
    return [int(i * step) for i in range(count)] + [total - 1]

if __name__ == "__main__":
    logfile = sys.argv[1] if len(sys.argv) > 1 else "logs/run_20260415_031715.json"
    main(logfile)
