#!/usr/bin/env python3
"""Train a Behavior Cloning recovery policy from the event log.

Usage:
    python scripts/train_offline_recovery.py \\
        --events data/events.db \\
        --output data/recovery_bc.json \\
        --epochs 200 --max-records 10000

Run when you've accumulated enough event data (≥ 1000 transitions
recommended). The output JSON can be loaded at boot via:

    OfflineRecoveryPolicy.load("data/recovery_bc.json")
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.ERROR, stream=sys.stderr)
try:
    import structlog

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.ERROR),
    )
except ImportError:
    pass

from src.ml.dataset import build_dataset_from_event_store  # noqa: E402
from src.ml.offline_recovery import OfflineRecoveryPolicy, train_bc  # noqa: E402
from src.persistence.sqlite_event_store import SqliteEventStore  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Train BC recovery policy")
    p.add_argument("--events", default="data/events.db")
    p.add_argument("--output", default="data/recovery_bc.json")
    p.add_argument("--epochs", type=int, default=200)
    p.add_argument("--max-records", type=int, default=10000)
    p.add_argument("--lr", type=float, default=0.05)
    args = p.parse_args()

    if not Path(args.events).exists():
        print(f"Error: event store not found at {args.events}", file=sys.stderr)
        sys.exit(1)

    es = SqliteEventStore(args.events)
    try:
        dataset = build_dataset_from_event_store(es, max_records=args.max_records)
        if dataset.n == 0:
            print("Empty dataset — nothing to train.")
            return
        print(f"Loaded {dataset.n} transitions from {args.events}")

        policy = train_bc(dataset, n_epochs=args.epochs, learning_rate=args.lr)
        OfflineRecoveryPolicy(bc_policy=policy).save(args.output)
        print(
            f"Saved trained BC policy to {args.output}: "
            f"n_features={policy.n_features}, n_actions={policy.n_actions}"
        )
    finally:
        es.close()


if __name__ == "__main__":
    main()
