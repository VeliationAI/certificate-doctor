from __future__ import annotations

import cv2
import numpy as np

from certificate_doctor.heatmap import ela_maps
from certificate_doctor.models import WEIGHTS, CheckResult, Issue, Region


def check_ela(bgr: np.ndarray, *, quality: int = 90) -> tuple[CheckResult, np.ndarray, np.ndarray]:
    """Error Level Analysis — edited regions light up after re-save/compare."""
    weight = WEIGHTS["ela"]
    gray, heat = ela_maps(bgr, quality=quality, scale=18.0)
    gray_lo, _ = ela_maps(bgr, quality=75, scale=18.0)

    blur = cv2.GaussianBlur(gray, (5, 5), 0).astype(np.float32)
    blur_lo = cv2.GaussianBlur(gray_lo, (5, 5), 0).astype(np.float32)

    src_gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    sobelx = cv2.Sobel(src_gray, cv2.CV_32F, 1, 0, ksize=3)
    sobely = cv2.Sobel(src_gray, cv2.CV_32F, 0, 1, ksize=3)
    edge_mag = cv2.magnitude(sobelx, sobely)
    edge_n = np.clip(edge_mag / (float(np.percentile(edge_mag, 99)) + 1e-6), 0, 1)

    anom = cv2.GaussianBlur(blur * (1.0 - 0.85 * edge_n), (5, 5), 0)
    anom_lo = cv2.GaussianBlur(blur_lo * (1.0 - 0.75 * edge_n), (5, 5), 0)
    diff = np.clip(anom_lo - anom * 1.1, 0, 255)

    mean_v = float(np.mean(anom))
    p90 = float(np.percentile(anom, 90))
    p95 = float(np.percentile(anom, 95))
    p99 = float(np.percentile(anom, 99))
    p999 = float(np.percentile(anom, 99.9))
    tail = p99 - p90

    def _regions_from(map_img: np.ndarray, threshold: float) -> tuple[list[Region], float]:
        mask = (map_img >= threshold).astype(np.uint8) * 255
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        regs: list[Region] = []
        area_sum = 0
        area_total = bgr.shape[0] * bgr.shape[1]
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            area = w * h
            if area < max(280, area_total * 0.0008) or area > area_total * 0.22:
                continue
            strength = float(np.mean(map_img[y : y + h, x : x + w]))
            if strength < threshold:
                continue
            area_sum += area
            regs.append(Region(x=x, y=y, w=w, h=h, label=f"ELA {strength:.0f}", score=strength))
        regs = sorted(regs, key=lambda r: -r.score)[:8]
        return regs, area_sum / max(1, area_total)

    thr = max(p95 + 8.0, mean_v + 4.0 * float(np.std(anom)), 32.0)
    thr_diff = max(
        float(np.percentile(diff, 98)),
        float(np.mean(diff)) + 5.0 * float(np.std(diff)),
        20.0,
    )

    regions, hotspot_frac = _regions_from(anom, thr)
    regions_d, frac_d = _regions_from(diff, thr_diff)
    used_diff = False
    if frac_d >= hotspot_frac and frac_d > 0.0015:
        regions, hotspot_frac = regions_d, frac_d
        used_diff = True

    score = 100.0
    issues: list[Issue] = []

    if hotspot_frac > 0.002 and regions:
        drop = min(80, 28 + hotspot_frac * 1700 + len(regions) * 6)
        score -= drop
        issues.append(
            Issue(
                check="ela",
                severity="high" if hotspot_frac > 0.008 or len(regions) >= 2 else "medium",
                title="Localized ELA anomalies",
                detail=(
                    f"Found {len(regions)} suspicious region(s) covering "
                    f"{hotspot_frac * 100:.2f}% of the page after JPEG re-encode"
                    f"{' (multi-quality differential)' if used_diff else ''}."
                ),
                evidence=f"regions={len(regions)}, frac={hotspot_frac:.4f}, tail={tail:.1f}",
                impact=drop * weight / 100,
            )
        )
    elif tail > 50:
        drop = min(30, (tail - 50) * 1.3)
        score -= drop
        issues.append(
            Issue(
                check="ela",
                severity="medium",
                title="ELA residual long-tail",
                detail=(
                    f"Residual tail (p99−p90={tail:.0f}) is elevated — "
                    "possible local re-encoding. Heavy compression can also cause this."
                ),
                evidence=f"tail={tail:.1f}, p99={p99:.1f}, p90={p90:.1f}",
                impact=drop * weight / 100,
            )
        )

    score = float(np.clip(score, 0, 100))
    if score >= 85:
        summary = "ELA residuals look consistent with a single compression pass."
    elif score >= 55:
        summary = "Some ELA hotspots — review highlighted regions."
    else:
        summary = "Strong ELA anomalies — likely local re-encoding / edit."

    result = CheckResult(
        name="ela",
        weight=weight,
        score=score,
        weighted_score=score * weight / 100,
        summary=summary,
        issues=issues,
        regions=regions,
        meta={
            "mean": round(mean_v, 2),
            "p90": round(p90, 2),
            "p95": round(p95, 2),
            "p99": round(p99, 2),
            "p999": round(p999, 2),
            "tail": round(tail, 2),
            "hotspot_frac": round(hotspot_frac, 5),
            "used_diff": used_diff,
            "quality": quality,
        },
    )
    return result, gray, heat
