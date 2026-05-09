"""ML regulators — rumination detector + collapse forecaster + recovery policy.

Stage 16 adds offline-RL components:
  - dataset.RecoveryDataset    — (s, a, r, s', done) from event store
  - offline_recovery.BehaviorCloningPolicy — multinomial logreg
  - offline_recovery.OfflineRecoveryPolicy — IRecoveryPolicy with BC
                                             + rule-based fallback
"""

from src.ml.collapse_forecaster import CsdCollapseForecaster
from src.ml.dataset import (
    ACTION_ORDER,
    FEATURE_KEYS,
    RecoveryDataset,
    build_dataset_from_event_store,
)
from src.ml.offline_recovery import (
    BehaviorCloningPolicy,
    OfflineRecoveryPolicy,
    train_bc,
)
from src.ml.recovery_policy import RuleBasedRecoveryPolicy
from src.ml.rumination_detector import ShannonRuminationDetector

__all__ = [
    "ACTION_ORDER",
    "BehaviorCloningPolicy",
    "CsdCollapseForecaster",
    "FEATURE_KEYS",
    "OfflineRecoveryPolicy",
    "RecoveryDataset",
    "RuleBasedRecoveryPolicy",
    "ShannonRuminationDetector",
    "build_dataset_from_event_store",
    "train_bc",
]
