from __future__ import annotations

import statistics

import numpy as np

from certificate_doctor.models import WEIGHTS, CheckResult, Issue, Region
from certificate_doctor.ocr_utils import OcrWord, run_ocr


def _baseline_anomalies(words: list[OcrWord]) -> list[Issue]:
    issues: list[Issue] = []
    if len(words) < 8:
        return issues

    # Group by approximate line (y)
    lines: dict[int, list[OcrWord]] = {}
    for w in words:
        key = int(round(w.y / 18) * 18)
        lines.setdefault(key, []).append(w)

    height_outliers = 0
    spacing_flags = 0
    for line in lines.values():
        if len(line) < 3:
            continue
        heights = [w.h for w in line if w.h > 4]
        if len(heights) >= 3:
            med = statistics.median(heights)
            if med > 0:
                height_outliers += sum(1 for h in heights if abs(h - med) / med > 0.45)

        ordered = sorted(line, key=lambda w: w.x)
        gaps = []
        for a, b in zip(ordered, ordered[1:]):
            gap = b.x - (a.x + a.w)
            if 0 <= gap < 120:
                gaps.append(gap)
        if len(gaps) >= 3:
            med_g = statistics.median(gaps)
            if med_g > 1:
                spacing_flags += sum(1 for g in gaps if abs(g - med_g) / med_g > 1.8)

    if height_outliers >= 3:
        issues.append(
            Issue(
                check="text_font",
                severity="medium",
                title="Inconsistent glyph heights",
                detail=f"OCR found {height_outliers} words with height outliers vs line median — possible pasted text.",
                evidence=f"height_outliers={height_outliers}",
                impact=8,
            )
        )
    if spacing_flags >= 4:
        issues.append(
            Issue(
                check="text_font",
                severity="medium",
                title="Irregular word spacing",
                detail=f"Spacing anomalies on {spacing_flags} gaps — baseline/kerning may be inconsistent.",
                evidence=f"spacing_flags={spacing_flags}",
                impact=6,
            )
        )
    return issues


def _edge_density_heuristic(bgr: np.ndarray) -> tuple[float, list[Issue], list[Region]]:
    """When OCR is unavailable, use local edge-density variance as a soft signal."""
    import cv2

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 80, 160)
    h, w = edges.shape
    bh, bw = max(24, h // 24), max(24, w // 18)
    densities = []
    regions: list[Region] = []
    for y in range(0, h - bh, bh):
        for x in range(0, w - bw, bw):
            patch = edges[y : y + bh, x : x + bw]
            dens = float(np.mean(patch > 0))
            densities.append(dens)
            if dens > 0.22:
                regions.append(Region(x=x, y=y, w=bw, h=bh, label="dense", score=dens))

    if not densities:
        return 92.0, [], []

    mean_d = float(np.mean(densities))
    std_d = float(np.std(densities))
    score = 92.0
    issues: list[Issue] = []
    # Soft heuristic only — do not tank scores without OCR
    if std_d > 0.09 and mean_d > 0.04:
        score = 82.0
        issues.append(
            Issue(
                check="text_font",
                severity="low",
                title="Uneven edge density (OCR offline)",
                detail=(
                    "Tesseract is not available. Soft edge-density variance is elevated; "
                    "install Tesseract for stronger font/baseline checks."
                ),
                evidence=f"edge_std={std_d:.3f}",
                impact=3,
            )
        )
    regions = sorted(regions, key=lambda r: -r.score)[:4]
    return score, issues, regions


def check_text_font(
    bgr: np.ndarray,
    *,
    ocr_text: str | None = None,
    ocr_words: list[OcrWord] | None = None,
    ocr_meta: dict | None = None,
) -> CheckResult:
    weight = WEIGHTS["text_font"]
    issues: list[Issue] = []
    regions: list[Region] = []
    meta: dict = {}

    if ocr_meta is None and (ocr_words is None or ocr_text is None):
        text, words, ocr_meta = run_ocr(bgr)
    elif ocr_meta is None:
        text, words = ocr_text or "", ocr_words or []
        ocr_meta = {"available": True, "engine": "injected"}
    else:
        text, words = ocr_text or "", ocr_words or []

    meta["ocr"] = ocr_meta

    if not ocr_meta.get("available"):
        score, soft_issues, soft_regions = _edge_density_heuristic(bgr)
        issues.extend(soft_issues)
        regions.extend(soft_regions)
        summary = "OCR unavailable — soft edge heuristic only (install Tesseract for full check)."
        score = float(np.clip(score, 0, 100))
        return CheckResult(
            name="text_font",
            weight=weight,
            score=score,
            weighted_score=score * weight / 100,
            summary=summary,
            issues=issues,
            regions=regions,
            meta=meta,
        )

    score = 100.0
    issues.extend(_baseline_anomalies(words))
    for iss in issues:
        score -= min(20, iss.impact * 2)

    # Very low mean confidence can indicate mixed fonts / noise
    confs = [w.conf for w in words if w.conf >= 0]
    if confs:
        mean_conf = float(np.mean(confs))
        meta["mean_ocr_conf"] = round(mean_conf, 1)
        if mean_conf < 55 and len(confs) > 10:
            drop = min(25, (55 - mean_conf) * 0.8)
            score -= drop
            issues.append(
                Issue(
                    check="text_font",
                    severity="medium",
                    title="Low OCR confidence",
                    detail=f"Mean OCR confidence {mean_conf:.0f}% — mixed fonts or local noise often cause this.",
                    evidence=f"mean_conf={mean_conf:.1f}",
                    impact=drop * weight / 100,
                )
            )

    # Mark height outliers as regions
    if words:
        heights = [w.h for w in words]
        med = float(np.median(heights))
        for w in words:
            if med > 0 and abs(w.h - med) / med > 0.55 and w.h > 8:
                regions.append(Region(x=w.x, y=w.y, w=w.w, h=w.h, label=w.text[:12], score=abs(w.h - med)))

    regions = sorted(regions, key=lambda r: -r.score)[:8]
    score = float(np.clip(score, 0, 100))
    if score >= 85:
        summary = f"OCR text/font heuristics look consistent ({len(words)} words)."
    elif score >= 55:
        summary = "Some font/baseline irregularities detected."
    else:
        summary = "Strong text/font inconsistencies — possible pasted glyphs."

    meta["word_count"] = len(words)
    meta["text_preview"] = (text or "")[:240]
    return CheckResult(
        name="text_font",
        weight=weight,
        score=score,
        weighted_score=score * weight / 100,
        summary=summary,
        issues=issues,
        regions=regions,
        meta=meta,
    )
