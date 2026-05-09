"""Tests for the constitutional auditor (Stage 11)."""

from pathlib import Path

import pytest

from src.contracts.governance import (
    AuditResult,
    ConstitutionalViolation,
    GovernanceDecision,
    IConstitutionalAuditor,
    NullConstitutionalAuditor,
    PolicySeverity,
    RiskTier,
    StimulationRequest,
)
from src.governance.auditor import ConstitutionalAuditor
from src.governance.checks import (
    CHECK_REGISTRY,
    check_circuit_breaker_tripped,
    check_cost_budget_exceeded,
    check_reflection_self_abuse,
    check_stimulation_channel_whitelist,
    check_stimulation_max_intensity,
    check_tool_args_no_secrets,
    check_tool_deny_list,
    register_check,
)
from src.governance.constitution import (
    Constitution,
    ConstitutionPolicy,
    load_constitution,
)


# --- Constitution loader ---------------------------------------------------


def test_load_constitution_from_yaml(tmp_path: Path):
    yaml = tmp_path / "c.yaml"
    yaml.write_text(
        """
constitution:
  schema_version: 1.0
  policies:
    - id: TEST_POLICY
      category: Safety
      severity: critical
      text: "for tests"
      check_function: stimulation_max_intensity
      params:
        max_intensity: 0.5
      applies_to: ["stimulation"]
""",
        encoding="utf-8",
    )
    c = load_constitution(yaml)
    assert c.schema_version == 1.0
    assert len(c.policies) == 1
    assert c.policies[0].id == "TEST_POLICY"
    assert c.policies[0].severity == PolicySeverity.CRITICAL


def test_load_constitution_missing_file_returns_empty(tmp_path: Path):
    c = load_constitution(tmp_path / "nonexistent.yaml")
    assert c.policies == []


def test_load_constitution_invalid_yaml_returns_empty(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("not : valid : yaml : {{{", encoding="utf-8")
    c = load_constitution(bad)
    assert c.policies == []


def test_constitution_rejects_duplicate_ids():
    with pytest.raises(Exception):
        Constitution(
            schema_version=1.0,
            policies=[
                ConstitutionPolicy(
                    id="X",
                    severity=PolicySeverity.LOW,
                    text="a",
                    check_function="stimulation_max_intensity",
                ),
                ConstitutionPolicy(
                    id="X",
                    severity=PolicySeverity.LOW,
                    text="b",
                    check_function="stimulation_max_intensity",
                ),
            ],
        )


def test_constitution_policies_for_filter():
    c = Constitution(
        schema_version=1.0,
        policies=[
            ConstitutionPolicy(
                id="A",
                severity=PolicySeverity.LOW,
                text="a",
                check_function="stimulation_max_intensity",
                applies_to=["stimulation"],
            ),
            ConstitutionPolicy(
                id="B",
                severity=PolicySeverity.LOW,
                text="b",
                check_function="tool_deny_list",
                applies_to=["tool"],
            ),
        ],
    )
    assert [p.id for p in c.policies_for("stimulation")] == ["A"]
    assert [p.id for p in c.policies_for("tool")] == ["B"]


# --- Check functions -------------------------------------------------------


def test_check_stimulation_max_intensity_pass_and_fail():
    req = StimulationRequest(agent="A", channel="stress", intensity=0.3, tick=0)
    ctx = {"kind": "stimulation", "request": req, "params": {"max_intensity": 0.5}}
    passed, _ = check_stimulation_max_intensity(ctx)
    assert passed is True

    req2 = StimulationRequest(agent="A", channel="stress", intensity=0.7, tick=0)
    ctx2 = {"kind": "stimulation", "request": req2, "params": {"max_intensity": 0.5}}
    passed, msg = check_stimulation_max_intensity(ctx2)
    assert passed is False
    assert "0.700" in msg


def test_check_channel_whitelist():
    req = StimulationRequest(agent="A", channel="stress", intensity=0.1, tick=0)
    ctx = {
        "kind": "stimulation",
        "request": req,
        "params": {"allowed_channels": ["stress", "euphoria"]},
    }
    assert check_stimulation_channel_whitelist(ctx)[0] is True

    req2 = StimulationRequest(agent="A", channel="banned", intensity=0.1, tick=0)
    ctx2 = {
        "kind": "stimulation",
        "request": req2,
        "params": {"allowed_channels": ["stress", "euphoria"]},
    }
    assert check_stimulation_channel_whitelist(ctx2)[0] is False


def test_check_reflection_self_abuse():
    req = StimulationRequest(agent="Reflection", channel="stress", intensity=0.05, tick=0)
    ctx = {"kind": "stimulation", "request": req, "params": {"cap": 0.1}}
    assert check_reflection_self_abuse(ctx)[0] is True

    req2 = StimulationRequest(agent="Reflection", channel="stress", intensity=0.2, tick=0)
    ctx2 = {"kind": "stimulation", "request": req2, "params": {"cap": 0.1}}
    assert check_reflection_self_abuse(ctx2)[0] is False

    # Non-reflection agent — should pass regardless
    req3 = StimulationRequest(agent="Emotion", channel="stress", intensity=0.9, tick=0)
    ctx3 = {"kind": "stimulation", "request": req3, "params": {"cap": 0.1}}
    assert check_reflection_self_abuse(ctx3)[0] is True


def test_check_tool_deny_list():
    ctx = {"kind": "tool", "tool_name": "bad_tool", "params": {"deny": ["bad_tool"]}}
    assert check_tool_deny_list(ctx)[0] is False
    ctx2 = {"kind": "tool", "tool_name": "good_tool", "params": {"deny": ["bad_tool"]}}
    assert check_tool_deny_list(ctx2)[0] is True


def test_check_tool_args_no_secrets():
    # API-key pattern
    ctx = {"kind": "tool", "args": {"msg": "use this key: sk-abc1234567890123456789"}}
    passed, msg = check_tool_args_no_secrets(ctx)
    assert passed is False
    assert "API key" in msg or "key" in msg

    # SSN pattern
    ctx2 = {"kind": "tool", "args": {"msg": "SSN 123-45-6789"}}
    assert check_tool_args_no_secrets(ctx2)[0] is False

    # Safe args
    ctx3 = {"kind": "tool", "args": {"msg": "hello world"}}
    assert check_tool_args_no_secrets(ctx3)[0] is True


def test_check_cost_budget_exceeded():
    ctx_ok = {"system_state": {"cost_budget_exceeded": False}}
    assert check_cost_budget_exceeded(ctx_ok)[0] is True
    ctx_bad = {"system_state": {"cost_budget_exceeded": True}}
    assert check_cost_budget_exceeded(ctx_bad)[0] is False


def test_check_circuit_breaker_tripped():
    req = StimulationRequest(agent="A", channel="stress", intensity=0.1, tick=0)
    ctx = {
        "kind": "stimulation",
        "request": req,
        "system_state": {"tripped_channels": ["fatigue"]},
    }
    assert check_circuit_breaker_tripped(ctx)[0] is True
    ctx2 = {
        "kind": "stimulation",
        "request": req,
        "system_state": {"tripped_channels": ["stress"]},
    }
    assert check_circuit_breaker_tripped(ctx2)[0] is False


def test_register_check_adds_to_registry():
    def my_check(ctx):
        return False, "custom"

    register_check("my_custom", my_check)
    assert "my_custom" in CHECK_REGISTRY
    # Cleanup
    del CHECK_REGISTRY["my_custom"]


# --- ConstitutionalAuditor -------------------------------------------------


def _make_auditor(policies):
    return ConstitutionalAuditor(
        constitution=Constitution(schema_version=1.0, policies=policies)
    )


def test_empty_constitution_approves_everything():
    auditor = _make_auditor([])
    req = StimulationRequest(agent="A", channel="stress", intensity=0.5, tick=0)
    result = auditor.audit_stimulation(req, {})
    assert result.approved is True
    assert result.decision == GovernanceDecision.ALLOW
    assert result.risk_tier == RiskTier.LOW


def test_critical_violation_denies():
    policies = [
        ConstitutionPolicy(
            id="MAX_0_5",
            severity=PolicySeverity.CRITICAL,
            text="max 0.5",
            check_function="stimulation_max_intensity",
            params={"max_intensity": 0.5},
            applies_to=["stimulation"],
        )
    ]
    auditor = _make_auditor(policies)
    req = StimulationRequest(agent="A", channel="stress", intensity=0.8, tick=0)
    result = auditor.audit_stimulation(req, {})
    assert result.approved is False
    assert result.decision == GovernanceDecision.DENY_CONSTITUTION
    assert result.risk_tier == RiskTier.HIGH
    assert len(result.violations) == 1
    assert result.violations[0].policy_id == "MAX_0_5"


def test_medium_violation_warns_but_allows():
    policies = [
        ConstitutionPolicy(
            id="MAX_0_5",
            severity=PolicySeverity.MEDIUM,
            text="max 0.5",
            check_function="stimulation_max_intensity",
            params={"max_intensity": 0.5},
            applies_to=["stimulation"],
        )
    ]
    auditor = _make_auditor(policies)
    req = StimulationRequest(agent="A", channel="stress", intensity=0.8, tick=0)
    result = auditor.audit_stimulation(req, {})
    assert result.approved is True
    assert result.decision == GovernanceDecision.WARN_CONSTITUTION


def test_tool_audit():
    policies = [
        ConstitutionPolicy(
            id="DENY_BAD",
            severity=PolicySeverity.CRITICAL,
            text="deny bad",
            check_function="tool_deny_list",
            params={"deny": ["bad_tool"]},
            applies_to=["tool"],
        )
    ]
    auditor = _make_auditor(policies)
    result = auditor.audit_tool_call("bad_tool", {}, "Agent", {})
    assert result.approved is False
    assert result.decision == GovernanceDecision.DENY_CONSTITUTION

    result2 = auditor.audit_tool_call("good_tool", {}, "Agent", {})
    assert result2.approved is True


def test_missing_check_function_logs_but_does_not_violate():
    policies = [
        ConstitutionPolicy(
            id="MISSING",
            severity=PolicySeverity.CRITICAL,
            text="refers to a non-existent check",
            check_function="nonexistent_check",
            applies_to=["stimulation"],
        )
    ]
    auditor = _make_auditor(policies)
    req = StimulationRequest(agent="A", channel="stress", intensity=0.5, tick=0)
    result = auditor.audit_stimulation(req, {})
    # Missing check is skipped (logged), not treated as a violation.
    assert result.approved is True
    assert result.violations == []


def test_check_exception_becomes_violation_fail_closed():
    def exploding_check(ctx):
        raise RuntimeError("boom")

    policies = [
        ConstitutionPolicy(
            id="BOMB",
            severity=PolicySeverity.MEDIUM,  # original severity, should bump to HIGH
            text="will explode",
            check_function="bomb",
            applies_to=["stimulation"],
        )
    ]
    auditor = ConstitutionalAuditor(
        constitution=Constitution(schema_version=1.0, policies=policies),
        registry={"bomb": exploding_check},
    )
    req = StimulationRequest(agent="A", channel="stress", intensity=0.5, tick=0)
    result = auditor.audit_stimulation(req, {})
    # Exception → HIGH severity → DENY
    assert result.approved is False
    assert result.violations[0].severity == PolicySeverity.HIGH


def test_multiple_violations_picks_worst():
    policies = [
        ConstitutionPolicy(
            id="LOW_ONE",
            severity=PolicySeverity.LOW,
            text="low",
            check_function="stimulation_channel_whitelist",
            params={"allowed_channels": ["ok"]},
            applies_to=["stimulation"],
        ),
        ConstitutionPolicy(
            id="CRIT_ONE",
            severity=PolicySeverity.CRITICAL,
            text="critical",
            check_function="stimulation_max_intensity",
            params={"max_intensity": 0.1},
            applies_to=["stimulation"],
        ),
    ]
    auditor = _make_auditor(policies)
    req = StimulationRequest(agent="A", channel="banned", intensity=0.5, tick=0)
    result = auditor.audit_stimulation(req, {})
    assert result.approved is False
    assert result.risk_tier == RiskTier.HIGH
    assert len(result.violations) == 2


def test_to_dict_lists_policies():
    policies = [
        ConstitutionPolicy(
            id="X",
            severity=PolicySeverity.HIGH,
            text="hi",
            check_function="stimulation_max_intensity",
            applies_to=["stimulation"],
        )
    ]
    auditor = _make_auditor(policies)
    d = auditor.to_dict()
    assert d["type"] == "constitutional_auditor"
    assert d["policies"][0]["id"] == "X"
    assert d["policies"][0]["severity"] == "high"


def test_null_auditor_allows_all():
    a: IConstitutionalAuditor = NullConstitutionalAuditor()
    req = StimulationRequest(agent="A", channel="stress", intensity=999.0, tick=0)
    r = a.audit_stimulation(req, {})
    assert r.approved is True
    r2 = a.audit_tool_call("anything", {"code": "rm -rf /"}, "A", {})
    assert r2.approved is True


def test_auditor_satisfies_contract():
    a: IConstitutionalAuditor = ConstitutionalAuditor(constitution=Constitution())
    assert isinstance(a, IConstitutionalAuditor)


# --- Kernel integration ----------------------------------------------------


def test_kernel_denies_on_constitutional_violation():
    from src.governance.kernel import DeterministicGovernanceKernel, GovernancePolicy

    policies = [
        ConstitutionPolicy(
            id="NO_HIGH",
            severity=PolicySeverity.CRITICAL,
            text="max 0.2",
            check_function="stimulation_max_intensity",
            params={"max_intensity": 0.2},
            applies_to=["stimulation"],
        )
    ]
    auditor = _make_auditor(policies)
    kernel = DeterministicGovernanceKernel(
        policy=GovernancePolicy(per_tick_stimulus_cap=10.0, per_agent_stimulus_cap=10.0),
        auditor=auditor,
    )
    kernel.begin_tick(0)
    req = StimulationRequest(agent="Emotion", channel="stress", intensity=0.5, tick=0)
    decision = kernel.authorize(req)
    assert decision == GovernanceDecision.DENY_CONSTITUTION


def test_kernel_warns_and_continues_on_medium():
    from src.governance.kernel import DeterministicGovernanceKernel, GovernancePolicy

    policies = [
        ConstitutionPolicy(
            id="WARN_HIGH",
            severity=PolicySeverity.MEDIUM,
            text="warn on high intensity",
            check_function="stimulation_max_intensity",
            params={"max_intensity": 0.2},
            applies_to=["stimulation"],
        )
    ]
    auditor = _make_auditor(policies)
    kernel = DeterministicGovernanceKernel(
        policy=GovernancePolicy(per_tick_stimulus_cap=10.0, per_agent_stimulus_cap=10.0),
        auditor=auditor,
    )
    kernel.begin_tick(0)
    req = StimulationRequest(agent="Emotion", channel="stress", intensity=0.5, tick=0)
    decision = kernel.authorize(req)
    # WARN allows through → eventual ALLOW from downstream caps
    assert decision == GovernanceDecision.ALLOW


def test_kernel_state_provider_feeds_auditor():
    from src.governance.kernel import DeterministicGovernanceKernel, GovernancePolicy

    policies = [
        ConstitutionPolicy(
            id="CB_RESPECT",
            severity=PolicySeverity.CRITICAL,
            text="don't touch tripped channels",
            check_function="circuit_breaker_tripped",
            applies_to=["stimulation"],
        )
    ]
    auditor = _make_auditor(policies)
    kernel = DeterministicGovernanceKernel(
        policy=GovernancePolicy(per_tick_stimulus_cap=10.0, per_agent_stimulus_cap=10.0),
        auditor=auditor,
        state_provider=lambda: {"tripped_channels": ["stress"]},
    )
    kernel.begin_tick(0)
    req = StimulationRequest(agent="Emotion", channel="stress", intensity=0.1, tick=0)
    decision = kernel.authorize(req)
    assert decision == GovernanceDecision.DENY_CONSTITUTION
