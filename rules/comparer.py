"""Per-network rule comparison and safe merge/replace planning."""
from __future__ import annotations

from dataclasses import dataclass, field

from rules.models import ChangeKind, RuleSet, VpnExclusionRule


@dataclass(slots=True)
class Change:
    kind: ChangeKind
    rule: VpnExclusionRule
    detail: str = ""


@dataclass(slots=True)
class Comparison:
    changes: list[Change] = field(default_factory=list)
    final: RuleSet = field(default_factory=RuleSet)

    def count(self, kind: ChangeKind) -> int:
        return sum(item.kind == kind for item in self.changes)

    @property
    def has_blockers(self) -> bool:
        return any(
            item.kind in {ChangeKind.INVALID, ChangeKind.DUPLICATE}
            for item in self.changes
        )


def compare(existing: RuleSet, proposed: RuleSet) -> Comparison:
    changes: list[Change] = []
    existing_by_fp = {item.fingerprint(): item for item in existing.rules}
    proposed_seen: set[str] = set()
    removed: set[str] = set()
    additions: list[VpnExclusionRule] = []

    for rule in proposed.rules:
        try:
            fingerprint = rule.fingerprint()
        except ValueError as exc:
            changes.append(Change(ChangeKind.INVALID, rule, str(exc)))
            continue
        if fingerprint in proposed_seen:
            changes.append(Change(ChangeKind.DUPLICATE, rule, "duplicate in import"))
            continue
        proposed_seen.add(fingerprint)
        if rule.action == "remove":
            if fingerprint in existing_by_fp:
                removed.add(fingerprint)
                changes.append(Change(ChangeKind.REMOVED, existing_by_fp[fingerprint]))
            else:
                changes.append(
                    Change(ChangeKind.UNCHANGED, rule, "remove target not present")
                )
        elif fingerprint in existing_by_fp:
            changes.append(
                Change(ChangeKind.UNCHANGED, rule, "identical rule already exists; skipped")
            )
        else:
            additions.append(rule)
            changes.append(Change(ChangeKind.NEW, rule))

    if proposed.mode == "replace":
        keep = [r for r in proposed.rules if r.action != "remove"]
        keep_fps = {r.fingerprint() for r in keep}
        for rule in existing.rules:
            if rule.fingerprint() not in keep_fps:
                changes.append(Change(ChangeKind.REMOVED, rule, "replace mode"))
        final_rules = keep
    else:
        final_rules = [
            item for item in existing.rules if item.fingerprint() not in removed
        ] + additions
    for index, rule in enumerate(final_rules):
        rule.order = index
    return Comparison(changes=changes, final=RuleSet(rules=final_rules, mode=proposed.mode))
