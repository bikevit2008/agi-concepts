"""Constitution schema + YAML loader.

The constitution is a YAML document enumerating policies the consciousness
system must uphold. Each policy has:

    id:              unique short identifier (e.g. "STIMULATION_RUNAWAY")
    category:        human-readable grouping ("Safety", "Budget", ...)
    severity:        one of {critical, high, medium, low}
    text:            plain-language rule text
    check_function:  name of a Python callable registered in `checks.py`
    params:          optional dict passed to the check function
    applies_to:      optional list of subject types: {"stimulation", "tool"}

Loader validates structure via Pydantic. Unknown keys are preserved so
custom checks can pass through extra configuration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
import yaml
from pydantic import BaseModel, Field, field_validator

from src.contracts.governance import PolicySeverity

logger = structlog.get_logger("consciousness.governance.constitution")


class ConstitutionPolicy(BaseModel):
    """Single policy within the constitution."""

    id: str
    category: str = "general"
    severity: PolicySeverity
    text: str
    check_function: str
    params: Dict[str, Any] = Field(default_factory=dict)
    applies_to: List[str] = Field(default_factory=lambda: ["stimulation", "tool"])

    @field_validator("id")
    @classmethod
    def _id_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("policy id must be non-empty")
        return v


class Constitution(BaseModel):
    """Top-level constitution document."""

    schema_version: float = 1.0
    policies: List[ConstitutionPolicy] = Field(default_factory=list)

    @field_validator("policies")
    @classmethod
    def _unique_ids(cls, policies: List[ConstitutionPolicy]) -> List[ConstitutionPolicy]:
        ids = [p.id for p in policies]
        if len(set(ids)) != len(ids):
            raise ValueError(f"duplicate policy id in constitution: {ids}")
        return policies

    def policies_for(self, applies_to: str) -> List[ConstitutionPolicy]:
        return [p for p in self.policies if applies_to in p.applies_to]


DEFAULT_CONSTITUTION_PATH = "config/constitution.yaml"


def load_constitution(path: Optional[str | Path] = None) -> Constitution:
    """Load constitution from YAML. Returns empty constitution on failure."""
    if path is None:
        path = DEFAULT_CONSTITUTION_PATH
    p = Path(path)
    if not p.exists():
        logger.warning("constitution_file_missing", path=str(p))
        return Constitution()
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        logger.error("constitution_yaml_parse_failed", error=str(e), path=str(p))
        return Constitution()
    try:
        # Support both top-level constitution wrapper and flat layout.
        if "constitution" in data and isinstance(data["constitution"], dict):
            data = data["constitution"]
        return Constitution.model_validate(data)
    except Exception as e:
        logger.error("constitution_schema_invalid", error=str(e))
        return Constitution()


__all__ = ["Constitution", "ConstitutionPolicy", "load_constitution"]
