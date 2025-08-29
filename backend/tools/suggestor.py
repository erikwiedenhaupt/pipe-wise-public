# tools/suggestor.py
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from .base import BaseTool


# Lightweight local models (kept independent from core.models)
class Issue(BaseModel):
    id: str
    code: str
    message: str
    severity: str = "medium"
    location: Optional[str] = None


class Suggestion(BaseModel):
    id: str
    issue_id: Optional[str] = None
    action: str
    details: Optional[Dict[str, Any]] = None
    rationale: Optional[str] = None


ISSUE_TO_SUGGESTIONS = {
    "VEL_HIGH": lambda loc: Suggestion(
        id=f"S::{loc}::VEL_DOWN",
        issue_id=None,
        action="increase_diameter",
        details={"element_id": loc, "target_velocity_m_per_s": 1.5},
        rationale="Higher diameter reduces velocity for the same flow.",
    ),
    "P_LOW": lambda loc: Suggestion(
        id=f"S::{loc}::BOOST_P",
        issue_id=None,
        action="increase_source_pressure",
        details={"location": loc, "delta_bar": 0.5},
        rationale="Raising inlet pressure can lift downstream pressure.",
    ),
    "RE_LOW": lambda loc: Suggestion(
        id=f"S::{loc}::RE_UP",
        issue_id=None,
        action="adjust_fluid_or_velocity",
        details={"location": loc, "target_reynolds": 3000},
        rationale="Increase velocity/diameter or change fluid to raise Reynolds.",
    ),
}


class SuggestorTool(BaseTool):
    """
    Maps Issues -> actionable Suggestions with rationale.
    """

    name = "suggestor"
    description = "Generate fix suggestions based on detected issues."

    def run(self, issues: List[Any]) -> List[Suggestion]:
        # Coerce dictionaries to Issue models for robustness
        norm: List[Issue] = []
        for it in issues or []:
            if isinstance(it, Issue):
                norm.append(it)
            elif isinstance(it, dict):
                try:
                    norm.append(Issue(**it))
                except Exception:
                    continue

        suggestions: List[Suggestion] = []
        for issue in norm:
            loc = getattr(issue, "location", None) or "unknown"
            maker = ISSUE_TO_SUGGESTIONS.get(issue.code)
            if maker:
                sug = maker(loc)
                sug.issue_id = issue.id
                suggestions.append(sug)
            else:
                suggestions.append(
                    Suggestion(
                        id=f"S::{issue.id}",
                        issue_id=issue.id,
                        action="review_model",
                        details={"note": "No rule for this issue code."},
                        rationale="Manual engineering review recommended.",
                    )
                )
        return suggestions


def get_tool(**options: Any) -> SuggestorTool:
    return SuggestorTool().configure(**options)


__all__ = ["SuggestorTool", "get_tool"]