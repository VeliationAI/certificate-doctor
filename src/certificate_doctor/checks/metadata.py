from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ExifTags

from certificate_doctor.models import WEIGHTS, CheckResult, Issue


EDITOR_MARKERS = (
    "photoshop",
    "adobe photoshop",
    "gimp",
    "affinity",
    "paint.net",
    "pixelmator",
    "corel",
    "snapseed",
    "lightroom",
)


def _exif_dict(path: str | Path | None, pil: Image.Image | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {}
    img = pil
    if img is None and path is not None:
        try:
            img = Image.open(path)
        except Exception:  # noqa: BLE001
            return data
    if img is None:
        return data
    try:
        raw = img.getexif()
        if not raw:
            # legacy
            raw = getattr(img, "_getexif", lambda: None)() or {}
        for tag_id, value in dict(raw).items():
            name = ExifTags.TAGS.get(tag_id, str(tag_id))
            if isinstance(value, bytes):
                try:
                    value = value.decode("utf-8", errors="ignore")
                except Exception:  # noqa: BLE001
                    value = repr(value)[:80]
            data[name] = value
    except Exception:  # noqa: BLE001
        pass

    # PNG text / info
    for k, v in (img.info or {}).items():
        if k not in data and isinstance(v, (str, int, float)):
            data[str(k)] = v
    return data


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    s = str(value).strip()
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    return None


def check_metadata(
    path: str | Path | None = None,
    *,
    pil: Image.Image | None = None,
    extra: dict[str, Any] | None = None,
) -> CheckResult:
    weight = WEIGHTS["metadata"]
    exif = _exif_dict(path, pil=pil)
    if extra:
        for k, v in extra.items():
            exif.setdefault(k, v)

    score = 100.0
    issues: list[Issue] = []
    software = str(exif.get("Software") or exif.get("software") or exif.get("CreatorTool") or "")
    soft_l = software.lower()

    if any(m in soft_l for m in EDITOR_MARKERS):
        drop = 100.0
        score -= drop
        issues.append(
            Issue(
                check="metadata",
                severity="high",
                title="Editor software tag present",
                detail=f"File metadata reports Software/CreatorTool as '{software}'. Common in edited exports.",
                evidence=f"Software={software}",
                impact=drop * weight / 100,
            )
        )

    dt = _parse_dt(exif.get("DateTime") or exif.get("DateTimeDigitized"))
    orig = _parse_dt(exif.get("DateTimeOriginal"))
    if dt and orig and abs((dt - orig).total_seconds()) > 86400 * 3:
        drop = 25.0
        score -= drop
        issues.append(
            Issue(
                check="metadata",
                severity="medium",
                title="Modification vs original date mismatch",
                detail=(
                    f"DateTime ({dt.date()}) differs from DateTimeOriginal ({orig.date()}) "
                    "by more than 3 days — possible re-export after edit."
                ),
                evidence=f"DateTime={dt}, DateTimeOriginal={orig}",
                impact=drop * weight / 100,
            )
        )

    # Heuristic: issue-date style keys from our synthetic payload
    issue_raw = exif.get("CertificateIssueDate") or exif.get("IssueDate")
    issue_dt = _parse_dt(issue_raw)
    if issue_dt and dt and dt < issue_dt:
        drop = 20.0
        score -= drop
        issues.append(
            Issue(
                check="metadata",
                severity="medium",
                title="File date before stated issue date",
                detail="Embedded file timestamp predates the certificate issue date heuristic.",
                evidence=f"file={dt.date()}, issue={issue_dt.date()}",
                impact=drop * weight / 100,
            )
        )

    if not software and not dt and not orig and len(exif) < 2:
        # Stripped metadata is common for screenshots / exports — mild caution, not a fail
        score = min(score, 92)
        issues.append(
            Issue(
                check="metadata",
                severity="low",
                title="Sparse metadata",
                detail="Little or no EXIF/history found. Common for scans and re-exports; not proof of forgery.",
                evidence=f"keys={len(exif)}",
                impact=1.2,
            )
        )

    score = float(np.clip(score, 0, 100))
    if score >= 85:
        summary = "Metadata looks clean (no strong editor fingerprints)."
    elif score >= 55:
        summary = "Metadata raises some review flags."
    else:
        summary = "Strong editor / history signals in metadata."

    # Serialize EXIF for report (truncate)
    preview = {k: str(v)[:120] for k, v in list(exif.items())[:24]}
    return CheckResult(
        name="metadata",
        weight=weight,
        score=score,
        weighted_score=score * weight / 100,
        summary=summary,
        issues=issues,
        meta={"exif_preview": preview, "software": software},
    )
