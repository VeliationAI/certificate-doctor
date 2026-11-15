from pathlib import Path

from certificate_doctor.engine import diagnose
from certificate_doctor.models import verdict_for

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def _sample(name: str) -> Path:
    jpg = SAMPLES / f"{name}_marksheet.jpg"
    if jpg.exists():
        return jpg
    return SAMPLES / f"{name}_marksheet.png"


def test_genuine_scores_high():
    result = diagnose(_sample("genuine"))
    assert result.overall_score >= 85
    assert result.verdict == "Likely Genuine"
    ela = next(c for c in result.checks if c.name == "ela")
    logic = next(c for c in result.checks if c.name == "logic")
    assert ela.score >= 80
    assert logic.score >= 85


def test_tampered_scores_low():
    result = diagnose(_sample("tampered"))
    assert result.overall_score <= 45
    assert result.verdict == "Likely Tampered"
    logic = next(c for c in result.checks if c.name == "logic")
    meta = next(c for c in result.checks if c.name == "metadata")
    assert logic.score < 50
    assert meta.score < 50
    flagged = {i.check for i in result.top_issues}
    assert "logic" in flagged
    assert "metadata" in flagged or "integrity" in flagged
    assert any(i.check in {"ela", "logic", "metadata", "copy_move", "integrity"} for i in result.top_issues)


def test_before_after_story():
    genuine = diagnose(_sample("genuine"))
    tampered = diagnose(_sample("tampered"))
    assert genuine.overall_score - tampered.overall_score >= 40
    assert genuine.overall_score >= 85
    assert tampered.overall_score <= 45


def test_verdict_thresholds():
    assert verdict_for(90) == "Likely Genuine"
    assert verdict_for(60) == "Needs Review"
    assert verdict_for(30) == "Likely Tampered"


def test_overlay_artifact_written(tmp_path):
    result = diagnose(_sample("tampered"), out_dir=tmp_path)
    assert result.overlay_path
    assert Path(result.overlay_path).exists()
    assert Path(result.heatmap_path).exists()
