"""Matching a bulk zip's entries to students by the register number at the start of each entry's
name or top-level folder — the piece `services.class_assignments.bulk_preview`/`bulk_commit` build
on to turn one zip for a whole class into a submission per student.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

_LEAD = re.compile(r"^\s*0*(\d+)(?=[\s_\-./]|$)")


@dataclass
class BulkPlan:
    matched: Dict[int, List[str]] = field(default_factory=dict)
    ambiguous: List[str] = field(default_factory=list)
    unmatched: List[str] = field(default_factory=list)


def _reg_of(name: str):
    head = Path(name).parts[0] if len(Path(name).parts) > 1 else Path(name).stem
    m = _LEAD.match(head)
    return int(m.group(1)) if m else None


def match_entries(names: List[str], students: List[dict]) -> BulkPlan:
    by_reg: Dict[int, List[dict]] = {}
    for s in students:
        by_reg.setdefault(int(s["reg_no"]), []).append(s)
    plan = BulkPlan()
    for n in names:
        reg = _reg_of(n)
        hits = by_reg.get(reg, []) if reg is not None else []
        if len(hits) == 1:
            plan.matched.setdefault(hits[0]["id"], []).append(n)
        elif len(hits) > 1:
            plan.ambiguous.append(n)
        else:
            plan.unmatched.append(n)
    return plan
