from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from certificate_doctor.models import WEIGHTS, CheckResult, Issue


LOGIC_KEY = "CertificateDoctorLogic"


def _parse_logic_payload(raw: str | dict | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    s = str(raw).strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # MARKS:85,90,78|TOTAL:253|PCT:84.3|ROLL:NSU-2024-1042
        data: dict[str, Any] = {}
        m = re.search(r"MARKS:([0-9,\s]+)", s, re.I)
        if m:
            data["marks"] = [int(x) for x in re.findall(r"\d+", m.group(1))]
        m = re.search(r"TOTAL:(\d+)", s, re.I)
        if m:
            data["printed_total"] = int(m.group(1))
        m = re.search(r"PCT:([0-9.]+)", s, re.I)
        if m:
            data["printed_pct"] = float(m.group(1))
        m = re.search(r"ROLL:([A-Z0-9\-_/]+)", s, re.I)
        if m:
            data["roll"] = m.group(1)
        return data or None


def _strip_exif_comment(val: Any) -> str:
    if isinstance(val, bytes):
        val = val.decode("utf-8", errors="ignore")
    s = str(val)
    # EXIF UserComment often prefixed with ASCII\0\0\0
    if s.startswith("ASCII"):
        s = s[5:].lstrip("\x00")
    if s.startswith(f"{LOGIC_KEY}:"):
        s = s[len(LOGIC_KEY) + 1 :]
    return s.strip()


def extract_logic_from_image(path: str | Path | None, pil: Image.Image | None = None) -> dict[str, Any] | None:
    img = pil
    if img is None and path is not None:
        try:
            img = Image.open(path)
        except Exception:  # noqa: BLE001
            return None
    if img is None:
        return None
    info = img.info or {}
    if LOGIC_KEY in info:
        return _parse_logic_payload(info[LOGIC_KEY])
    # EXIF UserComment / ImageDescription
    try:
        exif = img.getexif()
        for tag in (0x9286, 0x010E, 37510, 270):  # UserComment / ImageDescription
            if tag in exif:
                val = _strip_exif_comment(exif.get(tag))
                parsed = _parse_logic_payload(val)
                if parsed:
                    return parsed
    except Exception:  # noqa: BLE001
        pass
    # Also scan info strings
    for key in ("exif", "comment", "UserComment", "ImageDescription"):
        if key in info:
            parsed = _parse_logic_payload(_strip_exif_comment(info[key]))
            if parsed:
                return parsed
    return None


def extract_logic_from_ocr(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    data: dict[str, Any] = {}
    # Subject marks patterns: "Mathematics 85" or "Math: 85"
    marks = []
    for m in re.finditer(
        r"(?:Mathematics|Math|Physics|Chemistry|English|Biology|History|Computer|Science)\s*[:\-]?\s*(\d{1,3})",
        text,
        re.I,
    ):
        marks.append(int(m.group(1)))
    if marks:
        data["marks"] = marks

    m = re.search(r"(?:Grand\s*)?Total\s*[:\-]?\s*(\d{2,4})", text, re.I)
    if m:
        data["printed_total"] = int(m.group(1))

    m = re.search(r"(?:Percentage|Percent|Pct)\s*[:\-]?\s*([0-9]{1,3}(?:\.[0-9]+)?)\s*%?", text, re.I)
    if m:
        data["printed_pct"] = float(m.group(1))

    m = re.search(r"(?:Roll|Reg(?:istration)?)\s*(?:No|Number|#)?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-_/]{4,})", text, re.I)
    if m:
        data["roll"] = m.group(1)

    # Compact machine line if present in OCR
    compact = _parse_logic_payload(text)
    if compact:
        data = {**compact, **data}
    return data or None


def _roll_ok(roll: str) -> bool:
    # Heuristic: letters+digits, length, not all same digit
    if len(roll) < 6 or len(roll) > 24:
        return False
    if not re.search(r"[A-Za-z]", roll):
        return False
    if not re.search(r"\d", roll):
        return False
    if re.fullmatch(r"(.)\1+", re.sub(r"[^A-Za-z0-9]", "", roll) or "x"):
        return False
    return True


def evaluate_logic(data: dict[str, Any]) -> tuple[float, list[Issue], dict[str, Any]]:
    score = 100.0
    issues: list[Issue] = []
    meta: dict[str, Any] = {"payload": data}

    marks = [int(m) for m in data.get("marks") or [] if str(m).isdigit() or isinstance(m, (int, float))]
    marks = [int(m) for m in marks if 0 <= int(m) <= 100]
    printed_total = data.get("printed_total")
    printed_pct = data.get("printed_pct")
    roll = data.get("roll")

    if marks and printed_total is not None:
        calc = sum(marks)
        meta["calculated_total"] = calc
        if abs(calc - int(printed_total)) >= 1:
            drop = 85.0
            score -= drop
            issues.append(
                Issue(
                    check="logic",
                    severity="high",
                    title="Mark total mismatch",
                    detail=f"Subject marks sum to {calc}, but printed total is {printed_total}.",
                    evidence=f"marks={marks}, printed_total={printed_total}",
                    impact=drop * WEIGHTS["logic"] / 100,
                )
            )

    if marks and printed_pct is not None:
        max_possible = data.get("max_total") or (len(marks) * 100)
        calc_pct = round(100.0 * sum(marks) / max(1, int(max_possible)), 1)
        meta["calculated_pct"] = calc_pct
        if abs(calc_pct - float(printed_pct)) >= 1.0:
            # If total already flagged, still add but smaller
            drop = 35.0 if not issues else 20.0
            score -= drop
            issues.append(
                Issue(
                    check="logic",
                    severity="high",
                    title="Percentage mismatch",
                    detail=f"Calculated percentage {calc_pct}% vs printed {printed_pct}%.",
                    evidence=f"calc_pct={calc_pct}, printed_pct={printed_pct}",
                    impact=drop * WEIGHTS["logic"] / 100,
                )
            )

    if roll:
        meta["roll"] = roll
        if not _roll_ok(str(roll)):
            drop = 20.0
            score -= drop
            issues.append(
                Issue(
                    check="logic",
                    severity="medium",
                    title="Suspicious roll-number format",
                    detail=f"Roll/registration '{roll}' fails basic format heuristics.",
                    evidence=f"roll={roll}",
                    impact=drop * WEIGHTS["logic"] / 100,
                )
            )

    if not marks and printed_total is None and printed_pct is None:
        # Nothing to check
        score = 80.0
        issues.append(
            Issue(
                check="logic",
                severity="low",
                title="No numeric mark fields found",
                detail="Could not extract subject marks / totals for arithmetic checks.",
                evidence="empty_payload",
                impact=3,
            )
        )

    return float(np.clip(score, 0, 100)), issues, meta


def check_logic(
    path: str | Path | None = None,
    *,
    pil: Image.Image | None = None,
    ocr_text: str = "",
    injected: dict[str, Any] | None = None,
) -> CheckResult:
    weight = WEIGHTS["logic"]
    data = injected or extract_logic_from_image(path, pil=pil)
    source = "embedded" if data else None
    if data is None:
        data = extract_logic_from_ocr(ocr_text)
        source = "ocr" if data else None

    if data is None:
        return CheckResult(
            name="logic",
            weight=weight,
            score=80.0,
            weighted_score=80.0 * weight / 100,
            summary="No mark totals found (OCR/embedded). Logic check soft-passed.",
            issues=[
                Issue(
                    check="logic",
                    severity="low",
                    title="Logic check skipped",
                    detail=(
                        "Install Tesseract for OCR-based mark arithmetic, or embed a "
                        f"{LOGIC_KEY} payload (demo samples include one)."
                    ),
                    evidence="no_payload",
                    impact=3,
                )
            ],
            meta={"source": None},
        )

    score, issues, meta = evaluate_logic(data)
    meta["source"] = source
    if score >= 85:
        summary = "Mark totals / percentage / roll heuristics look consistent."
    elif score >= 55:
        summary = "Some arithmetic or format inconsistencies."
    else:
        summary = "Logic failures — totals or percentage do not reconcile."

    return CheckResult(
        name="logic",
        weight=weight,
        score=score,
        weighted_score=score * weight / 100,
        summary=summary,
        issues=issues,
        meta=meta,
    )
