from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


WEIGHTS = {
    "ela": 30,
    "text_font": 25,
    "metadata": 15,
    "copy_move": 15,
    "logic": 15,
}

CHECK_LABELS = {
    "ela": "Error Level Analysis",
    "text_font": "Text / font consistency",
    "metadata": "Metadata",
    "copy_move": "Copy-move detection",
    "logic": "Logic checks",
}


@dataclass
class Region:
    x: int
    y: int
    w: int
    h: int
    label: str = ""
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Issue:
    check: str
    severity: str  # high | medium | low
    title: str
    detail: str
    evidence: str = ""
    impact: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CheckResult:
    name: str
    weight: int
    score: float
    weighted_score: float
    summary: str
    issues: list[Issue] = field(default_factory=list)
    regions: list[Region] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": CHECK_LABELS.get(self.name, self.name),
            "weight": self.weight,
            "score": round(self.score, 1),
            "weighted_score": round(self.weighted_score, 1),
            "summary": self.summary,
            "issues": [i.to_dict() for i in self.issues],
            "regions": [r.to_dict() for r in self.regions],
            "meta": self.meta,
        }


@dataclass
class Diagnosis:
    file_name: str
    overall_score: float
    verdict: str
    checks: list[CheckResult]
    top_issues: list[Issue]
    heatmap_path: str | None = None
    overlay_path: str | None = None
    width: int = 0
    height: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "product": "Certificate Doctor",
            "version": "0.1.0",
            "file_name": self.file_name,
            "overall_score": round(self.overall_score, 1),
            "verdict": self.verdict,
            "width": self.width,
            "height": self.height,
            "heatmap_path": self.heatmap_path,
            "overlay_path": self.overlay_path,
            "checks": [c.to_dict() for c in self.checks],
            "top_issues": [i.to_dict() for i in self.top_issues],
            "meta": self.meta,
            "scope": {
                "cannot_verify_university_databases": True,
                "not_court_proof": True,
                "heavy_compression_false_positives": True,
                "professional_forgeries_may_slip": True,
            },
        }


def verdict_for(score: float) -> str:
    if score >= 75:
        return "Likely Genuine"
    if score >= 50:
        return "Needs Review"
    return "Likely Tampered"
