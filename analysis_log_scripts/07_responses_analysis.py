"""Анализ ответов: уникальность, повторения, длина, ответы на внешние стимулы."""
import json
import sys
from collections import Counter

def main(logfile: str) -> None:
    with open(logfile) as f:
        lines = [json.loads(l) for l in f if l.strip()]

    ticks = [l for l in lines if l.get("event") == "tick_complete"]
    responses = [(l["tick"], l["response"]) for l in ticks if l.get("response")]

    print(f"=== Ответы системы ===")
    print(f"Всего ответов: {len(responses)}")
    unique = set(r for _, r in responses)
    print(f"Уникальных: {len(unique)}")
    print(f"Повторяющихся: {len(responses) - len(unique)}")

    resp_counter = Counter(r for _, r in responses)
    print(f"\nТоп-10 повторяющихся:")
    for resp, count in resp_counter.most_common(10):
        print(f"  [{count}x] {resp[:80]}")

    # Response length over time
    print(f"\nДлина ответов по времени:")
    sample_indices = [0, len(responses)//4, len(responses)//2, 3*len(responses)//4, len(responses)-1]
    for i in sample_indices:
        tick, resp = responses[i]
        print(f"  T{tick:>5} | {len(resp)} символов | {resp[:60]}...")

    # External stimuli responses
    ext_stimuli = [l for l in lines if l.get("event") == "stimulus_submitted"]
    print(f"\n=== Внешние стимулы от пользователя ({len(ext_stimuli)}) ===")
    for stim in ext_stimuli:
        ts = stim.get("timestamp", "")[11:19]
        s = stim.get("stimulus", "")
        print(f"  {ts} | \"{s}\"")

    # Find responses near external stimuli ticks
    if ext_stimuli:
        print(f"\nОтветы на внешние стимулы:")
        for stim in ext_stimuli:
            stim_ts = stim.get("timestamp", "")
            s = stim.get("stimulus", "")
            # Find next response after this timestamp
            for tick, resp in responses:
                tick_data = next((t for t in ticks if t["tick"] == tick), None)
                if tick_data and tick_data.get("timestamp", "") > stim_ts:
                    ac = tick_data.get("active_channels", {})
                    print(f"  \"{s[:30]}\" -> [{list(ac.keys())}] \"{resp[:80]}\"")
                    break

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "logs/run_20260415_031715.json")
