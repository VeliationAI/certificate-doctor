from __future__ import annotations

import cv2
import numpy as np

from certificate_doctor.models import WEIGHTS, CheckResult, Issue, Region


def check_copy_move(bgr: np.ndarray, *, block: int = 36, stride: int = 28) -> CheckResult:
    """Detect cloned patches via textured-template matching + consistent shift."""
    weight = WEIGHTS["copy_move"]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    margin = 20

    # Candidate textured patches
    candidates: list[tuple[int, int, float]] = []
    for y in range(margin, h - block - margin, stride):
        for x in range(margin, w - block - margin, stride):
            patch = gray[y : y + block, x : x + block]
            std = float(np.std(patch))
            if std < 20:
                continue
            edges = cv2.Canny(patch, 60, 150)
            edge_frac = float(np.mean(edges > 0))
            if edge_frac < 0.06 or edge_frac > 0.48:
                continue
            candidates.append((x, y, std * edge_frac))

    candidates = sorted(candidates, key=lambda t: -t[2])[:48]

    # Match each candidate elsewhere; collect displacement votes
    shift_hits: dict[tuple[int, int], list[tuple[tuple[int, int], tuple[int, int], float]]] = {}
    for x, y, _score in candidates:
        tmpl = gray[y : y + block, x : x + block]
        # Search whole page but mask out nearby area by zeroing response later
        res = cv2.matchTemplate(gray, tmpl, cv2.TM_CCOEFF_NORMED)
        # Suppress local neighborhood around the template origin
        y0 = max(0, y - block)
        y1 = min(res.shape[0], y + block + 1)
        x0 = max(0, x - block)
        x1 = min(res.shape[1], x + block + 1)
        res[y0:y1, x0:x1] = -1.0

        min_v, max_v, min_l, max_l = cv2.minMaxLoc(res)
        if max_v < 0.97:
            continue
        mx, my = int(max_l[0]), int(max_l[1])
        dist = ((mx - x) ** 2 + (my - y) ** 2) ** 0.5
        if dist < block * 3.0:
            continue

        dx, dy = mx - x, my - y
        # Canonicalize shift direction
        if dx < 0 or (dx == 0 and dy < 0):
            dx, dy = -dx, -dy
            pair = ((mx, my), (x, y), float(max_v))
        else:
            pair = ((x, y), (mx, my), float(max_v))

        qx = int(round(dx / 8) * 8)
        qy = int(round(dy / 8) * 8)
        shift_hits.setdefault((qx, qy), []).append(pair)

    # Prefer shifts with multiple agreeing pairs
    clusters = sorted(shift_hits.items(), key=lambda kv: (-len(kv[1]), -max(p[2] for p in kv[1])))
    kept: list[tuple[tuple[int, int], tuple[int, int], float]] = []
    for _shift, pairs in clusters:
        local: list[tuple[tuple[int, int], tuple[int, int], float]] = []
        for p in sorted(pairs, key=lambda t: -t[2]):
            if any(abs(p[0][0] - k[0][0]) < stride and abs(p[0][1] - k[0][1]) < stride for k in local):
                continue
            local.append(p)
        # Require at least two agreeing pairs on the same shift (avoids lone false hits)
        if len(local) >= 2:
            kept.extend(local[:6])
            break

    score = 100.0
    issues: list[Issue] = []
    regions: list[Region] = []

    if kept:
        drop = min(90, 50 + len(kept) * 8)
        score -= drop
        for (x1, y1), (x2, y2), corr in kept:
            regions.append(Region(x=x1, y=y1, w=block, h=block, label=f"copy {corr:.2f}", score=corr))
            regions.append(Region(x=x2, y=y2, w=block, h=block, label="match", score=corr))
        issues.append(
            Issue(
                check="copy_move",
                severity="high",
                title="Duplicate patch fingerprints",
                detail=(
                    f"Found {len(kept)} highly similar block pair(s) sharing a displacement "
                    "vector — classic copy-move signal for cloned seals or stamps."
                ),
                evidence=f"pairs={len(kept)}, top_corr={kept[0][2]:.3f}",
                impact=drop * weight / 100,
            )
        )

    score = float(np.clip(score, 0, 100))
    if score >= 85:
        summary = "No strong copy-move duplicates detected."
    elif score >= 55:
        summary = "Possible duplicated patches — review highlighted blocks."
    else:
        summary = "Strong copy-move matches — likely cloned regions."

    return CheckResult(
        name="copy_move",
        weight=weight,
        score=score,
        weighted_score=score * weight / 100,
        summary=summary,
        issues=issues,
        regions=regions,
        meta={"pair_count": len(kept), "block": block, "stride": stride, "candidates": len(candidates)},
    )
