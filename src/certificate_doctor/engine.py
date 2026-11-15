from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from certificate_doctor.checks import (
    check_copy_move,
    check_ela,
    check_logic,
    check_metadata,
    check_text_font,
)
from certificate_doctor.heatmap import save_artifacts
from certificate_doctor.image_io import load_bgr, load_pil
from certificate_doctor.models import Diagnosis, Issue, verdict_for
from certificate_doctor.ocr_utils import run_ocr


def diagnose(
    path: str | Path,
    *,
    out_dir: str | Path | None = None,
    file_name: str | None = None,
    top_n: int = 10,
    injected_logic: dict[str, Any] | None = None,
) -> Diagnosis:
    path = Path(path)
    bgr, load_meta = load_bgr(path)
    pil = load_pil(path)
    return diagnose_array(
        bgr,
        pil=pil,
        path=path,
        out_dir=out_dir,
        file_name=file_name or path.name,
        top_n=top_n,
        injected_logic=injected_logic,
        load_meta=load_meta,
    )


def diagnose_array(
    bgr: np.ndarray,
    *,
    pil: Image.Image | None = None,
    path: str | Path | None = None,
    out_dir: str | Path | None = None,
    file_name: str = "upload",
    top_n: int = 10,
    injected_logic: dict[str, Any] | None = None,
    load_meta: dict[str, Any] | None = None,
) -> Diagnosis:
    if pil is None:
        from certificate_doctor.image_io import bgr_to_pil

        pil = bgr_to_pil(bgr)

    ocr_text, ocr_words, ocr_meta = run_ocr(bgr)

    ela_result, ela_gray, ela_heat = check_ela(bgr)
    text_result = check_text_font(
        bgr, ocr_text=ocr_text, ocr_words=ocr_words, ocr_meta=ocr_meta
    )
    meta_result = check_metadata(path, pil=pil)
    copy_result = check_copy_move(bgr)
    logic_result = check_logic(path, pil=pil, ocr_text=ocr_text, injected=injected_logic)

    checks = [ela_result, text_result, meta_result, copy_result, logic_result]
    overall = float(sum(c.weighted_score for c in checks))

    all_issues: list[Issue] = []
    all_regions = []
    for c in checks:
        all_issues.extend(c.issues)
        all_regions.extend(c.regions)

    # Multi-signal integrity penalty: independent high-severity flags compound risk
    high_checks = {i.check for i in all_issues if i.severity == "high"}
    integrity_penalty = 0.0
    if len(high_checks) >= 3:
        integrity_penalty = 40.0
    elif len(high_checks) >= 2:
        integrity_penalty = 32.0
    if integrity_penalty:
        overall = max(0.0, overall - integrity_penalty)
        all_issues.append(
            Issue(
                check="integrity",
                severity="high",
                title="Multiple independent forensic flags",
                detail=(
                    f"{len(high_checks)} checks raised high-severity findings "
                    f"({', '.join(sorted(high_checks))}) — compound risk of tampering."
                ),
                evidence=f"high_checks={sorted(high_checks)}, penalty={integrity_penalty}",
                impact=integrity_penalty,
            )
        )

    top_issues = sorted(all_issues, key=lambda i: (-i.impact, i.severity != "high"))[:top_n]

    # Persist heatmap / overlay
    if out_dir is None:
        out_dir = Path(tempfile.mkdtemp(prefix="cert-doctor-"))
    else:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

    stem = Path(file_name).stem
    heat_path, overlay_path = save_artifacts(
        bgr, ela_gray, ela_heat, all_regions, out_dir, stem
    )

    return Diagnosis(
        file_name=file_name,
        overall_score=overall,
        verdict=verdict_for(overall),
        checks=checks,
        top_issues=top_issues,
        heatmap_path=str(heat_path),
        overlay_path=str(overlay_path),
        width=int(bgr.shape[1]),
        height=int(bgr.shape[0]),
        meta={
            "load": load_meta or {},
            "ocr": ocr_meta,
            "artifacts_dir": str(out_dir),
            "scope_note": (
                "Screening tool only — cannot verify against university databases; "
                "not court-proof; heavy compression can false-positive; "
                "professional forgeries may slip through."
            ),
        },
    )
