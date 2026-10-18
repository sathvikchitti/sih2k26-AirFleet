"""Maintenance knowledge layer (spec section 17).

This is the module that lets the ML model stay ignorant of our parts
catalogue. The ML provider reports a degraded *subsystem* and a predicted
*issue*; this layer maps that to a maintenance *action* and a set of
*candidate components*.

    High-pressure subsystem degradation
        -> Inspect / replace high-pressure turbine module
        -> [HP-204]

The mapping is plain configuration data, so it can later be loaded from a
public maintenance corpus (MaintNet etc.) without touching any calling code.
There is deliberately no LLM/RAG component here.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .enums import Priority, RiskLevel


@dataclass(frozen=True)
class MaintenanceRule:
    """One row of the knowledge base."""

    issue: str
    """Human-readable predicted issue, as reported by the ML provider."""

    subsystem: str
    """Stable machine key for the degraded subsystem."""

    maintenance_action: str
    """What should be done, in maintenance language."""

    candidate_components: tuple[str, ...]
    """Parts that could satisfy this action, best first.

    The ML layer does NOT choose among these — the recommendation engine does,
    once it knows what stock actually exists.
    """

    default_priority: Priority = Priority.MEDIUM
    estimated_repair_hours: float = 4.0

    def matches(self, subsystem: str | None, issue: str | None) -> bool:
        """True when this rule applies to a prediction.

        Matching is deliberately loose: exact subsystem first, then a
        normalised text match on the issue, so a real model is not required to
        emit our vocabulary verbatim.
        """
        if subsystem and _normalise(subsystem) == _normalise(self.subsystem):
            return True
        if issue:
            return _normalise(issue) == _normalise(self.issue)
        return False


def _normalise(value: str | None) -> str:
    return " ".join(str(value or "").replace("_", " ").replace("-", " ").lower().split())


# --------------------------------------------------------------------------
# Configuration. Swap this table for a database/file-backed version later;
# every consumer goes through `resolve()`.
# --------------------------------------------------------------------------
MAINTENANCE_RULES: tuple[MaintenanceRule, ...] = (
    MaintenanceRule(
        issue="High-pressure subsystem degradation",
        subsystem="HIGH_PRESSURE",
        maintenance_action="Inspect / replace high-pressure turbine module",
        candidate_components=("HP-204",),
        default_priority=Priority.CRITICAL,
        estimated_repair_hours=6.0,
    ),
    MaintenanceRule(
        issue="Fuel system pressure loss",
        subsystem="FUEL_SYSTEM",
        maintenance_action="Inspect / replace fuel pump assembly",
        candidate_components=("FP-102",),
        default_priority=Priority.MEDIUM,
        estimated_repair_hours=4.0,
    ),
    MaintenanceRule(
        issue="Oil cooling capacity degradation",
        subsystem="COOLING",
        maintenance_action="Inspect / replace oil cooler / heat exchanger",
        candidate_components=("OE-310",),
        default_priority=Priority.MEDIUM,
        estimated_repair_hours=5.0,
    ),
    MaintenanceRule(
        issue="Avionics signal degradation",
        subsystem="AVIONICS",
        maintenance_action="Inspect / replace avionics line-replaceable unit",
        candidate_components=("AV-077",),
        default_priority=Priority.LOW,
        estimated_repair_hours=3.0,
    ),
)

_RULES_BY_SUBSYSTEM = {_normalise(r.subsystem): r for r in MAINTENANCE_RULES}

# C-MAPSS FD001 predicts engine RUL, not a subsystem or a component. This
# configurable mapping is a demo assumption only; it must never be presented
# as a model diagnosis. Keep the default explicit and limited to the ten
# mapped FD001 example engines. Deployments may provide a JSON object such as
# {"1":"HP-204","2":"OE-310"} via FD001_ENGINE_PART_MAPPING.
# This alternation is a demo-only category mapping, not a diagnosis: odd
# example engine IDs use the HP-204 category and even IDs use OE-310.
FD001_ENGINE_PART_MAPPING: dict[int, str] = {
    engine_id: "HP-204" if engine_id % 2 else "OE-310"
    for engine_id in range(1, 11)
}


def fd001_engine_part_mapping() -> tuple[dict[int, str], str]:
    """Return a validated demo-only engine-to-engine-part mapping.

    The optional environment override is data, never executable code. Only
    catalogued Engine-category parts and positive integer engine IDs are
    accepted.
    """
    raw = os.getenv("FD001_ENGINE_PART_MAPPING")
    if raw is None or not raw.strip():
        return dict(FD001_ENGINE_PART_MAPPING), "built_in_demo_assumption"
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("FD001_ENGINE_PART_MAPPING must be a JSON object") from exc
    if not isinstance(value, dict) or not value:
        raise ValueError("FD001_ENGINE_PART_MAPPING must be a non-empty JSON object")

    # Import lazily to keep the domain mapping independent during module load.
    from ..data import PARTS
    engine_parts = {
        str(row["part_number"]).upper()
        for row in PARTS if str(row.get("category", "")).casefold() == "engine"
    }
    mapping: dict[int, str] = {}
    for raw_id, raw_part in value.items():
        try:
            engine_id = int(raw_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("FD001 mapping keys must be positive engine IDs") from exc
        if engine_id < 1 or str(engine_id) != str(raw_id):
            raise ValueError("FD001 mapping keys must be canonical positive engine IDs")
        if not isinstance(raw_part, str):
            raise ValueError("FD001 mapping values must be component part numbers")
        part_number = raw_part.strip().upper()
        if part_number not in engine_parts:
            raise ValueError(f"FD001 mapping component {part_number!r} is not an engine-category part")
        mapping[engine_id] = part_number
    return mapping, "environment_configured_demo_assumption"


@dataclass
class KnowledgeResolution:
    """The outcome of mapping a prediction onto maintenance knowledge."""

    matched: bool
    rule: MaintenanceRule | None
    maintenance_action: str | None
    candidate_components: tuple[str, ...] = ()
    default_priority: Priority | None = None
    estimated_repair_hours: float | None = None

    @property
    def reason(self) -> str | None:
        if self.matched and self.rule:
            return f"Matched maintenance rule for subsystem '{self.rule.subsystem}'"
        return (
            "No maintenance rule matched this prediction — a manual work order "
            "is required because the knowledge layer cannot infer an action."
        )


def resolve(subsystem: str | None, issue: str | None) -> KnowledgeResolution:
    """Map an ML prediction onto a maintenance action and candidate parts.

    When nothing matches we return `matched=False` rather than guessing. A
    prediction with no known remediation must not silently become a work order
    for an arbitrary part.
    """
    if subsystem:
        rule = _RULES_BY_SUBSYSTEM.get(_normalise(subsystem))
        if rule:
            return KnowledgeResolution(
                matched=True,
                rule=rule,
                maintenance_action=rule.maintenance_action,
                candidate_components=rule.candidate_components,
                default_priority=rule.default_priority,
                estimated_repair_hours=rule.estimated_repair_hours,
            )

    for rule in MAINTENANCE_RULES:
        if rule.matches(subsystem, issue):
            return KnowledgeResolution(
                matched=True,
                rule=rule,
                maintenance_action=rule.maintenance_action,
                candidate_components=rule.candidate_components,
                default_priority=rule.default_priority,
                estimated_repair_hours=rule.estimated_repair_hours,
            )

    return KnowledgeResolution(matched=False, rule=None, maintenance_action=None)


def rules_as_dicts() -> list[dict]:
    """Config view of the knowledge base, for the API."""
    return [
        {
            "issue": r.issue,
            "subsystem": r.subsystem,
            "maintenance_action": r.maintenance_action,
            "candidate_components": list(r.candidate_components),
            "default_priority": str(r.default_priority),
            "estimated_repair_hours": r.estimated_repair_hours,
        }
        for r in MAINTENANCE_RULES
    ]


def priority_for_risk(risk_level: str | None) -> Priority:
    """Fallback priority when no rule supplies one."""
    return {
        RiskLevel.CRITICAL: Priority.CRITICAL,
        RiskLevel.HIGH: Priority.HIGH,
        RiskLevel.MEDIUM: Priority.MEDIUM,
    }.get(risk_level, Priority.LOW)
