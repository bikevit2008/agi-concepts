"""Анализ runtime-дельт: как менялись параметры системы."""
import json
import sys

def main(logfile: str) -> None:
    with open(logfile) as f:
        lines = [json.loads(l) for l in f if l.strip()]

    deltas = [l for l in lines if l.get("event") == "runtime_delta_applied"]

    if not deltas:
        print("Нет runtime_delta_applied событий")
        return

    params = ["temperature", "context_window", "processing_latency", "bandwidth", "attention_focus", "energy_level"]

    print(f"=== Runtime дельты ({len(deltas)} событий) ===\n")

    for param in params:
        vals = [l["delta"].get(param, 0) for l in deltas]
        non_zero = [v for v in vals if v != 0]
        if non_zero:
            print(f"  {param}:")
            print(f"    min={min(non_zero):.3f}  max={max(non_zero):.3f}  avg={sum(non_zero)/len(non_zero):.3f}  events={len(non_zero)}")
        else:
            print(f"  {param}: не менялся")

    # Vitality/max_tokens from Planning agent
    planning_runs = [l for l in lines if l.get("event") == "agent_run" and l.get("agent") == "Planning"]
    if planning_runs:
        vitalities = [l.get("vitality", 1.0) for l in planning_runs if "vitality" in l]
        max_tokens = [l.get("max_tokens", 1024) for l in planning_runs if "max_tokens" in l]
        if vitalities:
            print(f"\n  vitality (Planning):")
            print(f"    min={min(vitalities):.3f}  max={max(vitalities):.3f}  avg={sum(vitalities)/len(vitalities):.3f}")
        if max_tokens:
            print(f"  max_tokens (Planning):")
            print(f"    min={min(max_tokens)}  max={max(max_tokens)}  avg={sum(max_tokens)/len(max_tokens):.0f}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "logs/run_20260415_031715.json")
