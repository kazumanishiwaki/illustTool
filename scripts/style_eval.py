#!/usr/bin/env python3
import argparse
import csv
import fnmatch
import html
import json
import os
import shlex
import shutil
import statistics
import sys
import time
import unicodedata
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "style_fingerprints.json"
IMAGE_EXTENSIONS = {".webp", ".png", ".jpg", ".jpeg"}
MANUAL_AXES = {
    "subjectAdherence": 15,
    "lineShapeLanguage": 15,
    "textureMediumVisual": 15,
    "compositionIntent": 8,
    "stylePurity": 10,
    "productionUsefulness": 2
}
PASS_AXIS_MINIMUMS = {
    "subjectAdherence": 12,
    "textureMediumVisual": 12,
    "stylePurity": 8
}
SHEET_TILE_WIDTH = 220
SHEET_TILE_HEIGHT = 180
SHEET_LABEL_HEIGHT = 58
SHEET_GAP = 14
SHEET_MARGIN = 24


def write_text_atomic(path, text, encoding="utf-8"):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(text, encoding=encoding)
    tmp_path.replace(path)


def load_data():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def load_run_meta(run_id):
    meta_path = ROOT / "prompt_runs" / run_id / "run_meta.json"
    if not meta_path.exists():
        return None
    return json.loads(meta_path.read_text(encoding="utf-8"))


def load_run_theme(data, run_id):
    meta = load_run_meta(run_id)
    if meta is None:
        plan_path = ROOT / "prompt_runs" / run_id / "generation_plan.json"
        if plan_path.exists():
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            theme = plan.get("theme")
            if theme:
                return theme
        return data["theme"]
    return {
        "id": meta.get("runId", run_id),
        "ja": meta.get("subject", ""),
        "basePromptEn": meta.get("basePromptEn", meta.get("subject", "")),
        "mustContain": meta.get("requiredElements", []),
        "mustAvoid": meta.get("avoidElements", []),
    }


def theme_subject_lock_line(theme):
    theme = theme or {}
    subject = (theme.get("ja") or "").strip()
    must = [str(item).strip() for item in theme.get("mustContain", []) if str(item).strip()]
    avoid = [str(item).strip() for item in theme.get("mustAvoid", []) if str(item).strip()]
    if subject and must:
        line = f"Keep the fixed subject explicit: {subject}; required elements: {', '.join(must)}."
    elif subject:
        line = f"Keep the fixed subject explicit: {subject}."
    elif must:
        line = f"Keep required elements explicit: {', '.join(must)}."
    else:
        line = "Keep the subject lock at the start of the prompt."
    if avoid:
        line += f" Avoid: {', '.join(avoid)}."
    return line


def theme_subject_clarity_focus(theme):
    theme = theme or {}
    bits = []
    subject = (theme.get("ja") or "").strip()
    if subject:
        bits.append(subject)
    bits.extend(str(item).strip() for item in theme.get("mustContain", []) if str(item).strip())
    if bits:
        return (
            "subject clarity variant: make "
            f"{', '.join(bits)} immediately readable at thumbnail size"
        )
    return (
        "subject clarity variant: make the main subject, focal pose, and required props "
        "immediately readable at thumbnail size"
    )


def theme_subject_adherence_messages(theme):
    theme = theme or {}
    messages = [
        "The fixed subject must be obvious before judging style quality.",
    ]
    must = [str(item).strip() for item in theme.get("mustContain", []) if str(item).strip()]
    if must:
        messages.extend(f"Must contain: {item}" for item in must)
    subject = (theme.get("ja") or "").strip()
    avoid = [str(item).strip() for item in theme.get("mustAvoid", []) if str(item).strip()]
    if subject:
        messages.append(f"Reject or cap if the image does not clearly depict: {subject}.")
    if avoid:
        messages.append(f"Reject or cap if forbidden elements appear: {', '.join(avoid)}.")
    if not subject and not must:
        messages.append("Reject or cap if required subject elements are missing or ambiguous.")
    return messages


def theme_composition_messages(theme, fingerprint):
    subject = (theme or {}).get("ja", "").strip()
    if subject:
        return [
            f"Composition: {fingerprint['composition']}",
            f"The generated image should preserve reference density and whitespace while keeping {subject} readable.",
        ]
    return [
        f"Composition: {fingerprint['composition']}",
        "The generated image should preserve reference density and whitespace while keeping the main subject readable.",
    ]


def theme_production_usefulness_messages(theme):
    theme = theme or {}
    subject = (theme.get("ja") or "").strip()
    must = [str(item).strip() for item in theme.get("mustContain", []) if str(item).strip()]
    readable = ", ".join([part for part in [subject, *must] if part])
    if readable:
        return [
            "The image should be usable as a finished illustration candidate, not only as a style test.",
            f"{readable} should remain legible at thumbnail size.",
        ]
    return [
        "The image should be usable as a finished illustration candidate, not only as a style test.",
        "The main subject and silhouette should remain legible at thumbnail size.",
    ]


def theme_manual_subject_hint(theme):
    theme = theme or {}
    subject = (theme.get("ja") or "").strip()
    must = [str(item).strip() for item in theme.get("mustContain", []) if str(item).strip()]
    if subject and must:
        return (
            f"Subject: move the subject lock earlier and make {subject} with "
            f"{', '.join(must)} unambiguous."
        )
    if subject:
        return f"Subject: move the subject lock earlier and make {subject} unambiguous."
    if must:
        return f"Subject: move the subject lock earlier and make {', '.join(must)} unambiguous."
    return "Subject: move the subject lock earlier and make the required elements unambiguous."


LEGACY_STYLE_ALIASES = {
    "naive_wobbly": "naive_wobbly_line",
    "print_relief": "print_relief_lino",
    "editorial_outline": "editorial_outline_minimal",
}


def resolve_style_record(data, style_id, label_ja=""):
    styles_by_id = {style["id"]: style for style in data["styles"]}
    if style_id in styles_by_id:
        return styles_by_id[style_id]
    alias_id = LEGACY_STYLE_ALIASES.get(style_id)
    if alias_id and alias_id in styles_by_id:
        resolved = dict(styles_by_id[alias_id])
        resolved["id"] = style_id
        if label_ja:
            resolved["labelJa"] = label_ja
        return resolved
    return None


def styles_for_run(data, run_id):
    meta = load_run_meta(run_id)
    allowed = None
    if meta and meta.get("styleIds"):
        allowed = set(meta["styleIds"])
    else:
        plan_path = ROOT / "prompt_runs" / run_id / "generation_plan.json"
        if plan_path.exists():
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            job_ids = [job["styleId"] for job in plan.get("jobs", []) if job.get("styleId")]
            if job_ids:
                allowed = set(job_ids)
    if not allowed:
        return data["styles"]

    matched = [style for style in data["styles"] if style.get("id") in allowed]
    if len(matched) == len(allowed):
        return matched

    plan_path = ROOT / "prompt_runs" / run_id / "generation_plan.json"
    if not plan_path.exists():
        return matched or data["styles"]
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    legacy_rows = []
    for job in plan.get("jobs", []):
        style_id = job.get("styleId")
        if style_id not in allowed:
            continue
        style = resolve_style_record(
            data,
            style_id,
            job.get("labelJa", style_id),
        )
        if style is None:
            style = {
                "id": style_id,
                "labelJa": job.get("labelJa", style_id),
                "referenceGlob": "",
                "referenceGlobs": [],
                "promptFragments": [],
                "negativeFragments": [],
                "visualFingerprint": {},
                "styleScoringWeights": {},
                "improvementRules": {},
            }
        legacy_rows.append(style)
    return legacy_rows or matched or data["styles"]


def iter_reference_images(style):
    patterns = style.get("referenceGlobs") or [style["referenceGlob"]]
    paths = []
    for p in ROOT.iterdir():
        normalized_name = unicodedata.normalize("NFC", p.name)
        normalized_patterns = [unicodedata.normalize("NFC", pattern) for pattern in patterns]
        if p.suffix.lower() in IMAGE_EXTENSIONS and any(fnmatch.fnmatch(normalized_name, pattern) for pattern in normalized_patterns):
            paths.append(p)
    return sorted(paths, key=lambda p: unicodedata.normalize("NFC", p.name))


def image_metrics(path):
    im = Image.open(path).convert("RGB")
    im.thumbnail((180, 180))
    pixel_data = im.get_flattened_data() if hasattr(im, "get_flattened_data") else im.getdata()
    pixels = list(pixel_data)
    width, height = im.size
    sample_step = max(1, len(pixels) // 5000)
    sample = pixels[::sample_step]

    saturations = []
    values = []
    for r, g, b in sample:
        mx = max(r, g, b) / 255
        mn = min(r, g, b) / 255
        values.append(mx)
        saturations.append(0 if mx == 0 else (mx - mn) / mx)

    near_white = sum(1 for r, g, b in pixels if r > 224 and g > 224 and b > 220) / len(pixels)
    dark_share = sum(1 for r, g, b in pixels if r < 50 and g < 50 and b < 50) / len(pixels)

    gray = [int(0.299 * r + 0.587 * g + 0.114 * b) for r, g, b in pixels]
    total = 0
    count = 0
    for y in range(height):
        row = y * width
        for x in range(width):
            i = row + x
            if x + 1 < width:
                total += abs(gray[i] - gray[i + 1])
                count += 1
            if y + 1 < height:
                total += abs(gray[i] - gray[i + width])
                count += 1
    edge_density = total / (count * 255) if count else 0

    palette_image = im.quantize(colors=8, method=Image.Quantize.MEDIANCUT).convert("P")
    palette = palette_image.getpalette()
    colors = palette_image.getcolors(maxcolors=999999)
    top_colors = []
    for color_count, idx in sorted(colors, reverse=True)[:6]:
        rgb = tuple(palette[idx * 3:idx * 3 + 3])
        top_colors.append({"hex": f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}", "share": color_count / len(pixels)})

    return {
        "saturation": round(statistics.mean(saturations), 4),
        "brightness": round(statistics.mean(values), 4),
        "nearWhiteShare": round(near_white, 4),
        "darkShare": round(dark_share, 4),
        "edgeDensity": round(edge_density, 4),
        "topColors": top_colors
    }


def baseline_for_style(style):
    paths = iter_reference_images(style)
    if not paths:
        raise SystemExit(f"No references found for style {style['id']} with glob {style['referenceGlob']}")
    rows = [image_metrics(p) for p in paths]
    keys = ["saturation", "brightness", "nearWhiteShare", "darkShare", "edgeDensity"]
    baseline = {
        "styleId": style["id"],
        "labelJa": style["labelJa"],
        "referenceCount": len(paths),
        "references": [p.name for p in paths],
        "metrics": {}
    }
    for key in keys:
        vals = [r[key] for r in rows]
        baseline["metrics"][key] = {
            "mean": round(statistics.mean(vals), 4),
            "stdev": round(statistics.pstdev(vals), 4),
            "min": round(min(vals), 4),
            "max": round(max(vals), 4)
        }
    color_scores = {}
    for r in rows:
        for c in r["topColors"][:4]:
            color_scores[c["hex"]] = color_scores.get(c["hex"], 0) + c["share"]
    baseline["dominantColors"] = [
        {"hex": k, "weight": round(v / len(rows), 4)}
        for k, v in sorted(color_scores.items(), key=lambda item: item[1], reverse=True)[:10]
    ]
    return baseline


def metric_scale(metric_baseline):
    return max(metric_baseline["max"] - metric_baseline["min"], metric_baseline["stdev"] * 3, 0.03)


def metric_similarity(generated_value, reference_value, metric_baseline):
    return max(0, 1 - abs(generated_value - reference_value) / metric_scale(metric_baseline))


def range_score(value, low, high, soft=0.04):
    if low <= value <= high:
        return 1
    if value < low:
        return max(0, 1 - (low - value) / soft)
    return max(0, 1 - (value - high) / soft)


def style_marker_score(style_id, metrics):
    marker_style_id = {
        "naive_wobbly_line": "naive_wobbly",
        "naive_wobbly_plain": "naive_wobbly",
        "naive_wobbly_color": "naive_wobbly",
        "naive_wobbly_filled": "naive_wobbly",
        "naive_wobbly_filled_2": "naive_wobbly",
        "print_relief_lino": "print_relief",
        "print_relief_gradient": "print_relief",
        "woodcut_print": "print_relief",
        "woodcut_print_2": "print_relief",
        "woodcut_print_3": "print_relief",
        "editorial_outline_art": "editorial_outline",
        "editorial_outline_art_6": "editorial_outline",
        "editorial_outline_singleline": "editorial_outline",
        "editorial_outline_minimal": "editorial_outline",
        "flat_vector_corporate_3": "flat_vector",
        "flat_vector_twotone": "flat_vector",
        "flat_vector_filled": "flat_vector",
        "flat_vector_3d": "flat_vector",
        "grain_flat_5": "grain_flat",
        "tech_illustration": "flat_vector",
    }.get(style_id, style_id)
    marker_specs = {
        "naive_wobbly": [
            ("nearWhiteShare", 0.42, 0.86, 0.16, 2.0),
            ("darkShare", 0.0, 0.035, 0.04, 1.5),
            ("edgeDensity", 0.034, 0.085, 0.025, 2.5),
            ("saturation", 0.07, 0.34, 0.12, 1.5),
            ("brightness", 0.82, 0.97, 0.08, 1.5),
            ("grainFlatPenalty", 0, 0, 1, 1.0),
        ],
        "grain_flat": [
            ("nearWhiteShare", 0.0, 0.48, 0.18, 2.0),
            ("darkShare", 0.0, 0.035, 0.04, 1.5),
            ("edgeDensity", 0.0, 0.035, 0.02, 2.0),
            ("saturation", 0.10, 0.38, 0.12, 1.5),
            ("brightness", 0.72, 0.91, 0.10, 1.5),
            ("printPenalty", 0, 0, 1, 1.5),
        ],
        "print_relief": [
            ("darkShare", 0.025, 0.16, 0.08, 2.0),
            ("edgeDensity", 0.028, 0.075, 0.03, 2.0),
            ("saturation", 0.18, 0.58, 0.12, 1.5),
            ("brightness", 0.50, 0.86, 0.12, 1.5),
            ("nearWhiteShare", 0.0, 0.36, 0.20, 1.0),
            ("reliefContrast", 0, 0, 1, 2.0),
        ],
        "editorial_outline": [
            ("nearWhiteShare", 0.74, 1.0, 0.12, 3.0),
            ("saturation", 0.0, 0.08, 0.08, 2.0),
            ("edgeDensity", 0.008, 0.033, 0.02, 2.0),
            ("brightness", 0.90, 1.0, 0.06, 2.0),
            ("darkShare", 0.0, 0.04, 0.04, 1.0),
        ],
        "flat_vector": [
            ("nearWhiteShare", 0.45, 0.90, 0.18, 2.0),
            ("darkShare", 0.0, 0.035, 0.04, 1.5),
            ("edgeDensity", 0.018, 0.050, 0.025, 1.5),
            ("saturation", 0.12, 0.45, 0.14, 2.0),
            ("brightness", 0.84, 0.98, 0.08, 1.5),
            ("vectorCleanliness", 0, 0, 1, 1.5),
        ],
    }
    total = 0
    details = {}
    for key, low, high, soft, weight in marker_specs.get(marker_style_id, []):
        if key == "grainFlatPenalty":
            raw = 1 - max(0, min(1, (0.035 - metrics["edgeDensity"]) / 0.035)) * max(0, min(1, (0.45 - metrics["nearWhiteShare"]) / 0.45))
        elif key == "printPenalty":
            raw = 1 - max(0, min(1, (metrics["darkShare"] - 0.04) / 0.10)) * max(0, min(1, (metrics["edgeDensity"] - 0.035) / 0.04))
        elif key == "reliefContrast":
            raw = max(0, min(1, metrics["darkShare"] / 0.08)) * max(0, min(1, metrics["edgeDensity"] / 0.05))
        elif key == "vectorCleanliness":
            raw = max(0, min(1, metrics["nearWhiteShare"] / 0.60)) * max(0, min(1, (0.055 - metrics["edgeDensity"]) / 0.04)) * max(0, min(1, (0.04 - metrics["darkShare"]) / 0.04))
        else:
            raw = range_score(metrics[key], low, high, soft)
        points = round(raw * weight, 2)
        details[key] = {"value": None if key not in metrics else metrics[key], "points": points, "max": weight}
        total += points
    return round(total, 2), details


def reference_metric_rows(style):
    return [
        {"path": str(path), "metrics": image_metrics(path)}
        for path in iter_reference_images(style)
    ]


def all_reference_manifest(data):
    rows = []
    for style in data["styles"]:
        for index, path in enumerate(iter_reference_images(style), start=1):
            metrics = image_metrics(path)
            rows.append({
                "styleId": style["id"],
                "labelJa": style["labelJa"],
                "indexInStyle": index,
                "path": str(path),
                "fileName": path.name,
                "metrics": metrics,
                "visualFingerprint": style["visualFingerprint"],
                "promptFragments": style["promptFragments"],
                "negativeFragments": style["negativeFragments"]
            })
    return {
        "schemaVersion": 1,
        "referenceCount": len(rows),
        "styles": [
            {
                "styleId": style["id"],
                "labelJa": style["labelJa"],
                "referenceCount": len(iter_reference_images(style))
            }
            for style in data["styles"]
        ],
        "images": rows
    }


def write_reference_analysis(data):
    manifest = all_reference_manifest(data)
    out_json = ROOT / "reports" / "reference_manifest.json"
    out_md = ROOT / "reports" / "reference_analysis.md"
    out_json.parent.mkdir(exist_ok=True)
    write_text_atomic(out_json, json.dumps(manifest, ensure_ascii=False, indent=2))
    write_text_atomic(out_md, render_reference_analysis_md(data, manifest))
    return out_json, out_md


def render_reference_analysis_md(data, manifest):
    lines = [
        "# Reference Image Analysis",
        "",
        f"Total references: {manifest['referenceCount']}",
        "",
        "This report turns the local reference images into reusable style fingerprints for prompt generation and evaluation.",
        ""
    ]
    for style in data["styles"]:
        images = [row for row in manifest["images"] if row["styleId"] == style["id"]]
        baselines = baseline_for_style(style)
        lines.extend([
            f"## {style['labelJa']} / `{style['id']}`",
            "",
            f"Reference count: {len(images)}",
            "",
            "### Visual Fingerprint",
            "",
            f"- Line: {style['visualFingerprint']['line']}",
            f"- Shape: {style['visualFingerprint']['shape']}",
            f"- Color: {style['visualFingerprint']['color']}",
            f"- Texture: {style['visualFingerprint']['texture']}",
            f"- Composition: {style['visualFingerprint']['composition']}",
            f"- Person: {style['visualFingerprint']['person']}",
            "",
            "### Prompt Fragments",
            "",
            *[f"- `{fragment}`" for fragment in style["promptFragments"]],
            "",
            "### Negative Fragments",
            "",
            *[f"- `{fragment}`" for fragment in style["negativeFragments"]],
            "",
            "### Metric Baseline",
            "",
            "| Metric | Mean | Min | Max |",
            "|---|---:|---:|---:|"
        ])
        for metric, values in baselines["metrics"].items():
            lines.append(f"| {metric} | {values['mean']} | {values['min']} | {values['max']} |")
        lines.extend([
            "",
            "### Images",
            "",
            "| File | Saturation | Brightness | White share | Dark share | Edge density | Top colors |",
            "|---|---:|---:|---:|---:|---:|---|"
        ])
        for row in images:
            metrics = row["metrics"]
            colors = " ".join(color["hex"] for color in metrics["topColors"][:4])
            lines.append(
                f"| {row['fileName']} | {metrics['saturation']} | {metrics['brightness']} | "
                f"{metrics['nearWhiteShare']} | {metrics['darkShare']} | {metrics['edgeDensity']} | {colors} |"
            )
        lines.append("")
    return "\n".join(lines)


def score_generated(style, generated_path):
    baseline = baseline_for_style(style)
    generated = image_metrics(generated_path)
    weights = {
        "saturation": 5,
        "brightness": 4,
        "nearWhiteShare": 6,
        "darkShare": 4,
        "edgeDensity": 6
    }
    nearest = None
    for row in reference_metric_rows(style):
        total_weight = 0
        weighted_similarity = 0
        similarities = {}
        for key, weight in weights.items():
            sim = metric_similarity(generated[key], row["metrics"][key], baseline["metrics"][key])
            similarities[key] = sim
            total_weight += weight
            weighted_similarity += sim * weight
        score = weighted_similarity / total_weight
        if nearest is None or score > nearest["score"]:
            nearest = {"score": score, "path": row["path"], "metrics": row["metrics"], "similarities": similarities}

    total = 0
    details = {}
    for key, weight in weights.items():
        raw = nearest["similarities"][key]
        points = round(raw * weight, 2)
        details[key] = {
            "generated": generated[key],
            "referenceMean": baseline["metrics"][key]["mean"],
            "nearestReference": nearest["metrics"][key],
            "points": points,
            "max": weight
        }
        total += points
    marker_total, marker_details = style_marker_score(style["id"], generated)
    total += marker_total
    return {
        "styleId": style["id"],
        "generated": str(generated_path),
        "automaticScore": round(total, 2),
        "automaticMax": sum(weights.values()) + 10,
        "automaticDetails": details,
        "styleMarkerScore": marker_total,
        "styleMarkerDetails": marker_details,
        "generatedMetrics": generated,
        "nearestReference": nearest["path"],
        "referenceBaseline": baseline
    }


def generated_images_for_style(run_id, style_id):
    generated_dir = ROOT / "generated" / run_id / style_id
    if not generated_dir.exists():
        return []
    return sorted([p for p in generated_dir.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS])


def classify_generated(data, generated_path):
    results = [
        {
            "styleId": style["id"],
            "labelJa": style["labelJa"],
            "automaticScore": score_generated(style, generated_path)["automaticScore"]
        }
        for style in data["styles"]
    ]
    results.sort(key=lambda row: row["automaticScore"], reverse=True)
    return results


def manual_template():
    return {
        "axes": {key: None for key in MANUAL_AXES},
        "axisMax": MANUAL_AXES,
        "notes": "",
        "hardCapApplied": None,
        "finalScoreOverride": None
    }


def evaluate_run(data, run_id):
    run_rows = []
    for style in styles_for_run(data, run_id):
        images = generated_images_for_style(run_id, style["id"])
        style_row = {
            "styleId": style["id"],
            "labelJa": style["labelJa"],
            "promptPath": str(ROOT / "prompt_runs" / run_id / f"{style['id']}.md"),
            "generatedImages": []
        }
        for image_path in images:
            target_score = score_generated(style, image_path)
            ranking = classify_generated(data, image_path)
            rank = next((idx + 1 for idx, row in enumerate(ranking) if row["styleId"] == style["id"]), None)
            style_row["generatedImages"].append({
                "path": str(image_path),
                "targetAutomaticScore": target_score["automaticScore"],
                "automaticMax": target_score["automaticMax"],
                "targetRank": rank,
                "targetIsTopStyle": rank == 1,
                "styleRanking": ranking,
                "generatedMetrics": target_score["generatedMetrics"],
                "styleMarkerScore": target_score.get("styleMarkerScore"),
                "styleMarkerDetails": target_score.get("styleMarkerDetails", {}),
                "manualReview": manual_template()
            })
        run_rows.append(style_row)
    return {
        "runId": run_id,
        "theme": load_run_theme(data, run_id),
        "passScore": data["globalEvaluation"]["passScore"],
        "automaticMetricWeight": data["globalEvaluation"]["automaticMetricWeight"],
        "manualRubricWeight": data["globalEvaluation"]["manualRubricWeight"],
        "manualAxes": MANUAL_AXES,
        "passAxisMinimums": PASS_AXIS_MINIMUMS,
        "styles": run_rows
    }


def report_is_stale(data, run_id, out_json):
    if not out_json.exists():
        return True
    report_mtime = out_json.stat().st_mtime
    for style in styles_for_run(data, run_id):
        for image_path in generated_images_for_style(run_id, style["id"]):
            if image_path.stat().st_mtime > report_mtime:
                return True
    plan_path = ROOT / "prompt_runs" / run_id / "generation_plan.json"
    if plan_path.exists() and plan_path.stat().st_mtime > report_mtime:
        return True
    return False


def write_run_report(data, run_id, force=False):
    out_json, out_html = report_paths(run_id)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    if not force and out_json.exists() and not report_is_stale(data, run_id, out_json):
        try:
            report = json.loads(out_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            report = None
        if report is not None:
            if "summary" not in report:
                compute_final_scores(report)
                report["summary"] = summarize_report(report)
                write_text_atomic(out_json, json.dumps(report, ensure_ascii=False, indent=2))
            if not out_html.exists():
                write_text_atomic(out_html, render_run_html(report))
            return out_json, out_html

    report = evaluate_run(data, run_id)
    report["theme"] = load_run_theme(data, run_id)
    preserve_manual_reviews(report, out_json)
    compute_final_scores(report)
    report["summary"] = summarize_report(report)
    write_text_atomic(out_json, json.dumps(report, ensure_ascii=False, indent=2))
    write_text_atomic(out_html, render_run_html(report))
    return out_json, out_html


def report_paths(run_id):
    return ROOT / "reports" / f"{run_id}_evaluation.json", ROOT / "reports" / f"{run_id}_review.html"


def preserve_manual_reviews(report, out_json):
    if not out_json.exists():
        return
    try:
        existing = json.loads(out_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    existing_reviews = {}
    for style in existing.get("styles", []):
        for image in style.get("generatedImages", []):
            if "path" in image and "manualReview" in image:
                existing_reviews[image["path"]] = image["manualReview"]
    for style in report["styles"]:
        for image in style["generatedImages"]:
            if image["path"] in existing_reviews:
                image["manualReview"] = existing_reviews[image["path"]]


def compute_final_scores(report):
    pass_score = report["passScore"]
    for style in report["styles"]:
        for image in style["generatedImages"]:
            manual = image.get("manualReview", {})
            axes = manual.get("axes", {})
            values = [axes.get(key) for key in MANUAL_AXES]
            if all(isinstance(value, (int, float)) for value in values):
                manual_total = round(sum(values), 2)
                final_score = round(image["targetAutomaticScore"] + manual_total, 2)
                hard_cap = manual.get("hardCapApplied")
                if isinstance(hard_cap, (int, float)):
                    final_score = min(final_score, hard_cap)
                override = manual.get("finalScoreOverride")
                if isinstance(override, (int, float)):
                    final_score = override
                image["manualScore"] = manual_total
                image["finalScore"] = final_score
                failure_reasons = pass_failure_reasons(image, axes, pass_score)
                image["failureReasons"] = failure_reasons
                image["passed"] = not failure_reasons
            else:
                image["manualScore"] = None
                image["finalScore"] = None
                image["failureReasons"] = ["manual review missing"]
                image["passed"] = False


def pass_failure_reasons(image, axes, pass_score):
    reasons = []
    final_score = image.get("finalScore")
    if final_score is None or final_score < pass_score:
        reasons.append(f"final score below {pass_score}")
    if not image.get("targetIsTopStyle"):
        reasons.append("target style is not ranked first")
    for axis, minimum in PASS_AXIS_MINIMUMS.items():
        value = axes.get(axis)
        if not isinstance(value, (int, float)) or value < minimum:
            reasons.append(f"{axis} below {minimum}")
    manual = image.get("manualReview", {})
    hard_cap = manual.get("hardCapApplied")
    if isinstance(hard_cap, (int, float)) and hard_cap < pass_score:
        reasons.append(f"hard cap below {pass_score}")
    return reasons


def write_existing_report(report, run_id):
    out_json, out_html = report_paths(run_id)
    compute_final_scores(report)
    report["summary"] = summarize_report(report)
    write_text_atomic(out_json, json.dumps(report, ensure_ascii=False, indent=2))
    write_text_atomic(out_html, render_run_html(report))
    return out_json, out_html


def summarize_report(report):
    style_count = len(report["styles"])
    generated_count = 0
    reviewed_count = 0
    passed_styles = 0
    missing_styles = []
    pending_review_styles = []
    failed_styles = []
    best_by_style = {}
    for style in report["styles"]:
        images = style["generatedImages"]
        generated_count += len(images)
        if not images:
            missing_styles.append(style["styleId"])
            best_by_style[style["styleId"]] = None
            continue
        reviewed_images = [image for image in images if image.get("finalScore") is not None]
        reviewed_count += len(reviewed_images)
        passed_images = [image for image in images if image.get("passed")]
        if passed_images:
            passed_styles += 1
        elif not reviewed_images:
            pending_review_styles.append(style["styleId"])
        else:
            failed_styles.append(style["styleId"])
        ranked = sorted(
            images,
            key=lambda image: (
                image.get("passed") is True,
                image.get("finalScore") if image.get("finalScore") is not None else -1,
                image.get("targetAutomaticScore", -1)
            ),
            reverse=True
        )
        best = ranked[0]
        best_by_style[style["styleId"]] = {
            "path": best["path"],
            "targetAutomaticScore": best["targetAutomaticScore"],
            "targetRank": best["targetRank"],
            "manualScore": best.get("manualScore"),
            "finalScore": best.get("finalScore"),
            "passed": best.get("passed", False),
            "failureReasons": best.get("failureReasons", [])
        }
    return {
        "styleCount": style_count,
        "generatedImageCount": generated_count,
        "reviewedImageCount": reviewed_count,
        "passedStyleCount": passed_styles,
        "allStylesPassed": passed_styles == style_count,
        "missingStyles": missing_styles,
        "pendingReviewStyles": pending_review_styles,
        "failedStyles": failed_styles,
        "bestByStyle": best_by_style
    }


def run_passes(report):
    summary = report.get("summary") or summarize_report(report)
    return summary["allStylesPassed"]


def render_run_html(report):
    summary = report.get("summary") or summarize_report(report)
    axis_lines = "<br>".join(f"{key}: {value}" for key, value in MANUAL_AXES.items())
    style_blocks = []
    for style in report["styles"]:
        refs = sorted((ROOT / "_analysis_contact_sheets").glob(f"{style['styleId']}.jpg"))
        visual_sheet_path = ROOT / "reports" / f"{report['runId']}_visual_review" / f"{style['styleId']}.jpg"
        ref_html = ""
        if refs:
            ref_html = f'<img class="reference" src="{html.escape(str(refs[0]))}" alt="{html.escape(style["styleId"])} references">'
        generated = style["generatedImages"]
        if generated:
            cards = []
            for row in generated:
                rank_class = "pass" if row["targetIsTopStyle"] else "warn"
                final = "Not reviewed" if row.get("finalScore") is None else f'Final: {row["finalScore"]}/100'
                final_class = "pass" if row.get("passed") else "warn"
                ranking = "<br>".join(
                    f'{html.escape(r["styleId"])}: {r["automaticScore"]}/35'
                    for r in row["styleRanking"][:5]
                )
                review_command = (
                    f"python3 scripts/style_eval.py --set-review {report['runId']} {style['styleId']} "
                    f"{Path(row['path']).name} --scores SUBJECT LINE TEXTURE COMPOSITION PURITY USEFULNESS --notes \"\""
                )
                manual = row.get("manualReview", {})
                manual_axes = manual.get("axes", {})
                manual_summary = "<br>".join(
                    f"{html.escape(key)}: {html.escape(str(manual_axes.get(key)))} / {max_value}"
                    for key, max_value in MANUAL_AXES.items()
                )
                failures = row.get("failureReasons") or []
                failure_summary = "none" if not failures else "<br>".join(html.escape(reason) for reason in failures)
                cards.append(f"""
                <article class="candidate">
                  <img src="{html.escape(row["path"])}" alt="{html.escape(Path(row["path"]).name)}">
                  <div class="candidate-meta">
                    <b>{html.escape(Path(row["path"]).name)}</b>
                    <span>Auto: {row["targetAutomaticScore"]}/35</span>
                    <span class="{rank_class}">Target rank: {row["targetRank"]}</span>
                    <span class="{final_class}">{final}</span>
                    <details><summary>Style ranking</summary><p>{ranking}</p></details>
                    <details><summary>Manual scores</summary><p>{manual_summary}</p></details>
                    <details><summary>Failure reasons</summary><p>{failure_summary}</p></details>
                    <details><summary>Review command</summary><pre>{html.escape(review_command)}</pre></details>
                  </div>
                </article>
                """)
            generated_html = "\n".join(cards)
        else:
            generated_html = '<p class="missing">No generated image yet. Save planned variants under <code>generated/{run_id}/{style_id}/round_01_a.png</code>, <code>round_01_b.png</code>, and <code>round_01_c.png</code>.</p>'
            generated_html = generated_html.replace("{run_id}", html.escape(report["runId"])).replace("{style_id}", html.escape(style["styleId"]))
        style_blocks.append(f"""
        <section>
          <header>
            <h2>{html.escape(style["labelJa"])} <code>{html.escape(style["styleId"])}</code></h2>
            <nav>
              <a href="{html.escape(style["promptPath"])}">Prompt</a>
              <a href="{html.escape(str(visual_sheet_path))}">Visual sheet</a>
            </nav>
          </header>
          {ref_html}
          <div class="candidates">{generated_html}</div>
        </section>
        """)
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(report["runId"])} Review</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f6f6f1; color: #17191f; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 32px 22px 64px; }}
    h1 {{ margin: 0 0 8px; font-size: 30px; }}
    .lead {{ margin: 0 0 28px; color: #555b66; }}
    section {{ background: #fff; border: 1px solid #e0e3eb; border-radius: 8px; padding: 18px; margin: 18px 0; }}
    section header {{ display: flex; justify-content: space-between; align-items: baseline; gap: 16px; }}
    section nav {{ display: flex; gap: 12px; flex-wrap: wrap; }}
    h2 {{ margin: 0 0 14px; font-size: 20px; }}
    code {{ background: #f1f3f8; padding: 2px 5px; border-radius: 4px; }}
    .reference {{ width: 100%; max-width: 1040px; display: block; border: 1px solid #e2e4eb; border-radius: 6px; margin-bottom: 14px; }}
    .candidates {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; }}
    .candidate {{ border: 1px solid #e2e4eb; border-radius: 8px; overflow: hidden; background: #fbfbfb; }}
    .candidate img {{ width: 100%; aspect-ratio: 4 / 3; object-fit: contain; background: white; display: block; }}
    .candidate-meta {{ display: flex; flex-direction: column; gap: 5px; padding: 10px; font-size: 13px; }}
    .pass {{ color: #187141; font-weight: 700; }}
    .warn {{ color: #a24f00; font-weight: 700; }}
    .missing {{ color: #687080; border: 1px dashed #c9cfdb; padding: 14px; border-radius: 8px; }}
  </style>
</head>
<body>
  <main>
    <h1>{html.escape(report["runId"])} Review</h1>
    <p class="lead">Theme: {html.escape(report["theme"]["ja"])} / Pass: {report["passScore"]}+ with target style ranked #1.</p>
    <section>
      <h2>Run Summary</h2>
      <p>Generated: {summary["generatedImageCount"]} / Reviewed: {summary["reviewedImageCount"]} / Passed styles: {summary["passedStyleCount"]} of {summary["styleCount"]}</p>
      <p>Missing: {html.escape(", ".join(summary["missingStyles"]) or "none")}</p>
      <p>Pending review: {html.escape(", ".join(summary["pendingReviewStyles"]) or "none")}</p>
      <p>Failed: {html.escape(", ".join(summary["failedStyles"]) or "none")}</p>
      <p><a href="{html.escape(str(ROOT / "reports" / f"{report['runId']}_review_guide.md"))}">Review guide</a> / <a href="{html.escape(str(ROOT / "reports" / f"{report['runId']}_visual_review" / "index.md"))}">Visual review index</a></p>
      <p>Minimum axes: subjectAdherence 12/15, textureMediumVisual 12/15, stylePurity 8/10.</p>
      <details><summary>Manual score axes</summary><p>{axis_lines}</p></details>
    </section>
    {''.join(style_blocks)}
  </main>
</body>
</html>
"""


def write_style_prompt_file(out_dir, style, style_id, theme, constraints=None, source_run=None):
    prompt = ", ".join(dedupe([theme["basePromptEn"], *style["promptFragments"]]))
    negative = ", ".join(dedupe([*theme["mustAvoid"], *style["negativeFragments"]]))
    constraints = constraints or []
    constraints_block = ""
    if constraints:
        constraints_block = f"""
## Round Improvement Constraints
{chr(10).join(f"- {item}" for item in constraints)}
"""
    source_block = f"\nSource run: `{source_run}`\n" if source_run else ""
    body = f"""# {style["labelJa"]} / {style_id}
{source_block}

## Theme
{theme["ja"]}

## Positive Prompt
{prompt}

## Negative Prompt
{negative}

## Must Contain
{chr(10).join(f"- {item}" for item in theme["mustContain"])}

## Style Fingerprint
- Line: {style["visualFingerprint"].get("line", "")}
- Shape: {style["visualFingerprint"].get("shape", "")}
- Color: {style["visualFingerprint"].get("color", "")}
- Texture: {style["visualFingerprint"].get("texture", "")}
- Composition: {style["visualFingerprint"].get("composition", "")}
- Person: {style["visualFingerprint"].get("person", "")}

## Improvement Rules
{chr(10).join(f"- {key}: {value}" for key, value in style.get("improvementRules", {}).items())}

## Style Scoring Weights
{chr(10).join(f"- {key}: {value}" for key, value in style.get("styleScoringWeights", {}).items())}
{constraints_block}
"""
    write_text_atomic(out_dir / f"{style_id}.md", body)


def write_prompt_pack(data, out_dir, extra_constraints=None, source_run=None):
    out_dir.mkdir(parents=True, exist_ok=True)
    theme = data["theme"]
    for style in data["styles"]:
        constraints = extra_constraints.get(style["id"], []) if extra_constraints else []
        write_style_prompt_file(out_dir, style, style["id"], theme, constraints, source_run)


def read_report(run_id):
    path = ROOT / "reports" / f"{run_id}_evaluation.json"
    if not path.exists():
        raise SystemExit(f"Report not found: {path}. Run --report {run_id} first.")
    return json.loads(path.read_text(encoding="utf-8"))


def find_review_target(report, style_id, image_selector):
    matches = []
    for style in report.get("styles", []):
        if style.get("styleId") != style_id:
            continue
        for image in style.get("generatedImages", []):
            image_path = Path(image["path"])
            if image["path"] == image_selector or image_path.name == image_selector or str(image_path.resolve()) == str((ROOT / image_selector).resolve()):
                matches.append(image)
    if not matches:
        raise SystemExit(f"Generated image not found in report for style={style_id}: {image_selector}")
    if len(matches) > 1:
        raise SystemExit(f"Image selector is ambiguous for style={style_id}: {image_selector}")
    return matches[0]


def parse_review_scores(values):
    if len(values) != len(MANUAL_AXES):
        axes = ", ".join(MANUAL_AXES.keys())
        raise SystemExit(f"--scores requires {len(MANUAL_AXES)} values in this order: {axes}")
    scores = {}
    for key, raw in zip(MANUAL_AXES.keys(), values):
        try:
            value = float(raw)
        except ValueError as exc:
            raise SystemExit(f"Invalid score for {key}: {raw}") from exc
        max_value = MANUAL_AXES[key]
        if value < 0 or value > max_value:
            raise SystemExit(f"Score for {key} must be between 0 and {max_value}: {value}")
        scores[key] = int(value) if value.is_integer() else value
    return scores


def set_manual_review(data, run_id, style_id, image_selector, scores, notes="", hard_cap=None, override=None):
    write_run_report(data, run_id)
    report = read_report(run_id)
    target = find_review_target(report, style_id, image_selector)
    review = target.get("manualReview") or manual_template()
    review["axes"] = scores
    review["axisMax"] = MANUAL_AXES
    if notes:
        review["notes"] = notes
    if hard_cap is not None:
        review["hardCapApplied"] = optional_score_float(hard_cap, "hardCap")
    if override is not None:
        review["finalScoreOverride"] = optional_score_float(override, "override")
    target["manualReview"] = review
    return write_existing_report(report, run_id)


def optional_float(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid numeric value: {value}") from exc


def optional_score_float(value, field_name):
    parsed = optional_float(value)
    if parsed is None:
        return None
    if parsed < 0 or parsed > 100:
        raise SystemExit(f"{field_name} must be between 0 and 100: {parsed}")
    return int(parsed) if parsed.is_integer() else parsed


def validate_manual_review_csv(data, run_id, csv_path):
    write_run_report(data, run_id)
    report = read_report(run_id)
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise SystemExit(f"Manual review CSV not found: {csv_path}")

    errors = []
    warnings = []
    complete_rows = []
    incomplete_rows = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = set(reader.fieldnames or [])
        required = {"styleId"} | set(MANUAL_AXES.keys())
        missing_columns = sorted(required - fieldnames)
        if "imagePath" not in fieldnames and "imageName" not in fieldnames:
            missing_columns.append("imagePath or imageName")
        if missing_columns:
            errors.append({"line": 1, "reason": "missing columns", "columns": missing_columns})
            return {
                "runId": run_id,
                "source": str(csv_path),
                "valid": False,
                "errorCount": len(errors),
                "warningCount": len(warnings),
                "completeRowCount": 0,
                "incompleteRowCount": 0,
                "errors": errors,
                "warnings": warnings
            }

        for line_number, row in enumerate(reader, start=2):
            style_id = (row.get("styleId") or "").strip()
            image_selector = (row.get("imagePath") or row.get("imageName") or "").strip()
            score_values = [row.get(key, "") for key in MANUAL_AXES]
            row_ref = {"line": line_number, "styleId": style_id, "image": image_selector}
            if not style_id or not image_selector:
                warnings.append({**row_ref, "reason": "missing styleId or image selector; row will be skipped"})
                incomplete_rows.append(row_ref)
                continue
            if any(str(value).strip() == "" for value in score_values):
                warnings.append({**row_ref, "reason": "score columns incomplete; row will be skipped"})
                incomplete_rows.append(row_ref)
                continue
            try:
                parse_review_scores(score_values)
                optional_score_float(row.get("hardCap"), "hardCap")
                optional_score_float(row.get("override"), "override")
                find_review_target(report, style_id, image_selector)
            except SystemExit as exc:
                errors.append({**row_ref, "reason": str(exc)})
                continue
            complete_rows.append(row_ref)

    return {
        "runId": run_id,
        "source": str(csv_path),
        "valid": not errors,
        "errorCount": len(errors),
        "warningCount": len(warnings),
        "completeRowCount": len(complete_rows),
        "incompleteRowCount": len(incomplete_rows),
        "errors": errors,
        "warnings": warnings,
        "completeRows": complete_rows,
        "incompleteRows": incomplete_rows
    }


def write_manual_review_template(data, run_id):
    write_run_report(data, run_id)
    plan = load_generation_plan(data, run_id)
    report = read_report(run_id)
    images_by_path = {}
    for style in report["styles"]:
        for image in style.get("generatedImages", []):
            images_by_path[image["path"]] = image
    out_csv = ROOT / "reports" / f"{run_id}_manual_review_template.csv"
    rows = []
    for row in plan_output_rows(plan):
        image = images_by_path.get(row["outputPath"])
        manual = (image or {}).get("manualReview", {})
        axes = manual.get("axes", {})
        rows.append({
            "styleId": row["styleId"],
            "labelJa": row["labelJa"],
            "variant": row["variant"],
            "variantFocus": row["variantFocus"],
            "imageName": Path(row["outputPath"]).name,
            "imagePath": row["outputPath"],
            "exists": Path(row["outputPath"]).exists(),
            "targetAutomaticScore": "" if image is None else image.get("targetAutomaticScore"),
            "targetRank": "" if image is None else image.get("targetRank"),
            "subjectAdherence": axes.get("subjectAdherence", ""),
            "lineShapeLanguage": axes.get("lineShapeLanguage", ""),
            "textureMediumVisual": axes.get("textureMediumVisual", ""),
            "compositionIntent": axes.get("compositionIntent", ""),
            "stylePurity": axes.get("stylePurity", ""),
            "productionUsefulness": axes.get("productionUsefulness", ""),
            "notes": manual.get("notes", ""),
            "hardCap": "" if manual.get("hardCapApplied") is None else manual.get("hardCapApplied"),
            "override": "" if manual.get("finalScoreOverride") is None else manual.get("finalScoreOverride")
        })
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return out_csv


def apply_manual_review_csv(data, run_id, csv_path):
    validation = validate_manual_review_csv(data, run_id, csv_path)
    if not validation["valid"]:
        return {
            "runId": run_id,
            "source": str(csv_path),
            "appliedCount": 0,
            "skippedCount": 0,
            "applied": [],
            "skipped": [],
            "validation": validation
        }
    write_run_report(data, run_id)
    report = read_report(run_id)
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise SystemExit(f"Manual review CSV not found: {csv_path}")
    applied = []
    skipped = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for line_number, row in enumerate(reader, start=2):
            style_id = (row.get("styleId") or "").strip()
            image_selector = (row.get("imagePath") or row.get("imageName") or "").strip()
            score_values = [row.get(key, "") for key in MANUAL_AXES]
            if not style_id or not image_selector:
                skipped.append({"line": line_number, "reason": "missing styleId or image selector"})
                continue
            if any(str(value).strip() == "" for value in score_values):
                skipped.append({"line": line_number, "styleId": style_id, "image": image_selector, "reason": "score columns incomplete"})
                continue
            scores = parse_review_scores(score_values)
            try:
                target = find_review_target(report, style_id, image_selector)
            except SystemExit as exc:
                skipped.append({"line": line_number, "styleId": style_id, "image": image_selector, "reason": str(exc)})
                continue
            review = target.get("manualReview") or manual_template()
            review["axes"] = scores
            review["axisMax"] = MANUAL_AXES
            review["notes"] = row.get("notes", "")
            hard_cap = optional_score_float(row.get("hardCap"), "hardCap")
            override = optional_score_float(row.get("override"), "override")
            review["hardCapApplied"] = hard_cap
            review["finalScoreOverride"] = override
            target["manualReview"] = review
            applied.append({"line": line_number, "styleId": style_id, "image": image_selector})
    out_json, out_html = write_existing_report(report, run_id)
    refresh = refresh_run(data, run_id)
    return {
        "runId": run_id,
        "source": str(csv_path),
        "appliedCount": len(applied),
        "skippedCount": len(skipped),
        "applied": applied,
        "skipped": skipped,
        "validation": validation,
        "evaluationJson": str(out_json),
        "reviewHtml": str(out_html),
        "refreshStatus": refresh["status"]
    }


def best_image_for_style(style_report):
    images = style_report.get("generatedImages", [])
    if not images:
        return None
    return sorted(
        images,
        key=lambda image: (
            image.get("passed") is True,
            image.get("finalScore") if image.get("finalScore") is not None else -1,
            image.get("targetAutomaticScore", -1)
        ),
        reverse=True
    )[0]


def review_priority_payload(data, run_id):
    report_json, _ = write_run_report(data, run_id)
    report = json.loads(report_json.read_text(encoding="utf-8"))
    plan = load_generation_plan(data, run_id)
    planned_by_style = {}
    for row in plan_output_rows(plan):
        planned_by_style.setdefault(row["styleId"], []).append(row)

    styles = []
    for style in report["styles"]:
        style_id = style["styleId"]
        images = list(style.get("generatedImages", []))
        if images:
            ranked = sorted(
                images,
                key=lambda image: (
                    image.get("passed") is True,
                    image.get("finalScore") is None,
                    image.get("targetRank") == 1,
                    image.get("targetAutomaticScore", -1)
                ),
                reverse=True
            )
            candidates = []
            for index, image in enumerate(ranked, start=1):
                image_name = Path(image["path"]).name
                if image.get("passed"):
                    action = "accepted"
                    reason = "Already passes the 90-point gate."
                elif image.get("finalScore") is None:
                    action = "review"
                    reason = "Best unreviewed candidate by automatic score and target style rank."
                else:
                    action = "iterate"
                    reason = "; ".join(image.get("failureReasons") or ["Reviewed candidate did not pass."])
                candidates.append({
                    "priority": index,
                    "styleId": style_id,
                    "imageName": image_name,
                    "imagePath": image["path"],
                    "action": action,
                    "reason": reason,
                    "targetAutomaticScore": image.get("targetAutomaticScore"),
                    "targetRank": image.get("targetRank"),
                    "targetIsTopStyle": image.get("targetIsTopStyle"),
                    "manualScore": image.get("manualScore"),
                    "finalScore": image.get("finalScore"),
                    "passed": image.get("passed", False),
                    "reviewCommand": (
                        f"python3 scripts/style_eval.py --set-review {run_id} {style_id} {image_name} "
                        "--scores SUBJECT LINE TEXTURE COMPOSITION PURITY USEFULNESS --notes \"\""
                    )
                })
            status = "passed" if any(row["passed"] for row in candidates) else ("review" if any(row["action"] == "review" for row in candidates) else "iterate")
        else:
            candidates = []
            for index, row in enumerate(planned_by_style.get(style_id, []), start=1):
                candidates.append({
                    "priority": index,
                    "styleId": style_id,
                    "imageName": Path(row["outputPath"]).name,
                    "imagePath": row["outputPath"],
                    "action": "generate",
                    "reason": "Planned image is missing.",
                    "variant": row.get("variant"),
                    "variantFocus": row.get("variantFocus", ""),
                    "promptFile": str(ROOT / "prompt_runs" / run_id / "codex_prompts" / codex_prompt_file_name(index, style_id, row["outputPath"]))
                })
            status = "generate"
        styles.append({
            "styleId": style_id,
            "labelJa": style.get("labelJa", style_id),
            "status": status,
            "candidates": candidates
        })

    return {
        "runId": run_id,
        "theme": data["theme"]["ja"],
        "summary": report["summary"],
        "styles": styles,
        "commands": [
            f"python3 scripts/style_eval.py --review-workbench {run_id}",
            f"python3 scripts/style_eval.py --validate-review-csv {run_id} /path/to/{run_id}_manual_review_from_workbench.csv",
            f"python3 scripts/style_eval.py --apply-review-csv {run_id} /path/to/{run_id}_manual_review_from_workbench.csv",
            f"python3 scripts/style_eval.py --gate {run_id}"
        ]
    }


def render_review_priorities_md(payload):
    lines = [
        f"# Review Priorities: {payload['runId']}",
        "",
        f"Theme: {payload['theme']}",
        "",
        "Use this after importing generated images. Review candidates from priority 1 downward for each style; stop when a style passes.",
        "",
        "## Summary",
        "",
        f"- Generated images: {payload['summary']['generatedImageCount']}",
        f"- Reviewed images: {payload['summary']['reviewedImageCount']}",
        f"- Passed styles: {payload['summary']['passedStyleCount']} / {payload['summary']['styleCount']}",
        "",
        "## Commands",
        "",
        "```bash",
        *payload["commands"],
        "```",
        ""
    ]
    for style in payload["styles"]:
        lines.extend([
            f"## {style['labelJa']} / `{style['styleId']}`",
            "",
            f"Status: `{style['status']}`",
            "",
            "| Priority | Action | Image | Auto | Rank | Final | Reason |",
            "|---:|---|---|---:|---:|---:|---|"
        ])
        for row in style["candidates"]:
            lines.append(
                f"| {row['priority']} | `{row['action']}` | `{row['imageName']}` | "
                f"{row.get('targetAutomaticScore', '-')} | {row.get('targetRank', '-')} | "
                f"{row.get('finalScore', '-')} | {row['reason']} |"
            )
        lines.append("")
        for row in style["candidates"]:
            if row.get("reviewCommand"):
                lines.extend(["```bash", row["reviewCommand"], "```", ""])
    return "\n".join(lines)


def write_review_priorities(data, run_id):
    payload = review_priority_payload(data, run_id)
    out_json = ROOT / "reports" / f"{run_id}_review_priorities.json"
    out_md = ROOT / "reports" / f"{run_id}_review_priorities.md"
    write_text_atomic(out_json, json.dumps(payload, ensure_ascii=False, indent=2))
    write_text_atomic(out_md, render_review_priorities_md(payload))
    return out_json, out_md, payload


def operator_checklist_payload(data, run_id):
    loop = loop_state(data, run_id)
    audit = completion_audit(data, run_id)
    status = run_status(data, run_id)
    queue = codex_queue(data, run_id)
    review_priorities_json, review_priorities_md, _ = write_review_priorities(data, run_id)
    gate_report_md, gate_report_html, _ = write_gate_report(data, run_id)
    paths = {
        "projectHub": ROOT / "reports" / f"{run_id}_project_hub.html",
        "dashboard": ROOT / "reports" / f"{run_id}_dashboard.html",
        "codexPack": ROOT / "prompt_runs" / run_id / "codex_image_prompts.md",
        "codexPromptDir": ROOT / "prompt_runs" / run_id / "codex_prompts",
        "reviewPriorities": review_priorities_md,
        "reviewPrioritiesJson": review_priorities_json,
        "reviewWorkbench": ROOT / "reports" / f"{run_id}_review_workbench.html",
        "manualReviewCsv": ROOT / "reports" / f"{run_id}_manual_review_template.csv",
        "reviewGuide": ROOT / "reports" / f"{run_id}_review_guide.md",
        "gateReportMd": gate_report_md,
        "gateReportHtml": gate_report_html
    }
    return {
        "runId": run_id,
        "theme": data["theme"]["ja"],
        "loop": loop,
        "audit": audit,
        "status": status,
        "queue": {
            "expected": queue["expected"],
            "present": queue["present"],
            "missing": queue["missing"]
        },
        "paths": {key: str(value) for key, value in paths.items()}
    }


def render_operator_checklist_md(payload):
    loop = payload["loop"]
    generation = payload["status"]["generation"]
    review = payload["status"]["review"]
    lines = [
        f"# Operator Checklist: {payload['runId']}",
        "",
        f"Theme: {payload['theme']}",
        "",
        "## Current State",
        "",
        f"- Phase: `{loop['phase']}`",
        f"- Next action: {loop['nextAction']}",
        f"- Generated: {generation['present']} present / {generation['missing']} missing / {generation['expected']} expected",
        f"- Reviewed images: {review['reviewedImages']}",
        f"- Passed styles: {review['passedStyles']} / {review['styleCount']}",
        f"- Goal ready: `{payload['audit']['complete']}`",
        "",
        "## Blockers",
        ""
    ]
    if loop["blockers"]:
        lines.extend(f"- [ ] {item}" for item in loop["blockers"])
    else:
        lines.append("- [x] No current blockers.")
    lines.extend([
        "",
        "## Next Commands",
        "",
        "```bash",
        *loop["commands"],
        "```",
        "",
        "## Generation Checklist",
        "",
        "- [ ] Open the Codex prompt pack or prompt files.",
        "- [ ] Generate each planned prompt in Codex/ChatGPT image generation.",
        "- [ ] Save each image using the listed `saveAs` name or accepted sequence stem.",
        "- [ ] Run `--sync-run` with the saved image folder.",
        "",
        "## Review Checklist",
        "",
        "- [ ] Open review priorities and score candidates from priority 1 downward.",
        "- [ ] Open the review workbench and export CSV after entering manual scores.",
        "- [ ] Validate the review CSV before applying it.",
        "- [ ] Apply the review CSV and run the gate.",
        "- [ ] If the gate fails, run `--prepare-next-round` from the gate report.",
        "",
        "## Requirement Audit",
        ""
    ])
    for row in payload["audit"]["requirements"]:
        checked = "x" if row["status"] == "passed" else " "
        lines.extend([
            f"- [{checked}] {row['requirement']} - `{row['status']}`",
            f"  Evidence: {row['evidence']}"
        ])
    lines.extend(["", "## Files", ""])
    for label, path in payload["paths"].items():
        lines.append(f"- {label}: `{path}`")
    lines.append("")
    return "\n".join(lines)


def write_operator_checklist(data, run_id):
    payload = operator_checklist_payload(data, run_id)
    out_md = ROOT / "reports" / f"{run_id}_operator_checklist.md"
    write_text_atomic(out_md, render_operator_checklist_md(payload))
    return out_md, payload


def improvement_constraints_for_style(style, style_report, theme=None):
    best = best_image_for_style(style_report)
    if best is None:
        return [
            "No generated image was found for the previous run. Generate a first candidate with the base prompt before modifying the style.",
            theme_subject_lock_line(theme),
        ]
    if best.get("passed"):
        return [
            f"Previous best already passed at {best.get('finalScore')}/100. Keep this prompt stable; only regenerate if a better variant is needed.",
            f"Previous best image: {best['path']}"
        ]

    constraints = [
        f"Previous best image: {best['path']}",
        f"Previous automatic score: {best['targetAutomaticScore']}/35; target style rank: {best['targetRank']}.",
        theme_subject_lock_line(theme),
    ]
    final_score = best.get("finalScore")
    if final_score is None:
        constraints.append("Manual review is still missing; review the previous image before treating this prompt as validated.")
    else:
        constraints.append(f"Previous final score: {final_score}/100; improve the weakest style axes before regenerating.")

    if not best.get("targetIsTopStyle"):
        top = best["styleRanking"][0]
        constraints.append(f"Target style was not ranked first; it looked closer to {top['styleId']}. Strengthen {style['labelJa']} markers and avoid adjacent-style mixing.")

    for reason in best.get("failureReasons", []):
        constraints.append(f"Pass gate failure to fix: {reason}.")

    constraints.extend(metric_constraints(best))
    constraints.extend(manual_axis_constraints(style, best, theme=theme))
    constraints.extend(style["improvementRules"].values())
    return dedupe(constraints)


def metric_constraints(image):
    out = []
    details = image.get("automaticDetails", {})
    metric_messages = {
        "saturation": ("Color saturation is outside the reference range; tighten the palette and match the style's color intensity.", "Palette/Color"),
        "brightness": ("Overall brightness differs from the references; adjust background value and contrast.", "Palette/Color"),
        "nearWhiteShare": ("Whitespace/background share differs from the references; adjust negative space and filled-area density.", "Composition"),
        "darkShare": ("Black/dark-ink share differs from the references; adjust outline, ink, or dark accent usage.", "Line/Ink"),
        "edgeDensity": ("Line/detail density differs from the references; adjust stroke amount, object count, and contour complexity.", "Line/Shape")
    }
    for key, (message, label) in metric_messages.items():
        row = details.get(key)
        if not row:
            continue
        if row["points"] < row["max"] * 0.8:
            out.append(f"{label}: {message}")
    return out


def manual_axis_constraints(style, image, theme=None):
    manual = image.get("manualReview", {})
    axes = manual.get("axes", {})
    maxes = manual.get("axisMax", MANUAL_AXES)
    messages = {
        "subjectAdherence": theme_manual_subject_hint(theme),
        "lineShapeLanguage": f"Line/shape: strengthen the style fingerprint line and shape rules for {style['labelJa']}.",
        "textureMediumVisual": f"Texture/medium: strengthen the material/process words for {style['labelJa']}.",
        "compositionIntent": f"Composition: match the reference density, whitespace, and layout hierarchy for {style['labelJa']}.",
        "stylePurity": "Style purity: remove terms that invite photorealism, 3D, anime, watercolor realism, or adjacent styles.",
        "productionUsefulness": "Usefulness: keep the result readable as a production-ready illustration, not just a style experiment."
    }
    out = []
    for key, message in messages.items():
        value = axes.get(key)
        max_value = maxes.get(key, MANUAL_AXES[key])
        if isinstance(value, (int, float)) and value < max_value * 0.8:
            out.append(message)
    notes = manual.get("notes")
    if notes:
        out.append(f"Reviewer note to address: {notes}")
    hard_cap = manual.get("hardCapApplied")
    if hard_cap:
        out.append(f"A hard cap of {hard_cap} was applied; remove the underlying disqualifying issue before scoring again.")
    return out


def write_next_round(data, source_run, target_run):
    report = read_report(source_run)
    theme = load_run_theme(data, source_run)
    out_dir = ROOT / "prompt_runs" / target_run
    out_dir.mkdir(parents=True, exist_ok=True)
    style_ids = []
    for style_report in report["styles"]:
        style_id = style_report["styleId"]
        style = resolve_style_record(
            data,
            style_id,
            style_report.get("labelJa", style_id),
        )
        if style is None:
            continue
        style_ids.append(style_id)
        constraints = improvement_constraints_for_style(style, style_report, theme=theme)
        write_style_prompt_file(
            out_dir,
            style,
            style_id,
            theme,
            constraints,
            source_run=source_run,
        )
        (ROOT / "generated" / target_run / style_id).mkdir(parents=True, exist_ok=True)

    source_meta = load_run_meta(source_run)
    if source_meta:
        target_meta = dict(source_meta)
    else:
        target_meta = {
            "subject": theme.get("ja", ""),
            "requiredElements": list(theme.get("mustContain", [])),
            "avoidElements": list(theme.get("mustAvoid", [])),
            "useCase": "",
            "format": "",
            "tone": "",
            "basePromptEn": theme.get("basePromptEn", theme.get("ja", "")),
        }
    target_meta.update({
        "runId": target_run,
        "sourceRun": source_run,
        "styleIds": style_ids,
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    meta_path = out_dir / "run_meta.json"
    write_text_atomic(meta_path, json.dumps(target_meta, ensure_ascii=False, indent=2))
    return out_dir


def source_run_iteration_rows(data, source_run):
    report_json, _ = write_run_report(data, source_run)
    report = json.loads(report_json.read_text(encoding="utf-8"))
    theme = load_run_theme(data, source_run)
    rows = []
    for style_report in report["styles"]:
        style_id = style_report["styleId"]
        style = resolve_style_record(
            data,
            style_id,
            style_report.get("labelJa", style_id),
        )
        if style is None:
            continue
        best = best_image_for_style(style_report)
        rows.append({
            "styleId": style_id,
            "labelJa": style.get("labelJa", style_id),
            "bestImage": None if best is None else best.get("path"),
            "bestFinalScore": None if best is None else best.get("finalScore"),
            "bestAutomaticScore": None if best is None else best.get("targetAutomaticScore"),
            "targetRank": None if best is None else best.get("targetRank"),
            "passed": False if best is None else bool(best.get("passed")),
            "failureReasons": [] if best is None else best.get("failureReasons", []),
            "constraints": improvement_constraints_for_style(style, style_report, theme=theme)
        })
    return rows, report


def render_iteration_plan_md(data, source_run, target_run, variants, rows, source_report):
    lines = [
        f"# Iteration Plan: {source_run} -> {target_run}",
        "",
        f"Theme: {load_run_theme(data, source_run)['ja']}",
        "",
        f"Source status: {source_report['summary']['passedStyleCount']} / {source_report['summary']['styleCount']} styles passed.",
        f"Next run variants: {variants} per style.",
        "",
        "## Next Commands",
        "",
        "```bash",
        f"python3 scripts/style_eval.py --codex-image-pack {target_run}",
        f"python3 scripts/style_eval.py --codex-queue {target_run}",
        f"python3 scripts/style_eval.py --intake-audit {target_run} /path/to/saved/codex/images",
        f"python3 scripts/style_eval.py --import-codex-images {target_run} /path/to/saved/codex/images",
        f"python3 scripts/style_eval.py --refresh-run {target_run}",
        f"python3 scripts/style_eval.py --manual-review-template {target_run}",
        f"python3 scripts/style_eval.py --apply-review-csv {target_run} reports/{target_run}_manual_review_template.csv",
        f"python3 scripts/style_eval.py --gate {target_run}",
        "```",
        "",
        "## Style Actions",
        ""
    ]
    for row in rows:
        lines.extend([
            f"### {row['labelJa']} / `{row['styleId']}`",
            "",
            f"- Best image: `{row['bestImage'] or 'none'}`",
            f"- Best final score: `{row['bestFinalScore'] if row['bestFinalScore'] is not None else 'unreviewed'}`",
            f"- Best automatic score: `{row['bestAutomaticScore'] if row['bestAutomaticScore'] is not None else '-'}`",
            f"- Target rank: `{row['targetRank'] if row['targetRank'] is not None else '-'}`",
            f"- Passed: `{row['passed']}`",
            ""
        ])
        if row["failureReasons"]:
            lines.extend(["Failure reasons:", ""])
            lines.extend(f"- {reason}" for reason in row["failureReasons"])
            lines.append("")
        lines.extend(["Prompt constraints for next run:", ""])
        lines.extend(f"- {constraint}" for constraint in row["constraints"])
        lines.append("")
    return "\n".join(lines)


def prepare_next_round(data, source_run, target_run, variants=3):
    rows, source_report = source_run_iteration_rows(data, source_run)
    prompt_dir = write_next_round(data, source_run, target_run)
    generation_json, generation_md = write_generation_plan(data, target_run, variants)
    codex_pack = write_codex_image_pack(data, target_run)
    generator_shell = write_generator_shell(target_run)
    review_guide = write_review_guide(data, target_run)
    review_workbench = write_review_workbench(data, target_run)
    gate_report_md, gate_report_html, _ = write_gate_report(data, target_run)
    dashboard = write_dashboard(data, target_run)
    project_hub = write_project_hub(data, target_run)
    iteration_plan = ROOT / "prompt_runs" / target_run / "iteration_plan.md"
    write_text_atomic(iteration_plan, render_iteration_plan_md(data, source_run, target_run, variants, rows, source_report))
    intake = intake_audit(data, target_run)
    return {
        "sourceRun": source_run,
        "targetRun": target_run,
        "variantsPerStyle": variants,
        "sourceSummary": source_report["summary"],
        "paths": {
            "promptDir": str(prompt_dir),
            "iterationPlan": str(iteration_plan),
            "generationPlanJson": str(generation_json),
            "generationPlanMd": str(generation_md),
            "codexImagePrompts": str(codex_pack),
            "codexPromptDir": str(ROOT / "prompt_runs" / target_run / "codex_prompts"),
            "generatorShell": str(generator_shell),
            "reviewGuide": str(review_guide),
            "reviewWorkbench": str(review_workbench),
            "gateReportMd": str(gate_report_md),
            "gateReportHtml": str(gate_report_html),
            "dashboard": str(dashboard),
            "projectHub": str(project_hub)
        },
        "intake": {
            "expected": intake["expected"],
            "present": intake["present"],
            "missing": intake["missing"],
            "ready": intake["ready"]
        },
        "styleActions": rows
    }


def prompt_text_from_file(prompt_path, heading):
    text = prompt_path.read_text(encoding="utf-8")
    marker = f"## {heading}"
    start = text.find(marker)
    if start == -1:
        return ""
    start = text.find("\n", start)
    if start == -1:
        return ""
    end = text.find("\n## ", start + 1)
    if end == -1:
        end = len(text)
    return text[start:end].strip()


def prompt_list_from_file(prompt_path, heading):
    block = prompt_text_from_file(prompt_path, heading)
    items = []
    for line in block.splitlines():
        line = line.strip()
        if line.startswith("- "):
            items.append(line[2:].strip())
    return items


def generation_prompt_constraints(constraints):
    meta_prefixes = (
        "Previous best image:",
        "Previous automatic score:",
        "Previous final score:",
        "Previous best already passed",
        "No generated image was found",
        "Manual review is still missing",
        "Keep the fixed subject lock at the start"
    )
    return [
        item
        for item in constraints
        if not any(item.startswith(prefix) for prefix in meta_prefixes)
    ]


def prompt_with_round_constraints(positive, constraints):
    if not constraints:
        return positive
    return positive + ". Additional generation constraints: " + "; ".join(constraints)


def variant_focus(style, index, theme=None):
    fingerprint = style["visualFingerprint"]
    directions = [
        theme_subject_clarity_focus(theme),
        (
            f"composition and palette variant: emphasize {fingerprint['composition']}; preserve {fingerprint['color']}; keep the scene simple and balanced"
        ),
        (
            f"style technique variant: push {fingerprint['line']}; push {fingerprint['texture']}; keep the person treatment as {fingerprint['person']}"
        )
    ]
    if index < len(directions):
        return directions[index]
    return f"additional controlled variant {index + 1}: keep the same style fingerprint while changing only small pose and layout details"


def prompt_with_variant_focus(positive, focus):
    return f"{positive}, {focus}"


def plan_output_rows(plan):
    rows = []
    for job in plan["jobs"]:
        variants = job.get("variants")
        if variants:
            for row in variants:
                rows.append({
                    "runId": plan["runId"],
                    "styleId": job["styleId"],
                    "labelJa": job["labelJa"],
                    "variant": row["variant"],
                    "variantLabel": row.get("variantLabel", ""),
                    "variantFocus": row.get("variantFocus", ""),
                    "positivePrompt": row.get("positivePrompt", job["positivePrompt"]),
                    "negativePrompt": row.get("negativePrompt", job["negativePrompt"]),
                    "outputPath": row["outputPath"]
                })
        else:
            for variant_index, output in enumerate(job["expectedOutputs"], start=1):
                rows.append({
                    "runId": plan["runId"],
                    "styleId": job["styleId"],
                    "labelJa": job["labelJa"],
                    "variant": variant_index,
                    "variantLabel": "",
                    "variantFocus": "",
                    "positivePrompt": job["positivePrompt"],
                    "negativePrompt": job["negativePrompt"],
                    "outputPath": output
                })
    return rows


def write_generation_plan(data, run_id, variants=3):
    out_json = ROOT / "prompt_runs" / run_id / "generation_plan.json"
    out_md = ROOT / "prompt_runs" / run_id / "generation_plan.md"
    out_csv = ROOT / "prompt_runs" / run_id / "generation_jobs.csv"
    (ROOT / "prompt_runs" / run_id).mkdir(parents=True, exist_ok=True)
    theme = load_run_theme(data, run_id)
    jobs = []
    for style in styles_for_run(data, run_id):
        prompt_path = ROOT / "prompt_runs" / run_id / f"{style['id']}.md"
        if not prompt_path.exists():
            raise SystemExit(f"Prompt file not found: {prompt_path}")
        generated_dir = ROOT / "generated" / run_id / style["id"]
        generated_dir.mkdir(parents=True, exist_ok=True)
        positive = prompt_text_from_file(prompt_path, "Positive Prompt")
        negative = prompt_text_from_file(prompt_path, "Negative Prompt")
        round_constraints = prompt_list_from_file(prompt_path, "Round Improvement Constraints")
        generation_constraints = generation_prompt_constraints(round_constraints)
        generation_positive = prompt_with_round_constraints(positive, generation_constraints)
        outputs = []
        variant_rows = []
        for index in range(variants):
            suffix = chr(ord("a") + index)
            output = str(generated_dir / f"round_01_{suffix}.png")
            focus = variant_focus(style, index, theme=theme)
            outputs.append(output)
            variant_rows.append({
                "variant": index + 1,
                "variantLabel": suffix,
                "variantFocus": focus,
                "positivePrompt": prompt_with_variant_focus(generation_positive, focus),
                "negativePrompt": negative,
                "outputPath": output
            })
        jobs.append({
            "styleId": style["id"],
            "labelJa": style["labelJa"],
            "promptPath": str(prompt_path),
            "positivePrompt": generation_positive,
            "basePositivePrompt": positive,
            "negativePrompt": negative,
            "roundImprovementConstraints": round_constraints,
            "generationPromptConstraints": generation_constraints,
            "expectedOutputs": outputs,
            "variants": variant_rows,
            "variantCount": variants
        })
    plan = {
        "runId": run_id,
        "theme": load_run_theme(data, run_id),
        "variantCountPerStyle": variants,
        "expectedImageCount": len(jobs) * variants,
        "jobs": jobs
    }
    write_text_atomic(out_json, json.dumps(plan, ensure_ascii=False, indent=2))
    write_text_atomic(out_md, render_generation_plan_md(plan))
    write_generation_jobs_csv(plan, out_csv)
    return out_json, out_md


def write_generation_jobs_csv(plan, out_csv):
    rows = plan_output_rows(plan)
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return out_csv


def render_generation_plan_md(plan):
    lines = [
        f"# Generation Plan: {plan['runId']}",
        "",
        f"Theme: {plan['theme']['ja']}",
        "",
        f"Expected images: {plan['expectedImageCount']} ({plan['variantCountPerStyle']} per style)",
        "",
        "Generate every listed output before running the review gate.",
        "",
        "Optional external generator shell:",
        "",
        "```bash",
        f"python3 scripts/style_eval.py --export-generator-shell {plan['runId']}",
        "ILLUSTRATION_GENERATOR_CMD='python3 tools/generate.py --prompt \"$positive\" --negative \"$negative\" --out \"$output\"' \\",
        f"  prompt_runs/{plan['runId']}/run_generation_jobs.sh",
        "```",
        "",
        "Codex subscription image generation pack:",
        "",
        "```bash",
        f"python3 scripts/style_eval.py --codex-image-pack {plan['runId']}",
        f"python3 scripts/style_eval.py --codex-queue {plan['runId']}",
        f"python3 scripts/style_eval.py --intake-audit {plan['runId']} /path/to/saved/codex/images",
        f"python3 scripts/style_eval.py --import-codex-images {plan['runId']} /path/to/saved/codex/images",
        "```",
        "",
        "After generation, create visual comparison sheets:",
        "",
        "```bash",
        f"python3 scripts/style_eval.py --codex-queue {plan['runId']}",
        f"python3 scripts/style_eval.py --visual-review {plan['runId']}",
        f"python3 scripts/style_eval.py --review-guide {plan['runId']}",
        "```",
        ""
    ]
    for job in plan["jobs"]:
        lines.extend([
            f"## {job['labelJa']} / `{job['styleId']}`",
            "",
            f"Prompt file: `{job['promptPath']}`",
            "",
            "### Positive Prompt",
            "",
            "```text",
            job["positivePrompt"],
            "```",
            "",
            "### Negative Prompt",
            "",
            "```text",
            job["negativePrompt"],
            "```",
            ""
        ])
        if job.get("roundImprovementConstraints"):
            lines.extend([
                "### Round Improvement Constraints",
                "",
                *[f"- {item}" for item in job["roundImprovementConstraints"]],
                ""
            ])
        if job.get("generationPromptConstraints"):
            lines.extend([
                "### Constraints Included In Generation Prompt",
                "",
                *[f"- {item}" for item in job["generationPromptConstraints"]],
                ""
            ])
        lines.extend([
            "### Save Outputs",
            "",
            ""
        ])
        for row in [r for r in plan_output_rows(plan) if r["styleId"] == job["styleId"]]:
            lines.extend([
                f"#### Variant {row['variant']} / `{Path(row['outputPath']).name}`",
                "",
                f"Focus: {row['variantFocus'] or 'base prompt'}",
                "",
                "```text",
                row["positivePrompt"],
                "```",
                "",
                f"Save to: `{row['outputPath']}`",
                ""
            ])
    return "\n".join(lines)


def write_generator_shell(run_id):
    plan_path = ROOT / "prompt_runs" / run_id / "generation_plan.json"
    if not plan_path.exists():
        raise SystemExit(f"Generation plan not found: {plan_path}. Run --generation-plan {run_id}.")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    out_path = ROOT / "prompt_runs" / run_id / "run_generation_jobs.sh"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        "# ILLUSTRATION_GENERATOR_CMD is evaluated once per planned output.",
        "# Available variables: run_id, style_id, variant, positive, negative, output.",
        ': "${ILLUSTRATION_GENERATOR_CMD:?Set ILLUSTRATION_GENERATOR_CMD, e.g. ILLUSTRATION_GENERATOR_CMD=\'python3 tools/generate.py --prompt \"$positive\" --negative \"$negative\" --out \"$output\"\'}"',
        "",
        "run_job() {",
        '  local run_id="$1"',
        '  local style_id="$2"',
        '  local variant="$3"',
        '  local positive="$4"',
        '  local negative="$5"',
        '  local output="$6"',
        '  mkdir -p "$(dirname "$output")"',
        '  echo "Generating ${run_id}/${style_id} variant ${variant} -> ${output}"',
        '  eval "$ILLUSTRATION_GENERATOR_CMD"',
        '  if [[ ! -s "$output" ]]; then',
        '    echo "Expected generated image was not created or is empty: $output" >&2',
        "    exit 1",
        "  fi",
        "}",
        ""
    ]
    for row in plan_output_rows(plan):
        args = [
            row["runId"],
            row["styleId"],
            str(row["variant"]),
            row["positivePrompt"],
            row["negativePrompt"],
            row["outputPath"]
        ]
        lines.append("run_job " + " ".join(shlex.quote(value) for value in args))
    lines.append("")
    write_text_atomic(out_path, "\n".join(lines))
    out_path.chmod(0o755)
    return out_path


def load_generation_plan(data, run_id):
    plan_path = ROOT / "prompt_runs" / run_id / "generation_plan.json"
    if not plan_path.exists():
        write_generation_plan(data, run_id, 3)
    return json.loads(plan_path.read_text(encoding="utf-8"))


def codex_saved_file_name(style_id, output_path):
    return f"{codex_saved_file_stem(style_id, output_path)}.png"


def codex_saved_file_stem(style_id, output_path):
    return f"{style_id}_{Path(output_path).stem}"


def codex_prompt_text(row, theme=None):
    theme_ja = (theme or {}).get("ja", "").strip()
    if theme_ja:
        subject_lock = f"Keep the subject and required elements exact: {theme_ja}."
    else:
        subject_lock = "Follow the positive prompt subject exactly."
    return "\n".join([
        "Generate a single 2D illustration image.",
        "Do not include any text, logo, watermark, caption, or UI chrome in the image.",
        subject_lock,
        f"Variant focus: {row['variantFocus'] or 'base prompt'}",
        "",
        "Positive prompt:",
        row["positivePrompt"],
        "",
        "Negative constraints:",
        row["negativePrompt"],
        ""
    ])


def codex_prompt_file_name(sequence, style_id, output_path):
    return f"{sequence:02d}_{codex_saved_file_stem(style_id, output_path)}.txt"


def render_codex_image_pack_md(plan):
    lines = [
        f"# Codex Image Generation Pack: {plan['runId']}",
        "",
        "Use these prompts with Codex/ChatGPT image generation under your subscription. Generate one image per prompt, then save it with the exact file name shown under each block.",
        "",
        "If your browser changes download names, the importer also accepts sequence-only names like `01.png`, `02.webp`, or prompt-stem names like `01_naive_wobbly_round_01_a.png`.",
        "",
        "After saving the 15 files into one folder, import them into the evaluation tree:",
        "",
        "```bash",
        f"python3 scripts/style_eval.py --codex-queue {plan['runId']}",
        f"python3 scripts/style_eval.py --intake-audit {plan['runId']} /path/to/saved/codex/images",
        f"python3 scripts/style_eval.py --import-codex-images {plan['runId']} /path/to/saved/codex/images",
        f"python3 scripts/style_eval.py --visual-review {plan['runId']}",
        f"python3 scripts/style_eval.py --report {plan['runId']}",
        "```",
        ""
    ]
    sequence = 1
    for job in plan["jobs"]:
        lines.extend([
            f"## {job['labelJa']} / `{job['styleId']}`",
            ""
        ])
        style_rows = [row for row in plan_output_rows(plan) if row["styleId"] == job["styleId"]]
        for row in style_rows:
            file_name = codex_saved_file_name(row["styleId"], row["outputPath"])
            prompt_file = ROOT / "prompt_runs" / plan["runId"] / "codex_prompts" / codex_prompt_file_name(sequence, row["styleId"], row["outputPath"])
            lines.extend([
                f"### Variant {row['variant']}: `{file_name}`",
                "",
                f"Prompt file: `{prompt_file}`",
                f"Variant focus: {row['variantFocus'] or 'base prompt'}",
                f"Evaluation path after import: `{row['outputPath']}`",
                "",
                "```text",
                codex_prompt_text(row).strip(),
                "```",
                ""
            ])
            sequence += 1
    return "\n".join(lines)


def write_codex_image_pack(data, run_id):
    plan = load_generation_plan(data, run_id)
    out_path = ROOT / "prompt_runs" / run_id / "codex_image_prompts.md"
    write_text_atomic(out_path, render_codex_image_pack_md(plan))
    write_codex_prompt_files(plan)
    return out_path


def write_codex_prompt_files(plan):
    out_dir = ROOT / "prompt_runs" / plan["runId"] / "codex_prompts"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    sequence = 1
    for row in plan_output_rows(plan):
        prompt_path = out_dir / codex_prompt_file_name(sequence, row["styleId"], row["outputPath"])
        saved_file_name = codex_saved_file_name(row["styleId"], row["outputPath"])
        write_text_atomic(prompt_path, codex_prompt_text(row, plan.get("theme")))
        rows.append({
            "sequence": sequence,
            "styleId": row["styleId"],
            "labelJa": row["labelJa"],
            "variant": row["variant"],
            "variantFocus": row["variantFocus"],
            "promptFile": str(prompt_path),
            "saveAs": saved_file_name,
            "acceptedSourceStems": ";".join(codex_accepted_source_stems(sequence, row["styleId"], row["outputPath"])),
            "evaluationPath": row["outputPath"]
        })
        sequence += 1
    manifest_csv = out_dir / "manifest.csv"
    with manifest_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    manifest_md = out_dir / "README.md"
    lines = [
        f"# Codex Prompt Files: {plan['runId']}",
        "",
        "Use one `.txt` file per Codex/ChatGPT image generation. Save each generated image with the matching `saveAs` name.",
        "",
        "The importer also accepts sequence-only filenames such as `01.png`, `02.webp`, or prompt-stem filenames such as `01_naive_wobbly_round_01_a.png`.",
        "",
        "| # | Style | Variant | Focus | Prompt file | Save as | Also accepted stems | Evaluation path |",
        "|---:|---|---:|---|---|---|---|---|"
    ]
    for row in rows:
        lines.append(
            f"| {row['sequence']} | `{row['styleId']}` | {row['variant']} | "
            f"{row['variantFocus']} | `{Path(row['promptFile']).name}` | `{row['saveAs']}` | "
            f"`{row['acceptedSourceStems']}` | `{row['evaluationPath']}` |"
        )
    write_text_atomic(manifest_md, "\n".join(lines))
    return out_dir


def codex_accepted_source_stems(sequence, style_id, output_path):
    expected_stem = codex_saved_file_stem(style_id, output_path)
    stems = [expected_stem]
    if sequence is not None:
        seq2 = f"{sequence:02d}"
        stems.extend([seq2, str(sequence), f"{seq2}_{expected_stem}"])
    return stems


def codex_source_match_reason(path, sequence, style_id, output_path):
    expected_name = codex_saved_file_name(style_id, output_path)
    expected_stem = codex_saved_file_stem(style_id, output_path)
    normalized = unicodedata.normalize("NFC", path.name)
    normalized_stem = unicodedata.normalize("NFC", path.stem)
    if normalized == expected_name or normalized_stem == expected_stem:
        return "expectedSaveName"
    if sequence is not None:
        seq2 = f"{sequence:02d}"
        if normalized_stem == f"{seq2}_{expected_stem}":
            return "promptFileStem"
        if normalized_stem in {seq2, str(sequence)}:
            return "sequenceNumber"
    return None


def find_codex_source_file(source_dir, sequence, style_id, output_path):
    candidates = find_codex_source_candidates(source_dir, sequence, style_id, output_path)
    expected_name = codex_saved_file_name(style_id, output_path)
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        raise SystemExit(f"Ambiguous Codex saved image for {expected_name}: {[str(p) for p in candidates]}")
    return None


def find_codex_source_candidates(source_dir, sequence, style_id, output_path):
    candidates = []
    for path in source_dir.iterdir():
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            if codex_source_match_reason(path, sequence, style_id, output_path):
                candidates.append(path)
    return sorted(candidates, key=lambda p: unicodedata.normalize("NFC", p.name))


def average_hash(path, size=8):
    with Image.open(path) as image:
        gray = ImageOps.grayscale(image).resize((size, size), Image.Resampling.LANCZOS)
        pixel_data = gray.get_flattened_data() if hasattr(gray, "get_flattened_data") else gray.getdata()
        pixels = list(pixel_data)
    mean = sum(pixels) / len(pixels)
    value = 0
    for pixel in pixels:
        value = (value << 1) | (1 if pixel >= mean else 0)
    return f"{value:0{size * size // 4}x}"


def image_probe(path):
    path = Path(path)
    try:
        with Image.open(path) as image:
            width, height = image.size
            mode = image.mode
            image_format = image.format
            image.verify()
        return {
            "readable": True,
            "width": width,
            "height": height,
            "mode": mode,
            "format": image_format,
            "suffix": path.suffix.lower(),
            "hash": average_hash(path)
        }
    except Exception as exc:
        return {
            "readable": False,
            "width": None,
            "height": None,
            "mode": None,
            "format": None,
            "suffix": path.suffix.lower(),
            "hash": None,
            "error": str(exc)
        }


def intake_audit(data, run_id, source_dir=None):
    plan = load_generation_plan(data, run_id)
    source_path = Path(source_dir) if source_dir else None
    if source_path and (not source_path.exists() or not source_path.is_dir()):
        raise SystemExit(f"Source directory not found: {source_path}")

    rows = []
    hash_buckets = {}
    for sequence, row in enumerate(plan_output_rows(plan), start=1):
        evaluation_path = Path(row["outputPath"])
        expected_name = codex_saved_file_name(row["styleId"], row["outputPath"])
        expected_stem = codex_saved_file_stem(row["styleId"], row["outputPath"])
        item = {
            "sequence": sequence,
            "styleId": row["styleId"],
            "labelJa": row["labelJa"],
            "variant": row["variant"],
            "variantLabel": row.get("variantLabel", ""),
            "variantFocus": row.get("variantFocus", ""),
            "expectedFileName": expected_name,
            "expectedStem": expected_stem,
            "acceptedSourceStems": codex_accepted_source_stems(sequence, row["styleId"], row["outputPath"]),
            "evaluationPath": str(evaluation_path),
            "sourcePath": None,
            "sourceCandidates": [],
            "sourceMatchReason": None,
            "present": False,
            "readable": False,
            "width": None,
            "height": None,
            "mode": None,
            "format": None,
            "suffix": None,
            "hash": None,
            "issues": []
        }

        candidate_path = None
        if source_path:
            candidates = find_codex_source_candidates(source_path, sequence, row["styleId"], row["outputPath"])
            item["sourceCandidates"] = [str(path) for path in candidates]
            if len(candidates) == 1:
                candidate_path = candidates[0]
                item["sourcePath"] = str(candidate_path)
                item["sourceMatchReason"] = codex_source_match_reason(candidate_path, sequence, row["styleId"], row["outputPath"])
                item["present"] = True
            elif len(candidates) > 1:
                item["present"] = True
                item["issues"].append("ambiguousSource")
            else:
                item["issues"].append("missing")
        else:
            candidate_path = evaluation_path
            item["present"] = candidate_path.exists()
            if not item["present"]:
                item["issues"].append("missing")

        if candidate_path and candidate_path.exists():
            probe = image_probe(candidate_path)
            item.update({key: probe.get(key) for key in ["readable", "width", "height", "mode", "format", "suffix", "hash"]})
            if not probe["readable"]:
                item["issues"].append("unreadable")
                item["error"] = probe.get("error")
            if probe["readable"] and probe["hash"]:
                hash_buckets.setdefault(probe["hash"], []).append(item)

        if "ambiguousSource" in item["issues"]:
            item["actionNeeded"] = "resolveAmbiguousSource"
        elif "missing" in item["issues"]:
            item["actionNeeded"] = "missing"
        elif "unreadable" in item["issues"]:
            item["actionNeeded"] = "unreadable"
        elif source_path:
            if item["suffix"] and item["suffix"] != evaluation_path.suffix.lower():
                item["actionNeeded"] = "extensionWillConvert"
            else:
                item["actionNeeded"] = "readyToImport"
        else:
            item["actionNeeded"] = "present"
        rows.append(item)

    duplicate_groups = []
    for image_hash, items in sorted(hash_buckets.items()):
        if len(items) < 2:
            continue
        group_rows = []
        for item in items:
            if "duplicateCandidate" not in item["issues"]:
                item["issues"].append("duplicateCandidate")
            item["actionNeeded"] = "duplicateCandidate"
            group_rows.append({
                "styleId": item["styleId"],
                "variant": item["variant"],
                "expectedFileName": item["expectedFileName"],
                "sourcePath": item["sourcePath"],
                "evaluationPath": item["evaluationPath"]
            })
        duplicate_groups.append({"hash": image_hash, "items": group_rows})

    missing_count = sum(1 for item in rows if "missing" in item["issues"])
    unreadable_count = sum(1 for item in rows if "unreadable" in item["issues"])
    ambiguous_count = sum(1 for item in rows if "ambiguousSource" in item["issues"])
    duplicate_item_count = sum(len(group["items"]) for group in duplicate_groups)
    ready = missing_count == 0 and unreadable_count == 0 and ambiguous_count == 0 and not duplicate_groups
    return {
        "runId": run_id,
        "mode": "sourceDir" if source_path else "evaluationTree",
        "sourceDir": str(source_path) if source_path else None,
        "expected": len(rows),
        "present": sum(1 for item in rows if item["present"]),
        "missing": missing_count,
        "unreadable": unreadable_count,
        "ambiguous": ambiguous_count,
        "duplicateGroups": duplicate_groups,
        "duplicateItemCount": duplicate_item_count,
        "ready": ready,
        "rows": rows
    }


def copy_or_convert_image(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == destination.suffix.lower():
        shutil.copy2(source, destination)
        return "copied"
    image = Image.open(source)
    if destination.suffix.lower() == ".png":
        image.convert("RGBA").save(destination)
    else:
        image.convert("RGB").save(destination)
    return "converted"


def import_codex_images(data, run_id, source_dir):
    source_dir = Path(source_dir)
    if not source_dir.exists() or not source_dir.is_dir():
        raise SystemExit(f"Source directory not found: {source_dir}")
    plan = load_generation_plan(data, run_id)
    copied = []
    missing = []
    for sequence, row in enumerate(plan_output_rows(plan), start=1):
        destination = Path(row["outputPath"])
        source = find_codex_source_file(source_dir, sequence, row["styleId"], row["outputPath"])
        expected_name = codex_saved_file_name(row["styleId"], row["outputPath"])
        if source is None:
            missing.append({
                "sequence": sequence,
                "expectedFileName": expected_name,
                "acceptedSourceStems": codex_accepted_source_stems(sequence, row["styleId"], row["outputPath"]),
                "destination": str(destination)
            })
            continue
        action = copy_or_convert_image(source, destination)
        copied.append({
            "sequence": sequence,
            "source": str(source),
            "destination": str(destination),
            "action": action,
            "matchReason": codex_source_match_reason(source, sequence, row["styleId"], row["outputPath"])
        })
    return {
        "runId": run_id,
        "sourceDir": str(source_dir),
        "copiedCount": len(copied),
        "missingCount": len(missing),
        "copied": copied,
        "missing": missing
    }


def codex_queue(data, run_id):
    plan = load_generation_plan(data, run_id)
    write_codex_image_pack(data, run_id)
    rows = []
    sequence = 1
    for row in plan_output_rows(plan):
        prompt_file = ROOT / "prompt_runs" / run_id / "codex_prompts" / codex_prompt_file_name(sequence, row["styleId"], row["outputPath"])
        destination = Path(row["outputPath"])
        rows.append({
            "sequence": sequence,
            "styleId": row["styleId"],
            "variant": row["variant"],
            "variantFocus": row["variantFocus"],
            "promptFile": str(prompt_file),
            "saveAs": codex_saved_file_name(row["styleId"], row["outputPath"]),
            "acceptedSourceStems": codex_accepted_source_stems(sequence, row["styleId"], row["outputPath"]),
            "evaluationPath": str(destination),
            "status": "present" if destination.exists() else "missing"
        })
        sequence += 1
    return {
        "runId": run_id,
        "expected": len(rows),
        "present": sum(1 for row in rows if row["status"] == "present"),
        "missing": sum(1 for row in rows if row["status"] == "missing"),
        "rows": rows
    }


def write_dashboard(data, run_id):
    write_codex_image_pack(data, run_id)
    write_run_report(data, run_id)
    write_review_sheet(data, run_id)
    write_manual_review_template(data, run_id)
    write_visual_review(data, run_id)
    write_review_guide(data, run_id)
    write_review_workbench(data, run_id)
    project_hub = ROOT / "reports" / f"{run_id}_project_hub.html"
    queue = codex_queue(data, run_id)
    report = read_report(run_id)
    out_path = ROOT / "reports" / f"{run_id}_dashboard.html"
    write_text_atomic(out_path, render_dashboard_html(data, run_id, queue, report))
    return out_path


def refresh_run(data, run_id):
    plan = load_generation_plan(data, run_id)
    out_json = ROOT / "prompt_runs" / run_id / "generation_plan.json"
    out_md = ROOT / "prompt_runs" / run_id / "generation_plan.md"
    codex_pack = write_codex_image_pack(data, run_id)
    generator_shell = write_generator_shell(run_id)
    report_json, report_html = write_run_report(data, run_id)
    review_csv, review_md = write_review_sheet(data, run_id)
    manual_review_template = write_manual_review_template(data, run_id)
    visual_index, visual_sheets = write_visual_review(data, run_id)
    review_guide = write_review_guide(data, run_id)
    review_workbench = write_review_workbench(data, run_id)
    review_priorities_json, review_priorities_md, _ = write_review_priorities(data, run_id)
    gate_report_md, gate_report_html, _ = write_gate_report(data, run_id)
    dashboard = write_dashboard(data, run_id)
    project_hub = write_project_hub(data, run_id)
    operator_checklist, _ = write_operator_checklist(data, run_id)
    status = run_status(data, run_id)
    return {
        "runId": run_id,
        "expectedImageCount": plan["expectedImageCount"],
        "paths": {
            "generationPlanJson": str(out_json),
            "generationPlanMd": str(out_md),
            "generationJobsCsv": str(ROOT / "prompt_runs" / run_id / "generation_jobs.csv"),
            "codexImagePrompts": str(codex_pack),
            "codexPromptDir": str(ROOT / "prompt_runs" / run_id / "codex_prompts"),
            "generatorShell": str(generator_shell),
            "evaluationJson": str(report_json),
            "reviewHtml": str(report_html),
            "reviewSheetCsv": str(review_csv),
            "reviewSheetMd": str(review_md),
            "manualReviewTemplateCsv": str(manual_review_template),
            "visualReviewIndex": str(visual_index),
            "visualReviewSheets": [str(path) for path in visual_sheets],
            "reviewGuide": str(review_guide),
            "reviewWorkbench": str(review_workbench),
            "reviewPrioritiesJson": str(review_priorities_json),
            "reviewPrioritiesMd": str(review_priorities_md),
            "gateReportMd": str(gate_report_md),
            "gateReportHtml": str(gate_report_html),
            "dashboard": str(dashboard),
            "projectHub": str(project_hub),
            "operatorChecklist": str(operator_checklist)
        },
        "status": status
    }


def sync_run(data, run_id, source_dir=None):
    result = {
        "runId": run_id,
        "sourceDir": str(source_dir) if source_dir else None,
        "sourceReady": None,
        "imported": None,
        "ok": True
    }

    if source_dir:
        source_audit = intake_audit(data, run_id, source_dir)
        result["sourceAudit"] = {
            key: source_audit[key]
            for key in ["mode", "sourceDir", "expected", "present", "missing", "unreadable", "ambiguous", "duplicateItemCount", "ready"]
        }
        result["sourceReady"] = source_audit["ready"]
        if not source_audit["ready"]:
            result["ok"] = False
            result["imported"] = False
            result["blockingRows"] = [
                {
                    "sequence": row["sequence"],
                    "styleId": row["styleId"],
                    "expectedFileName": row["expectedFileName"],
                    "actionNeeded": row["actionNeeded"],
                    "issues": row["issues"],
                    "sourceCandidates": row["sourceCandidates"],
                    "acceptedSourceStems": row["acceptedSourceStems"]
                }
                for row in source_audit["rows"]
                if row["issues"]
            ]
        else:
            import_result = import_codex_images(data, run_id, source_dir)
            result["imported"] = import_result["missingCount"] == 0
            result["import"] = import_result
            result["ok"] = result["imported"]

    target_audit = intake_audit(data, run_id)
    result["targetAudit"] = {
        key: target_audit[key]
        for key in ["mode", "expected", "present", "missing", "unreadable", "ambiguous", "duplicateItemCount", "ready"]
    }
    result["refresh"] = refresh_run(data, run_id)
    result["loop"] = loop_state(data, run_id)
    result["goalReady"] = result["loop"]["phase"] == "complete"
    return result


def dashboard_image_cell(path):
    path = Path(path)
    if path.exists():
        return f'<img class="candidate-img" src="{html.escape(str(path))}" alt="{html.escape(path.name)}">'
    return '<div class="missing-box">missing</div>'


def dashboard_score_meta(report, row):
    style = next((item for item in report.get("styles", []) if item.get("styleId") == row["styleId"]), None)
    if not style:
        return "No report row"
    image = next((item for item in style.get("generatedImages", []) if item.get("path") == row["evaluationPath"]), None)
    if not image:
        return "Not generated"
    final = "-" if image.get("finalScore") is None else image["finalScore"]
    passed = "passed" if image.get("passed") else "not passed"
    failures = ", ".join(image.get("failureReasons") or [])
    if failures:
        return f'Auto {image["targetAutomaticScore"]}/35, rank {image["targetRank"]}, final {final}, {passed}: {html.escape(failures)}'
    return f'Auto {image["targetAutomaticScore"]}/35, rank {image["targetRank"]}, final {final}, {passed}'


def prompt_builder_payload(data):
    styles = []
    for style in data["styles"]:
        refs = [str(path) for path in iter_reference_images(style)]
        styles.append({
            "id": style["id"],
            "labelJa": style["labelJa"],
            "references": refs,
            "thumbnail": refs[0] if refs else "",
            "fingerprint": style["visualFingerprint"],
            "promptFragments": style["promptFragments"],
            "negativeFragments": style["negativeFragments"],
            "improvementRules": style["improvementRules"]
        })
    return {
        "theme": data["theme"],
        "styles": styles,
        "defaultUseCases": [
            "SaaS LP hero",
            "article hero",
            "SNS campaign",
            "slide deck",
            "help / empty state",
            "brand visual"
        ],
        "defaultFormats": [
            "square thumbnail-readable image",
            "web hero illustration",
            "article header illustration",
            "slide-friendly horizontal image",
            "simple isolated image on light background"
        ]
    }


def render_prompt_builder_html(payload):
    payload_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Illustration Prompt Builder</title>
  <style>
    :root {{ --ink:#17191f; --muted:#667085; --line:#dfe3eb; --bg:#f6f6f1; --panel:#fff; --active:#244fbf; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--ink); background:var(--bg); }}
    header {{ padding:24px 28px 14px; background:#fff; border-bottom:1px solid var(--line); }}
    h1 {{ margin:0 0 8px; font-size:26px; letter-spacing:0; }}
    .lead {{ margin:0; color:var(--muted); font-size:14px; }}
    main {{ max-width:1380px; margin:0 auto; padding:18px; display:grid; grid-template-columns:360px minmax(0,1fr); gap:18px; }}
    section {{ background:#fff; border:1px solid var(--line); border-radius:8px; padding:14px; }}
    h2 {{ margin:0 0 12px; font-size:18px; }}
    label {{ display:block; font-size:12px; font-weight:800; color:#475064; margin:10px 0 5px; }}
    input, textarea, select {{ width:100%; border:1px solid #cfd6e3; border-radius:6px; padding:8px; font:13px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    textarea {{ min-height:76px; resize:vertical; }}
    .styles {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(190px,1fr)); gap:12px; }}
    .style-card {{ border:1px solid var(--line); border-radius:8px; background:#fff; overflow:hidden; cursor:pointer; text-align:left; padding:0; }}
    .style-card.active {{ border-color:var(--active); box-shadow:0 0 0 3px rgba(36,79,191,.12); }}
    .style-card img {{ width:100%; height:128px; object-fit:cover; background:#fff; display:block; }}
    .style-card div {{ padding:10px; }}
    .style-card strong {{ display:block; font-size:14px; margin-bottom:4px; }}
    .style-card small {{ color:var(--muted); }}
    .refs {{ display:flex; gap:6px; overflow:auto; padding:8px 0; }}
    .refs img {{ height:78px; width:92px; object-fit:contain; border:1px solid var(--line); border-radius:5px; background:#fff; flex:0 0 auto; }}
    .fingerprint {{ display:grid; grid-template-columns:100px minmax(0,1fr); gap:5px 8px; margin:8px 0; padding:10px; border:1px solid #eef1f6; border-radius:6px; background:#f8f9fb; font-size:12px; }}
    .fingerprint b {{ color:#38404f; }}
    .outputs {{ display:grid; grid-template-columns:1fr; gap:12px; margin-top:12px; }}
    pre {{ white-space:pre-wrap; overflow-wrap:anywhere; margin:0; padding:12px; border:1px solid var(--line); border-radius:6px; background:#f8f9fb; font:12px ui-monospace,SFMono-Regular,Menlo,monospace; }}
    .actions {{ display:flex; gap:8px; flex-wrap:wrap; margin:10px 0; }}
    button {{ border:1px solid #cfd6e3; background:#fff; border-radius:6px; padding:8px 10px; cursor:pointer; font-weight:800; }}
    button.primary {{ background:#17191f; border-color:#17191f; color:#fff; }}
    .hint {{ color:var(--muted); font-size:12px; margin:8px 0 0; }}
    @media (max-width: 900px) {{ main {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <header>
    <h1>Illustration Prompt Builder</h1>
    <p class="lead">Subject and use case are typed. Style, taste, and technique are filled from reference-backed thumbnail selection.</p>
  </header>
  <main>
    <section>
      <h2>Illustration Form</h2>
      <label for="subject">Subject</label>
      <textarea id="subject"></textarea>
      <label for="required">Required elements</label>
      <textarea id="required"></textarea>
      <label for="avoid">Avoid elements</label>
      <textarea id="avoid"></textarea>
      <label for="usecase">Use case</label>
      <select id="usecase"></select>
      <label for="format">Format</label>
      <select id="format"></select>
      <label for="tone">Tone</label>
      <input id="tone" value="relaxed morning mood, casual, warm, readable at thumbnail size">
      <div class="actions">
        <button class="primary" type="button" id="copyCodex">Copy Codex prompt</button>
        <button type="button" id="copyPositive">Copy positive</button>
        <button type="button" id="copyNegative">Copy negative</button>
      </div>
      <p class="hint">This builder does not call an API. Use the copied prompt in Codex/ChatGPT image generation, then import outputs into the evaluation loop.</p>
    </section>
    <section>
      <h2>Thumbnail Style Selection</h2>
      <div class="styles" id="styles"></div>
      <div id="selected"></div>
      <div class="outputs">
        <div>
          <h2>Codex Prompt</h2>
          <pre id="codexPrompt"></pre>
        </div>
        <div>
          <h2>Variant Focus</h2>
          <pre id="variants"></pre>
        </div>
      </div>
    </section>
  </main>
  <script id="payload" type="application/json">{payload_json}</script>
  <script>
    const payload = JSON.parse(document.getElementById('payload').textContent);
    let selectedStyle = payload.styles[0];
    const subject = document.getElementById('subject');
    const required = document.getElementById('required');
    const avoid = document.getElementById('avoid');
    const usecase = document.getElementById('usecase');
    const format = document.getElementById('format');
    const tone = document.getElementById('tone');
    subject.value = payload.theme.ja;
    required.value = payload.theme.mustContain.join('\\n');
    avoid.value = payload.theme.mustAvoid.join('\\n');
    usecase.innerHTML = payload.defaultUseCases.map(v => `<option>${{escapeHtml(v)}}</option>`).join('');
    format.innerHTML = payload.defaultFormats.map(v => `<option>${{escapeHtml(v)}}</option>`).join('');

    function escapeHtml(value) {{
      return String(value ?? '').replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
    }}
    function listValue(textarea) {{
      return textarea.value.split(/\\n|,/).map(v => v.trim()).filter(Boolean);
    }}
    function dedupe(items) {{
      const seen = new Set();
      return items.filter(item => {{
        const key = item.toLowerCase();
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      }});
    }}
    function buildPositive() {{
      const fragments = dedupe([
        subject.value,
        ...listValue(required).map(item => `must include ${{item}}`),
        `intended use: ${{usecase.value}}`,
        `format: ${{format.value}}`,
        `tone: ${{tone.value}}`,
        ...selectedStyle.promptFragments
      ]);
      return fragments.join(', ');
    }}
    function buildNegative() {{
      return dedupe([...listValue(avoid), ...selectedStyle.negativeFragments, 'text', 'logo', 'watermark']).join(', ');
    }}
    function buildCodexPrompt() {{
      return [
        'Generate a single 2D illustration image.',
        'Do not include any text, logo, watermark, caption, or UI chrome in the image.',
        '',
        'Positive prompt:',
        buildPositive(),
        '',
        'Negative constraints:',
        buildNegative()
      ].join('\\n');
    }}
    function variantText() {{
      const f = selectedStyle.fingerprint;
      return [
        `A / subject clarity: make required elements immediately readable at thumbnail size.`,
        `B / composition and palette: emphasize ${{f.composition}}; preserve ${{f.color}}.`,
        `C / technique and texture: push ${{f.line}}; push ${{f.texture}}; person treatment: ${{f.person}}.`
      ].join('\\n');
    }}
    function renderStyles() {{
      document.getElementById('styles').innerHTML = payload.styles.map(style => `
        <button type="button" class="style-card ${{style.id === selectedStyle.id ? 'active' : ''}}" data-style="${{style.id}}">
          <img src="${{escapeHtml(style.thumbnail)}}" alt="">
          <div><strong>${{escapeHtml(style.labelJa)}}</strong><small>${{escapeHtml(style.id)}}</small></div>
        </button>
      `).join('');
    }}
    function renderSelected() {{
      const f = selectedStyle.fingerprint;
      document.getElementById('selected').innerHTML = `
        <div class="refs">${{selectedStyle.references.map(path => `<img src="${{escapeHtml(path)}}" alt="">`).join('')}}</div>
        <div class="fingerprint">
          ${{Object.entries(f).map(([k,v]) => `<b>${{escapeHtml(k)}}</b><span>${{escapeHtml(v)}}</span>`).join('')}}
        </div>
      `;
      document.getElementById('codexPrompt').textContent = buildCodexPrompt();
      document.getElementById('variants').textContent = variantText();
    }}
    function render() {{
      renderStyles();
      renderSelected();
    }}
    document.addEventListener('click', event => {{
      const card = event.target.closest('[data-style]');
      if (card) {{
        selectedStyle = payload.styles.find(style => style.id === card.dataset.style);
        render();
      }}
      const copyMap = {{
        copyCodex: buildCodexPrompt,
        copyPositive: buildPositive,
        copyNegative: buildNegative
      }};
      if (copyMap[event.target.id]) navigator.clipboard?.writeText(copyMap[event.target.id]());
    }});
    [subject, required, avoid, usecase, format, tone].forEach(el => el.addEventListener('input', renderSelected));
    render();
  </script>
</body>
</html>
"""


def write_prompt_builder(data):
    out_path = ROOT / "reports" / "prompt_builder.html"
    out_path.parent.mkdir(exist_ok=True)
    write_text_atomic(out_path, render_prompt_builder_html(prompt_builder_payload(data)))
    return out_path


def project_hub_payload(data, run_id):
    prompt_builder = write_prompt_builder(data)
    codex_pack = write_codex_image_pack(data, run_id)
    report_json, report_html = write_run_report(data, run_id)
    review_workbench = write_review_workbench(data, run_id)
    review_priorities_json, review_priorities_md, _ = write_review_priorities(data, run_id)
    operator_checklist, _ = write_operator_checklist(data, run_id)
    review_guide = write_review_guide(data, run_id)
    visual_index, _ = write_visual_review(data, run_id)
    queue = codex_queue(data, run_id)
    status = run_status(data, run_id)
    audit = completion_audit(data, run_id)
    loop = loop_state(data, run_id)
    paths = {
        "promptBuilder": prompt_builder,
        "generationPlan": ROOT / "prompt_runs" / run_id / "generation_plan.md",
        "codexPack": codex_pack,
        "codexPromptDir": ROOT / "prompt_runs" / run_id / "codex_prompts",
        "dashboard": ROOT / "reports" / f"{run_id}_dashboard.html",
        "reviewWorkbench": review_workbench,
        "reviewPriorities": review_priorities_md,
        "reviewPrioritiesJson": review_priorities_json,
        "operatorChecklist": operator_checklist,
        "reviewGuide": review_guide,
        "visualReview": visual_index,
        "evaluationJson": report_json,
        "reviewHtml": report_html,
        "manualReviewCsv": ROOT / "reports" / f"{run_id}_manual_review_template.csv"
    }
    return {
        "runId": run_id,
        "theme": data["theme"]["ja"],
        "status": status,
        "audit": audit,
        "loop": loop,
        "queue": queue,
        "paths": {key: str(path) for key, path in paths.items()}
    }


def render_project_hub_html(payload):
    status = payload["status"]
    generation = status["generation"]
    review = status["review"]
    loop = payload["loop"]
    loop_commands = "\n".join(loop["commands"])
    loop_blockers = "".join(f"<li>{html.escape(item)}</li>" for item in loop["blockers"])
    audit_rows = "\n".join(
        f"<tr><td>{html.escape(row['requirement'])}</td><td><span class=\"pill {html.escape(row['status'])}\">{html.escape(row['status'])}</span></td><td>{html.escape(row['evidence'])}</td></tr>"
        for row in payload["audit"]["requirements"]
    )
    job_rows = "\n".join(
        f"<tr><td>{row['sequence']:02d}</td><td>{html.escape(row['styleId'])}</td><td>{html.escape(str(row['variant']))}</td><td><code>{html.escape(row['saveAs'])}</code><br><small>{html.escape(', '.join(row.get('acceptedSourceStems', [])))}</small></td><td><span class=\"pill {html.escape(row['status'])}\">{html.escape(row['status'])}</span></td><td><code>{html.escape(row['promptFile'])}</code></td></tr>"
        for row in payload["queue"]["rows"]
    )
    path_links = "\n".join(
        f"<li><a href=\"{html.escape(path)}\">{html.escape(label)}</a><code>{html.escape(path)}</code></li>"
        for label, path in payload["paths"].items()
    )
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(payload['runId'])} Project Hub</title>
  <style>
    :root {{ --ink:#17191f; --muted:#667085; --line:#dfe3eb; --bg:#f6f6f1; --panel:#fff; --ok:#147a4d; --bad:#a33a2b; --warn:#995c00; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--ink); background:var(--bg); }}
    header {{ padding:28px; background:#fff; border-bottom:1px solid var(--line); }}
    h1 {{ margin:0 0 8px; font-size:28px; letter-spacing:0; }}
    main {{ max-width:1280px; margin:0 auto; padding:18px; }}
    section {{ background:#fff; border:1px solid var(--line); border-radius:8px; padding:16px; margin:14px 0; }}
    h2 {{ margin:0 0 10px; font-size:18px; }}
    .summary {{ display:flex; gap:10px; flex-wrap:wrap; color:var(--muted); font-size:14px; }}
    .stat {{ border:1px solid var(--line); border-radius:8px; padding:10px; background:#fff; min-width:150px; }}
    .stat b {{ display:block; color:var(--ink); font-size:24px; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:10px; }}
    ol {{ margin:0; padding-left:22px; }}
    li {{ margin:8px 0; }}
    a {{ color:#244fbf; text-decoration:none; margin-right:8px; font-weight:700; }}
    code {{ background:#f1f3f8; padding:2px 5px; border-radius:4px; overflow-wrap:anywhere; }}
    table {{ width:100%; border-collapse:collapse; }}
    th,td {{ border-bottom:1px solid var(--line); padding:7px; text-align:left; vertical-align:top; font-size:13px; }}
    th {{ color:#475064; }}
    .pill {{ display:inline-block; border-radius:999px; padding:3px 8px; font-weight:800; font-size:12px; background:#eef1f6; color:#475064; }}
    .pill.passed,.pill.present {{ background:#e9f7ef; color:var(--ok); }}
    .pill.missing,.pill.incomplete {{ background:#fff1f1; color:var(--bad); }}
    .commands {{ white-space:pre-wrap; background:#f8f9fb; border:1px solid var(--line); border-radius:6px; padding:12px; }}
    .phase {{ display:inline-block; margin:8px 0; border:1px solid var(--line); border-radius:8px; padding:8px 10px; background:#f8f9fb; font-weight:800; }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(payload['runId'])} Project Hub</h1>
    <div class="summary"><span>Theme: {html.escape(payload['theme'])}</span><span>Goal ready: {str(payload['audit']['complete']).lower()}</span></div>
  </header>
  <main>
    <section class="grid">
      <div class="stat"><b>{generation['present']}</b>generated present</div>
      <div class="stat"><b>{generation['missing']}</b>generated missing</div>
      <div class="stat"><b>{review['reviewedImages']}</b>reviewed images</div>
      <div class="stat"><b>{review['passedStyles']} / {review['styleCount']}</b>passed styles</div>
    </section>
    <section>
      <h2>Current Loop Step</h2>
      <div class="phase">{html.escape(loop['phase'])}: {html.escape(loop['title'])}</div>
      <p>{html.escape(loop['nextAction'])}</p>
      <ul>{loop_blockers}</ul>
      <pre class="commands">{html.escape(loop_commands)}</pre>
    </section>
    <section>
      <h2>Full Workflow</h2>
      <ol>
        <li>Open Prompt Builder or Codex prompt pack.</li>
        <li>Generate 15 images in Codex/ChatGPT and save them with the listed filenames.</li>
        <li>Run intake audit before import.</li>
        <li>Import images, refresh artifacts, and score candidates in the review workbench.</li>
        <li>Apply the review CSV and run the gate.</li>
        <li>If the gate fails, prepare the next round.</li>
      </ol>
      <pre class="commands">python3 scripts/style_eval.py --loop-status {html.escape(payload['runId'])}
python3 scripts/style_eval.py --operator-checklist {html.escape(payload['runId'])}
python3 scripts/style_eval.py --intake-audit {html.escape(payload['runId'])} /path/to/saved/codex/images
python3 scripts/style_eval.py --import-codex-images {html.escape(payload['runId'])} /path/to/saved/codex/images
python3 scripts/style_eval.py --sync-run {html.escape(payload['runId'])} /path/to/saved/codex/images
python3 scripts/style_eval.py --refresh-run {html.escape(payload['runId'])}
python3 scripts/style_eval.py --review-priorities {html.escape(payload['runId'])}
python3 scripts/style_eval.py --review-workbench {html.escape(payload['runId'])}
python3 scripts/style_eval.py --validate-review-csv {html.escape(payload['runId'])} /path/to/{html.escape(payload['runId'])}_manual_review_from_workbench.csv
python3 scripts/style_eval.py --apply-review-csv {html.escape(payload['runId'])} /path/to/{html.escape(payload['runId'])}_manual_review_from_workbench.csv
python3 scripts/style_eval.py --gate {html.escape(payload['runId'])}</pre>
    </section>
    <section>
      <h2>Files</h2>
      <ul>{path_links}</ul>
    </section>
    <section>
      <h2>Completion Audit</h2>
      <table><thead><tr><th>Requirement</th><th>Status</th><th>Evidence</th></tr></thead><tbody>{audit_rows}</tbody></table>
    </section>
    <section>
      <h2>Codex Generation Queue</h2>
      <table><thead><tr><th>#</th><th>Style</th><th>Variant</th><th>Save As / Accepted Stems</th><th>Status</th><th>Prompt File</th></tr></thead><tbody>{job_rows}</tbody></table>
    </section>
  </main>
</body>
</html>
"""


def write_project_hub(data, run_id):
    out_path = ROOT / "reports" / f"{run_id}_project_hub.html"
    out_path.parent.mkdir(exist_ok=True)
    write_text_atomic(out_path, render_project_hub_html(project_hub_payload(data, run_id)))
    return out_path


def review_workbench_payload(data, run_id, force=False):
    plan = load_generation_plan(data, run_id)
    report_json, _ = write_run_report(data, run_id, force=force)
    report = json.loads(report_json.read_text(encoding="utf-8"))
    images_by_path = {}
    for style_report in report["styles"]:
        for image in style_report.get("generatedImages", []):
            images_by_path[image["path"]] = image

    rows = []
    for row in plan_output_rows(plan):
        style = resolve_style_record(data, row["styleId"], row.get("labelJa", row["styleId"]))
        if style is None:
            continue
        image = images_by_path.get(row["outputPath"], {})
        manual = image.get("manualReview", {})
        rows.append({
            "styleId": row["styleId"],
            "labelJa": row["labelJa"],
            "variant": row["variant"],
            "variantFocus": row["variantFocus"],
            "imageName": Path(row["outputPath"]).name,
            "imagePath": row["outputPath"],
            "exists": Path(row["outputPath"]).exists(),
            "targetAutomaticScore": image.get("targetAutomaticScore"),
            "targetRank": image.get("targetRank"),
            "finalScore": image.get("finalScore"),
            "passed": image.get("passed"),
            "failureReasons": image.get("failureReasons", []),
            "manualAxes": manual.get("axes", {}),
            "notes": manual.get("notes", ""),
            "hardCap": manual.get("hardCapApplied"),
            "override": manual.get("finalScoreOverride"),
            "references": [str(path) for path in iter_reference_images(style)],
            "fingerprint": style["visualFingerprint"],
            "negativeFragments": style["negativeFragments"],
            "maxScores": MANUAL_AXES
        })
    return {
        "runId": run_id,
        "theme": load_run_theme(data, run_id),
        "manualAxes": MANUAL_AXES,
        "passScore": data["globalEvaluation"]["passScore"],
        "csvFileName": f"{run_id}_manual_review_from_workbench.csv",
        "applyCommand": f"python3 scripts/style_eval.py --apply-review-csv {run_id} /path/to/{run_id}_manual_review_from_workbench.csv",
        "rows": rows
    }


def render_review_workbench_html(payload):
    payload_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    axis_headers = "".join(
        f"<th>{html.escape(axis)}<br><small>/{max_score}</small></th>"
        for axis, max_score in MANUAL_AXES.items()
    )
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(payload['runId'])} Review Workbench</title>
  <style>
    :root {{ --ink:#17191f; --muted:#667085; --line:#dfe3eb; --bg:#f6f6f1; --panel:#fff; --ok:#147a4d; --bad:#9d2f2f; --warn:#995c00; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--ink); }}
    header {{ padding:24px 28px 16px; background:#fff; border-bottom:1px solid var(--line); position:sticky; top:0; z-index:3; }}
    h1 {{ margin:0 0 8px; font-size:26px; letter-spacing:0; }}
    .summary {{ display:flex; flex-wrap:wrap; gap:10px; color:var(--muted); font-size:13px; }}
    .toolbar {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; align-items:center; }}
    button {{ border:1px solid #cfd6e3; background:#fff; border-radius:6px; padding:7px 10px; cursor:pointer; font-weight:700; }}
    button.primary {{ background:#17191f; color:#fff; border-color:#17191f; }}
    main {{ max-width:1360px; margin:0 auto; padding:18px; }}
    .job {{ display:grid; grid-template-columns:360px minmax(0,1fr); gap:16px; background:#fff; border:1px solid var(--line); border-radius:8px; padding:14px; margin:14px 0; }}
    .job.missing {{ border-left:5px solid #c9ced8; }}
    .job.present {{ border-left:5px solid var(--ok); }}
    .media h2 {{ margin:0 0 8px; font-size:17px; line-height:1.35; }}
    .candidate {{ width:100%; height:260px; border:1px solid var(--line); border-radius:6px; object-fit:contain; background:#fff; display:block; }}
    .missing-box {{ height:260px; border:1px solid var(--line); border-radius:6px; display:flex; align-items:center; justify-content:center; background:#f7f8fa; color:#777; }}
    .refs {{ display:grid; grid-template-columns:repeat(3,1fr); gap:6px; margin-top:8px; }}
    .refs img {{ width:100%; height:86px; object-fit:contain; border:1px solid var(--line); border-radius:4px; background:#fff; }}
    .meta {{ color:var(--muted); font-size:12px; margin:8px 0; }}
    .fingerprint {{ display:grid; grid-template-columns:110px minmax(0,1fr); gap:4px 8px; font-size:12px; background:#f8f9fb; border:1px solid #eef1f6; border-radius:6px; padding:8px; }}
    .fingerprint b {{ color:#38404f; }}
    table {{ width:100%; border-collapse:collapse; table-layout:fixed; }}
    th,td {{ border-bottom:1px solid var(--line); padding:7px 5px; text-align:left; vertical-align:top; font-size:12px; }}
    th {{ color:#475064; font-weight:800; }}
    input[type="number"] {{ width:100%; min-width:0; padding:7px 5px; border:1px solid #cfd6e3; border-radius:5px; }}
    input[type="text"], textarea {{ width:100%; border:1px solid #cfd6e3; border-radius:5px; padding:7px; font:13px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    textarea {{ min-height:62px; resize:vertical; }}
    .scoreline {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:8px 0; font-size:13px; }}
    .pill {{ border-radius:999px; padding:3px 8px; font-size:12px; font-weight:800; background:#eef1f6; color:#475064; }}
    .pill.pass {{ background:#e9f7ef; color:var(--ok); }}
    .pill.fail {{ background:#fff1f1; color:var(--bad); }}
    .actions {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; }}
    .failures {{ color:var(--bad); font-size:12px; margin:6px 0; }}
    .output {{ width:100%; min-height:110px; margin-top:10px; font:12px ui-monospace,SFMono-Regular,Menlo,monospace; }}
    @media (max-width: 900px) {{ header {{ position:static; }} .job {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(payload['runId'])} Review Workbench</h1>
    <div class="summary">
      <span>Theme: {html.escape(payload['theme']['ja'])}</span>
      <span>Pass score: {payload['passScore']}</span>
      <span>CSV applies with: <code>{html.escape(payload['applyCommand'])}</code></span>
    </div>
    <div class="toolbar">
      <button class="primary" type="button" id="exportCsv">Export CSV text</button>
      <button type="button" id="downloadCsv">Download CSV</button>
      <button type="button" id="fillExisting">Load existing scores</button>
      <button type="button" id="clearDraft">Clear draft</button>
    </div>
  </header>
  <main id="app"></main>
  <template id="scoreTable">
    <table>
      <thead><tr>{axis_headers}<th>notes</th><th>hardCap</th><th>override</th></tr></thead>
      <tbody></tbody>
    </table>
  </template>
  <script id="payload" type="application/json">{payload_json}</script>
  <script>
    const payload = JSON.parse(document.getElementById('payload').textContent);
    const axes = Object.keys(payload.manualAxes);
    const storageKey = `review-workbench:${{payload.runId}}`;
    const draft = JSON.parse(localStorage.getItem(storageKey) || '{{}}');

    function esc(value) {{
      return String(value ?? '').replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
    }}
    function csvCell(value) {{
      const text = String(value ?? '');
      return /[",\\n]/.test(text) ? `"${{text.replace(/"/g, '""')}}"` : text;
    }}
    function rowKey(row) {{ return row.imagePath; }}
    function getDraft(row) {{
      return draft[rowKey(row)] || {{
        ...row.manualAxes,
        notes: row.notes || '',
        hardCap: row.hardCap ?? '',
        override: row.override ?? ''
      }};
    }}
    function saveInput(input) {{
      const key = input.closest('.job').dataset.key;
      draft[key] = draft[key] || {{}};
      draft[key][input.name] = input.value;
      localStorage.setItem(storageKey, JSON.stringify(draft));
    }}
    function render() {{
      const app = document.getElementById('app');
      app.innerHTML = payload.rows.map((row, index) => {{
        const d = getDraft(row);
        const refImgs = row.references.map(path => `<img src="${{esc(path)}}" alt="">`).join('');
        const candidate = row.exists
          ? `<img class="candidate" src="${{esc(row.imagePath)}}" alt="${{esc(row.imageName)}}">`
          : `<div class="missing-box">missing image</div>`;
        const scoreInputs = axes.map(axis => `<td><input type="number" min="0" max="${{payload.manualAxes[axis]}}" step="0.5" name="${{axis}}" value="${{esc(d[axis] ?? '')}}"></td>`).join('');
        const failures = row.failureReasons && row.failureReasons.length ? `<div class="failures">${{esc(row.failureReasons.join(', '))}}</div>` : '';
        return `<section class="job ${{row.exists ? 'present' : 'missing'}}" data-key="${{esc(row.imagePath)}}">
          <div class="media">
            <h2>${{String(index + 1).padStart(2, '0')}}. ${{esc(row.labelJa)}} <code>${{esc(row.imageName)}}</code></h2>
            <div class="meta">variant ${{esc(row.variant)}} / ${{esc(row.variantFocus || 'base prompt')}}</div>
            ${{candidate}}
            <div class="refs">${{refImgs}}</div>
          </div>
          <div>
            <div class="scoreline">
              <span class="pill ${{row.passed ? 'pass' : 'fail'}}">${{row.passed ? 'passed' : 'not passed'}}</span>
              <span>Auto: ${{row.targetAutomaticScore ?? '-' }}/35</span>
              <span>Rank: ${{row.targetRank ?? '-'}}</span>
              <span>Final: ${{row.finalScore ?? '-'}}</span>
            </div>
            ${{failures}}
            <div class="fingerprint">
              ${{Object.entries(row.fingerprint).map(([k,v]) => `<b>${{esc(k)}}</b><span>${{esc(v)}}</span>`).join('')}}
              <b>avoid</b><span>${{esc(row.negativeFragments.join(', '))}}</span>
            </div>
            <table>
              <thead><tr>{axis_headers}<th>notes</th><th>hardCap</th><th>override</th></tr></thead>
              <tbody><tr>${{scoreInputs}}<td><textarea name="notes">${{esc(d.notes ?? '')}}</textarea></td><td><input type="text" name="hardCap" value="${{esc(d.hardCap ?? '')}}"></td><td><input type="text" name="override" value="${{esc(d.override ?? '')}}"></td></tr></tbody>
            </table>
            <div class="actions">
              <button type="button" data-fill-max>Fill max</button>
              <button type="button" data-clear-row>Clear row</button>
            </div>
          </div>
        </section>`;
      }}).join('');
      app.querySelectorAll('input, textarea').forEach(input => input.addEventListener('input', () => saveInput(input)));
    }}
    function buildCsv() {{
      const header = ['styleId','labelJa','variant','variantFocus','imageName','imagePath','exists','targetAutomaticScore','targetRank',...axes,'notes','hardCap','override'];
      const lines = [header.map(csvCell).join(',')];
      for (const row of payload.rows) {{
        const d = getDraft(row);
        const values = [
          row.styleId, row.labelJa, row.variant, row.variantFocus, row.imageName, row.imagePath, row.exists,
          row.targetAutomaticScore ?? '', row.targetRank ?? '',
          ...axes.map(axis => d[axis] ?? ''),
          d.notes ?? '', d.hardCap ?? '', d.override ?? ''
        ];
        lines.push(values.map(csvCell).join(','));
      }}
      return lines.join('\\n') + '\\n';
    }}
    function exportCsv() {{
      const text = buildCsv();
      let box = document.getElementById('csvOutput');
      if (!box) {{
        box = document.createElement('textarea');
        box.id = 'csvOutput';
        box.className = 'output';
        document.querySelector('header').appendChild(box);
      }}
      box.value = text;
      box.select();
      navigator.clipboard?.writeText(text);
    }}
    function downloadCsv() {{
      const blob = new Blob([buildCsv()], {{type: 'text/csv;charset=utf-8'}});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = payload.csvFileName;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    }}
    document.addEventListener('click', event => {{
      const job = event.target.closest('.job');
      if (event.target.id === 'exportCsv') exportCsv();
      if (event.target.id === 'downloadCsv') downloadCsv();
      if (event.target.id === 'fillExisting') {{ localStorage.removeItem(storageKey); location.reload(); }}
      if (event.target.id === 'clearDraft') {{ localStorage.removeItem(storageKey); location.reload(); }}
      if (event.target.matches('[data-fill-max]') && job) {{
        const key = job.dataset.key;
        draft[key] = draft[key] || {{}};
        for (const axis of axes) draft[key][axis] = payload.manualAxes[axis];
        localStorage.setItem(storageKey, JSON.stringify(draft));
        render();
      }}
      if (event.target.matches('[data-clear-row]') && job) {{
        delete draft[job.dataset.key];
        localStorage.setItem(storageKey, JSON.stringify(draft));
        render();
      }}
    }});
    render();
  </script>
</body>
</html>
"""


def write_review_workbench(data, run_id):
    payload = review_workbench_payload(data, run_id)
    out_path = ROOT / "reports" / f"{run_id}_review_workbench.html"
    out_path.parent.mkdir(exist_ok=True)
    write_text_atomic(out_path, render_review_workbench_html(payload))
    return out_path


def render_dashboard_html(data, run_id, queue, report):
    rows_html = []
    styles_by_id = {style["id"]: style for style in data["styles"]}
    project_hub = ROOT / "reports" / f"{run_id}_project_hub.html"
    for row in queue["rows"]:
        prompt_text = Path(row["promptFile"]).read_text(encoding="utf-8") if Path(row["promptFile"]).exists() else ""
        status_class = "present" if row["status"] == "present" else "missing"
        review_command = (
            f"python3 scripts/style_eval.py --set-review {run_id} {row['styleId']} "
            f"{Path(row['evaluationPath']).name} --scores SUBJECT LINE TEXTURE COMPOSITION PURITY USEFULNESS --notes \"\""
        )
        rows_html.append(f"""
        <article class="job {status_class}" id="job-{row['sequence']}">
          <div class="job-media">
            {dashboard_image_cell(row['evaluationPath'])}
          </div>
          <div class="job-main">
            <div class="job-head">
              <h3>{row['sequence']:02d}. {html.escape(styles_by_id[row['styleId']]['labelJa'])} <code>{html.escape(Path(row['evaluationPath']).name)}</code></h3>
              <span class="pill {status_class}">{row['status']}</span>
            </div>
            <p class="focus">{html.escape(row.get('variantFocus') or 'base prompt')}</p>
            <dl>
              <dt>Prompt file</dt><dd><code>{html.escape(row['promptFile'])}</code></dd>
              <dt>Save as</dt><dd><code>{html.escape(row['saveAs'])}</code></dd>
              <dt>Also accepts</dt><dd><code>{html.escape(", ".join(row.get('acceptedSourceStems', [])))}</code></dd>
              <dt>Evaluation</dt><dd><code>{html.escape(row['evaluationPath'])}</code></dd>
              <dt>Score</dt><dd>{dashboard_score_meta(report, row)}</dd>
            </dl>
            <div class="actions">
              <button type="button" data-copy-target="prompt-{row['sequence']}">Copy prompt</button>
              <button type="button" data-copy-value="{html.escape(row['saveAs'])}">Copy filename</button>
              <button type="button" data-copy-value="{html.escape(review_command)}">Copy review command</button>
            </div>
            <textarea id="prompt-{row['sequence']}" readonly>{html.escape(prompt_text)}</textarea>
          </div>
        </article>
        """)

    style_links = []
    for style in data["styles"]:
        visual_sheet = ROOT / "reports" / f"{run_id}_visual_review" / f"{style['id']}.jpg"
        prompt_file = ROOT / "prompt_runs" / run_id / f"{style['id']}.md"
        style_links.append(f"""
          <li>
            <strong>{html.escape(style['labelJa'])}</strong>
            <a href="{html.escape(str(visual_sheet))}">Visual sheet</a>
            <a href="{html.escape(str(prompt_file))}">Prompt</a>
          </li>
        """)

    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(run_id)} Codex Generation Dashboard</title>
  <style>
    :root {{ --ink:#17191f; --muted:#5f6878; --line:#dfe3eb; --bg:#f6f6f1; --panel:#fff; --ok:#1f7a4d; --warn:#9a4c00; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--ink); }}
    header {{ padding:28px 28px 16px; border-bottom:1px solid var(--line); background:#fff; position:sticky; top:0; z-index:2; }}
    h1 {{ margin:0 0 8px; font-size:28px; letter-spacing:0; }}
    .summary {{ display:flex; gap:12px; flex-wrap:wrap; color:var(--muted); font-size:14px; }}
    .summary b {{ color:var(--ink); }}
    main {{ max-width:1180px; margin:0 auto; padding:22px; }}
    .tools {{ display:grid; grid-template-columns:1.2fr .8fr; gap:18px; margin-bottom:18px; }}
    .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; }}
    .panel h2 {{ margin:0 0 10px; font-size:18px; }}
    .commands pre {{ white-space:pre-wrap; margin:0; background:#f1f3f8; border-radius:6px; padding:12px; font-size:13px; }}
    .style-links {{ margin:0; padding-left:18px; }}
    .style-links li {{ margin:7px 0; }}
    a {{ color:#244fbf; text-decoration:none; margin-right:10px; }}
    .job {{ display:grid; grid-template-columns:220px minmax(0,1fr); gap:16px; background:#fff; border:1px solid var(--line); border-radius:8px; padding:14px; margin:14px 0; }}
    .job.present {{ border-left:5px solid var(--ok); }}
    .job.missing {{ border-left:5px solid #c9ced8; }}
    .candidate-img,.missing-box {{ width:220px; height:170px; object-fit:contain; background:#fff; border:1px solid var(--line); border-radius:6px; display:flex; align-items:center; justify-content:center; color:#777; }}
    .missing-box {{ background:#f7f8fa; }}
    .job-head {{ display:flex; justify-content:space-between; gap:12px; align-items:flex-start; }}
    .job h3 {{ margin:0; font-size:17px; line-height:1.35; }}
    code {{ background:#f1f3f8; padding:2px 5px; border-radius:4px; }}
    .pill {{ font-size:12px; border-radius:999px; padding:3px 9px; font-weight:700; }}
    .pill.present {{ color:var(--ok); background:#e9f7ef; }}
    .pill.missing {{ color:#667085; background:#eef1f6; }}
    .focus {{ margin:8px 0; color:#2f3746; font-size:14px; }}
    dl {{ display:grid; grid-template-columns:96px minmax(0,1fr); gap:5px 10px; margin:8px 0; font-size:13px; }}
    dt {{ color:var(--muted); font-weight:700; }}
    dd {{ margin:0; min-width:0; overflow-wrap:anywhere; }}
    .actions {{ display:flex; gap:8px; flex-wrap:wrap; margin:10px 0; }}
    button {{ border:1px solid #cfd6e3; background:#fff; border-radius:6px; padding:7px 10px; cursor:pointer; font-weight:700; }}
    textarea {{ width:100%; min-height:148px; resize:vertical; border:1px solid var(--line); border-radius:6px; padding:10px; font:12px ui-monospace,SFMono-Regular,Menlo,monospace; }}
    @media (max-width: 820px) {{ header {{ position:static; }} .tools,.job {{ grid-template-columns:1fr; }} .candidate-img,.missing-box {{ width:100%; }} }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(run_id)} Codex Generation Dashboard</h1>
    <div class="summary">
      <span><b>{queue['present']}</b> present</span>
      <span><b>{queue['missing']}</b> missing</span>
      <span><b>{report['summary']['passedStyleCount']}</b> passed styles</span>
      <span>Theme: {html.escape(data['theme']['ja'])}</span>
    </div>
  </header>
  <main>
    <div class="tools">
      <section class="panel commands">
        <h2>Next Commands</h2>
        <pre>python3 scripts/style_eval.py --codex-queue {html.escape(run_id)}
python3 scripts/style_eval.py --operator-checklist {html.escape(run_id)}
python3 scripts/style_eval.py --intake-audit {html.escape(run_id)} /path/to/saved/codex/images
python3 scripts/style_eval.py --import-codex-images {html.escape(run_id)} /path/to/saved/codex/images
python3 scripts/style_eval.py --refresh-run {html.escape(run_id)}
python3 scripts/style_eval.py --review-priorities {html.escape(run_id)}
python3 scripts/style_eval.py --review-workbench {html.escape(run_id)}
python3 scripts/style_eval.py --manual-review-template {html.escape(run_id)}
python3 scripts/style_eval.py --validate-review-csv {html.escape(run_id)} reports/{html.escape(run_id)}_manual_review_template.csv
python3 scripts/style_eval.py --apply-review-csv {html.escape(run_id)} reports/{html.escape(run_id)}_manual_review_template.csv</pre>
      </section>
      <section class="panel">
        <h2>Style Links</h2>
        <ul class="style-links">
          {''.join(style_links)}
        </ul>
        <p><a href="{html.escape(str(project_hub))}">Project hub</a><a href="{html.escape(str(ROOT / "reports" / f"{run_id}_review_guide.md"))}">Review guide</a><a href="{html.escape(str(ROOT / "reports" / f"{run_id}_review_sheet.md"))}">Review sheet</a><a href="{html.escape(str(ROOT / "reports" / f"{run_id}_review_workbench.html"))}">Review workbench</a><a href="{html.escape(str(ROOT / "reports" / f"{run_id}_manual_review_template.csv"))}">Manual review CSV</a></p>
      </section>
    </div>
    {''.join(rows_html)}
  </main>
  <script>
    document.addEventListener('click', async (event) => {{
      const button = event.target.closest('button[data-copy-target], button[data-copy-value]');
      if (!button) return;
      const value = button.dataset.copyValue || document.getElementById(button.dataset.copyTarget).value;
      await navigator.clipboard.writeText(value);
      const label = button.textContent;
      button.textContent = 'Copied';
      setTimeout(() => button.textContent = label, 900);
    }});
  </script>
</body>
</html>
"""


def check_generation_plan(run_id):
    plan_path = ROOT / "prompt_runs" / run_id / "generation_plan.json"
    if not plan_path.exists():
        raise SystemExit(f"Generation plan not found: {plan_path}. Run --generation-plan {run_id}.")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    missing = []
    present = []
    for job in plan["jobs"]:
        for output in job["expectedOutputs"]:
            path = Path(output)
            if path.exists():
                present.append(str(path))
            else:
                missing.append(str(path))
    return {
        "runId": run_id,
        "expectedImageCount": plan["expectedImageCount"],
        "presentImageCount": len(present),
        "missingImageCount": len(missing),
        "ready": not missing,
        "present": present,
        "missing": missing
    }


def run_status(data, run_id):
    plan_path = ROOT / "prompt_runs" / run_id / "generation_plan.json"
    if not plan_path.exists():
        write_generation_plan(data, run_id, 3)
    generation = check_generation_plan(run_id)
    report_json, _ = write_run_report(data, run_id)
    report = json.loads(report_json.read_text(encoding="utf-8"))
    return {
        "runId": run_id,
        "generation": {
            "expected": generation["expectedImageCount"],
            "present": generation["presentImageCount"],
            "missing": generation["missingImageCount"],
            "ready": generation["ready"]
        },
        "review": {
            "generatedImages": report["summary"]["generatedImageCount"],
            "reviewedImages": report["summary"]["reviewedImageCount"],
            "passedStyles": report["summary"]["passedStyleCount"],
            "styleCount": report["summary"]["styleCount"],
            "allStylesPassed": report["summary"]["allStylesPassed"]
        },
        "missingStyles": report["summary"]["missingStyles"],
        "pendingReviewStyles": report["summary"]["pendingReviewStyles"],
        "failedStyles": report["summary"]["failedStyles"]
    }


def write_review_sheet(data, run_id):
    write_run_report(data, run_id)
    plan_path = ROOT / "prompt_runs" / run_id / "generation_plan.json"
    if not plan_path.exists():
        write_generation_plan(data, run_id, 3)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    report = read_report(run_id)
    images_by_path = {}
    for style in report["styles"]:
        for image in style.get("generatedImages", []):
            images_by_path[image["path"]] = image

    out_csv = ROOT / "reports" / f"{run_id}_review_sheet.csv"
    out_md = ROOT / "reports" / f"{run_id}_review_sheet.md"
    rows = []
    for row in plan_output_rows(plan):
        output = row["outputPath"]
        image = images_by_path.get(output)
        command = (
            f"python3 scripts/style_eval.py --set-review {run_id} {row['styleId']} "
            f"{Path(output).name} --scores SUBJECT LINE TEXTURE COMPOSITION PURITY USEFULNESS "
            f"--notes \"\""
        )
        rows.append({
            "styleId": row["styleId"],
            "labelJa": row["labelJa"],
            "variant": row["variant"],
            "variantFocus": row["variantFocus"],
            "imagePath": output,
            "exists": Path(output).exists(),
            "targetAutomaticScore": "" if image is None else image.get("targetAutomaticScore"),
            "targetRank": "" if image is None else image.get("targetRank"),
            "finalScore": "" if image is None else image.get("finalScore"),
            "passed": "" if image is None else image.get("passed"),
            "reviewCommandTemplate": command
        })

    out_csv.parent.mkdir(exist_ok=True)
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    write_text_atomic(out_md, render_review_sheet_md(run_id, rows))
    return out_csv, out_md


def default_font(size=14):
    candidates = [
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf"
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def wrap_text_for_draw(draw, text, font, max_width, max_lines=3):
    words = str(text).replace("\n", " ").split()
    if not words:
        return [""]
    lines = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
        if len(lines) == max_lines:
            break
    if len(lines) < max_lines and current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    if words and len(" ".join(words)) > len(" ".join(lines)):
        lines[-1] = lines[-1].rstrip(".") + "..."
    return lines


def image_tile(path, label, meta="", exists=True):
    width = SHEET_TILE_WIDTH
    height = SHEET_TILE_HEIGHT + SHEET_LABEL_HEIGHT
    tile = Image.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(tile)
    font = default_font(13)
    small_font = default_font(11)
    image_box = (0, 0, width, SHEET_TILE_HEIGHT)
    draw.rectangle(image_box, fill="#f7f8fa", outline="#d8dde8")
    if exists and path.exists():
        try:
            im = Image.open(path).convert("RGBA")
            fitted = ImageOps.contain(im, (width - 16, SHEET_TILE_HEIGHT - 16))
            bg = Image.new("RGBA", (width - 16, SHEET_TILE_HEIGHT - 16), "#ffffff")
            x = (bg.width - fitted.width) // 2
            y = (bg.height - fitted.height) // 2
            bg.alpha_composite(fitted, (x, y))
            tile.paste(bg.convert("RGB"), (8, 8))
        except OSError:
            exists = False
    if not exists or not path.exists():
        draw.rectangle((12, 12, width - 12, SHEET_TILE_HEIGHT - 12), outline="#aeb6c6", width=2)
        draw.line((18, 18, width - 18, SHEET_TILE_HEIGHT - 18), fill="#ccd2de", width=2)
        draw.line((width - 18, 18, 18, SHEET_TILE_HEIGHT - 18), fill="#ccd2de", width=2)
        draw.text((18, SHEET_TILE_HEIGHT // 2 - 8), "missing image", fill="#6c7586", font=font)
    label_y = SHEET_TILE_HEIGHT + 8
    for line in wrap_text_for_draw(draw, label, font, width - 16, max_lines=2):
        draw.text((8, label_y), line, fill="#17191f", font=font)
        label_y += 16
    if meta:
        for line in wrap_text_for_draw(draw, meta, small_font, width - 16, max_lines=1):
            draw.text((8, label_y + 2), line, fill="#586174", font=small_font)
    return tile


def generated_review_meta(report, style_id, output_path):
    style = next((row for row in report.get("styles", []) if row.get("styleId") == style_id), None)
    if not style:
        return ""
    image = next((row for row in style.get("generatedImages", []) if row.get("path") == output_path), None)
    if not image:
        return "not generated"
    final = "final: -" if image.get("finalScore") is None else f"final: {image['finalScore']}"
    return f"auto: {image['targetAutomaticScore']}/35 rank: {image['targetRank']} {final}"


def draw_sheet_section(canvas, y, title, tiles, columns, heading_font):
    draw = ImageDraw.Draw(canvas)
    draw.text((SHEET_MARGIN, y), title, fill="#17191f", font=heading_font)
    y += 34
    for index, tile in enumerate(tiles):
        col = index % columns
        row = index // columns
        x = SHEET_MARGIN + col * (SHEET_TILE_WIDTH + SHEET_GAP)
        tile_y = y + row * (SHEET_TILE_HEIGHT + SHEET_LABEL_HEIGHT + SHEET_GAP)
        canvas.paste(tile, (x, tile_y))
    rows = max(1, (len(tiles) + columns - 1) // columns)
    return y + rows * (SHEET_TILE_HEIGHT + SHEET_LABEL_HEIGHT + SHEET_GAP) + 18


def render_style_visual_sheet(style, job, report):
    columns = 3
    width = SHEET_MARGIN * 2 + columns * SHEET_TILE_WIDTH + (columns - 1) * SHEET_GAP
    ref_paths = iter_reference_images(style)
    generated_paths = [Path(path) for path in job["expectedOutputs"]]
    ref_rows = max(1, (len(ref_paths) + columns - 1) // columns)
    gen_rows = max(1, (len(generated_paths) + columns - 1) // columns)
    header_height = 88
    section_heading_height = 52
    tile_full_height = SHEET_TILE_HEIGHT + SHEET_LABEL_HEIGHT + SHEET_GAP
    height = (
        SHEET_MARGIN
        + header_height
        + section_heading_height + ref_rows * tile_full_height
        + section_heading_height + gen_rows * tile_full_height
        + SHEET_MARGIN
    )
    canvas = Image.new("RGB", (width, height), "#f5f6f2")
    draw = ImageDraw.Draw(canvas)
    title_font = default_font(24)
    heading_font = default_font(18)
    small_font = default_font(12)
    draw.text((SHEET_MARGIN, SHEET_MARGIN), f"{style['labelJa']} / {style['id']}", fill="#17191f", font=title_font)
    draw.text((SHEET_MARGIN, SHEET_MARGIN + 34), "References vs generated candidates for visual style reproduction review.", fill="#586174", font=small_font)
    y = SHEET_MARGIN + header_height
    ref_tiles = [
        image_tile(path, path.name, "reference", exists=True)
        for path in ref_paths
    ]
    y = draw_sheet_section(canvas, y, f"Reference images ({len(ref_tiles)})", ref_tiles, columns, heading_font)
    generated_tiles = [
        image_tile(
            path,
            path.name,
            generated_review_meta(report, style["id"], str(path)),
            exists=path.exists()
        )
        for path in generated_paths
    ]
    draw_sheet_section(canvas, y, f"Generated candidates ({len(generated_tiles)})", generated_tiles, columns, heading_font)
    return canvas


def write_visual_review(data, run_id):
    plan_path = ROOT / "prompt_runs" / run_id / "generation_plan.json"
    if not plan_path.exists():
        write_generation_plan(data, run_id, 3)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    report_json, _ = write_run_report(data, run_id)
    report = json.loads(report_json.read_text(encoding="utf-8"))
    styles_by_id = {style["id"]: style for style in data["styles"]}
    out_dir = ROOT / "reports" / f"{run_id}_visual_review"
    out_dir.mkdir(parents=True, exist_ok=True)
    sheet_paths = []
    for job in plan["jobs"]:
        style = styles_by_id[job["styleId"]]
        sheet = render_style_visual_sheet(style, job, report)
        out_path = out_dir / f"{style['id']}.jpg"
        sheet.save(out_path, quality=92)
        sheet_paths.append(out_path)
    index_path = out_dir / "index.md"
    write_text_atomic(index_path, render_visual_review_index(run_id, sheet_paths))
    return index_path, sheet_paths


def render_visual_review_index(run_id, sheet_paths):
    lines = [
        f"# Visual Review Sheets: {run_id}",
        "",
        "Compare the local reference images against the planned generated candidates before entering manual review scores.",
        "",
        "After real generation, rerun:",
        "",
        "```bash",
        f"python3 scripts/style_eval.py --visual-review {run_id}",
        "```",
        ""
    ]
    for path in sheet_paths:
        lines.extend([
            f"## `{path.stem}`",
            "",
            f"![{path.stem}]({path})",
            ""
        ])
    return "\n".join(lines)


def score_axis_guidance(data, style, theme=None):
    theme = theme or data.get("theme", {})
    fingerprint = style["visualFingerprint"]
    return {
        "subjectAdherence": theme_subject_adherence_messages(theme),
        "lineShapeLanguage": [
            f"Line: {fingerprint['line']}",
            f"Shape: {fingerprint['shape']}",
            f"Person treatment: {fingerprint['person']}",
            f"Style weight lineEdge={style['styleScoringWeights']['lineEdge']}, shapeLanguage={style['styleScoringWeights']['shapeLanguage']}"
        ],
        "textureMediumVisual": [
            f"Texture/medium: {fingerprint['texture']}",
            f"Color behavior: {fingerprint['color']}",
            f"Style weight textureMedium={style['styleScoringWeights']['textureMedium']}, palette={style['styleScoringWeights']['palette']}"
        ],
        "compositionIntent": [
            *theme_composition_messages(theme, fingerprint),
            f"Style weight composition={style['styleScoringWeights']['composition']}",
        ],
        "stylePurity": [
            "Do not reward a good-looking image if it drifts into an adjacent style.",
            "Negative markers: " + ", ".join(style["negativeFragments"]),
            "Global avoid list: " + ", ".join(theme.get("mustAvoid", data["theme"].get("mustAvoid", [])))
        ],
        "productionUsefulness": theme_production_usefulness_messages(theme)
    }


def render_review_guide_md(data, run_id):
    plan_path = ROOT / "prompt_runs" / run_id / "generation_plan.json"
    if not plan_path.exists():
        write_generation_plan(data, run_id, 3)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    theme = load_run_theme(data, run_id)
    styles_by_id = {style["id"]: style for style in data["styles"]}
    jobs_by_style = {job["styleId"]: job for job in plan["jobs"]}
    lines = [
        f"# Review Guide: {run_id}",
        "",
        f"Theme: {theme.get('ja', '')}",
        "",
        "Use this guide with the visual review sheets and the review sheet before entering manual scores.",
        "",
        "Score order:",
        "",
        "```text",
        "subjectAdherence lineShapeLanguage textureMediumVisual compositionIntent stylePurity productionUsefulness",
        "```",
        "",
        "Max scores:",
        "",
        "```text",
        "15 15 15 8 10 2",
        "```",
        "",
        "Hard caps:",
        "",
        *[f"- `{key}`: {value}" for key, value in data["globalEvaluation"]["hardCaps"].items()],
        "",
        "Minimum axes for pass:",
        "",
        *[f"- `{key}`: {value} / {MANUAL_AXES[key]}" for key, value in PASS_AXIS_MINIMUMS.items()],
        ""
    ]
    for style in data["styles"]:
        job = jobs_by_style[style["id"]]
        baseline = baseline_for_style(style)
        guide = score_axis_guidance(data, style, theme=theme)
        visual_sheet = ROOT / "reports" / f"{run_id}_visual_review" / f"{style['id']}.jpg"
        lines.extend([
            f"## {style['labelJa']} / `{style['id']}`",
            "",
            f"Visual sheet: `{visual_sheet}`",
            f"Prompt file: `{job['promptPath']}`",
            "",
            "### Reference Metric Range",
            "",
            "| Metric | Mean | Min | Max |",
            "|---|---:|---:|---:|"
        ])
        for metric, values in baseline["metrics"].items():
            lines.append(f"| `{metric}` | {values['mean']} | {values['min']} | {values['max']} |")
        lines.extend([
            "",
            "### Manual Axis Checklist",
            ""
        ])
        for axis, max_value in MANUAL_AXES.items():
            lines.extend([
                f"#### `{axis}` / {max_value}",
                "",
                *[f"- {item}" for item in guide[axis]],
                ""
            ])
        lines.extend([
            "### Improvement Rules",
            "",
            *[f"- `{key}`: {value}" for key, value in style["improvementRules"].items()],
            "",
            "### Candidate Review Commands",
            ""
        ])
        for output in job["expectedOutputs"]:
            lines.extend([
                "```bash",
                f"python3 scripts/style_eval.py --set-review {run_id} {style['id']} {Path(output).name} --scores SUBJECT LINE TEXTURE COMPOSITION PURITY USEFULNESS --notes \"\"",
                "```",
                ""
            ])
    return "\n".join(lines)


def write_review_guide(data, run_id):
    out_path = ROOT / "reports" / f"{run_id}_review_guide.md"
    out_path.parent.mkdir(exist_ok=True)
    write_text_atomic(out_path, render_review_guide_md(data, run_id))
    return out_path


def render_review_sheet_md(run_id, rows):
    lines = [
        f"# Review Sheet: {run_id}",
        "",
        "Score order:",
        "",
        "```text",
        "subjectAdherence lineShapeLanguage textureMediumVisual compositionIntent stylePurity productionUsefulness",
        "```",
        "",
        "Max scores:",
        "",
        "```text",
        "15 15 15 8 10 2",
        "```",
        ""
    ]
    for row in rows:
        status = "present" if row["exists"] else "missing"
        lines.extend([
            f"## {row['labelJa']} / `{row['styleId']}` / `{Path(row['imagePath']).name}`",
            "",
            f"Variant: `{row.get('variant', '')}`",
            f"Focus: {row.get('variantFocus', '') or 'base prompt'}",
            f"Image: `{row['imagePath']}`",
            f"Status: `{status}`",
            f"Auto: `{row['targetAutomaticScore']}` / Target rank: `{row['targetRank']}` / Final: `{row['finalScore']}` / Passed: `{row['passed']}`",
            "",
            "```bash",
            row["reviewCommandTemplate"],
            "```",
            ""
        ])
    return "\n".join(lines)


def completion_audit(data, run_id):
    manifest_path = ROOT / "reports" / "reference_manifest.json"
    if not manifest_path.exists():
        write_reference_analysis(data)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    plan_path = ROOT / "prompt_runs" / run_id / "generation_plan.json"
    if not plan_path.exists():
        write_generation_plan(data, run_id, 3)
    generation_status = check_generation_plan(run_id)
    report_json, _ = write_run_report(data, run_id)
    report = json.loads(report_json.read_text(encoding="utf-8"))
    summary = report["summary"]
    requirements = [
        {
            "requirement": "37 reference images are analyzed",
            "status": "passed" if manifest["referenceCount"] == 37 else "failed",
            "evidence": f"reports/reference_manifest.json referenceCount={manifest['referenceCount']}"
        },
        {
            "requirement": "five target style groups are represented",
            "status": "passed" if len(manifest["styles"]) == 5 else "failed",
            "evidence": f"style groups={[(s['styleId'], s['referenceCount']) for s in manifest['styles']]}"
        },
        {
            "requirement": "generation plan exists for the fixed coffee-walk theme",
            "status": "passed",
            "evidence": str(plan_path)
        },
        {
            "requirement": "planned generated images are present",
            "status": "passed" if generation_status["ready"] else "missing",
            "evidence": f"{generation_status['presentImageCount']} present / {generation_status['missingImageCount']} missing"
        },
        {
            "requirement": "all generated images are reviewed and at least one per style passes",
            "status": "passed" if summary["allStylesPassed"] else "incomplete",
            "evidence": json.dumps(summary, ensure_ascii=False)
        },
        {
            "requirement": "goal gate exits successfully",
            "status": "passed" if run_passes(report) else "incomplete",
            "evidence": f"python3 scripts/style_eval.py --gate {run_id}"
        }
    ]
    return {
        "runId": run_id,
        "complete": all(row["status"] == "passed" for row in requirements),
        "requirements": requirements
    }


def loop_state(data, run_id):
    report_json, _ = write_run_report(data, run_id)
    report = json.loads(report_json.read_text(encoding="utf-8"))
    summary = report["summary"]
    next_run = next_run_id(run_id)

    if run_passes(report):
        commands = [f"python3 scripts/style_eval.py --gate {run_id}"]
        if (ROOT / "prompt_runs" / run_id / "generation_plan.json").exists():
            commands.append(f"python3 scripts/style_eval.py --audit {run_id}")
        return {
            "runId": run_id,
            "phase": "complete",
            "title": "90-point gate passed",
            "nextAction": "Keep the accepted candidates and archive the run artifacts.",
            "blockers": [],
            "commands": commands,
            "summary": summary
        }

    generation = check_generation_plan(run_id)
    intake = intake_audit(data, run_id)

    if generation["missingImageCount"]:
        return {
            "runId": run_id,
            "phase": "generate",
            "title": "Generate missing Codex images",
            "nextAction": "Generate every planned prompt in Codex/ChatGPT image generation, save the files, audit the download folder, then import them.",
            "blockers": [
                f"{generation['missingImageCount']} planned images are missing.",
                "The 90-point gate cannot run until generated images exist."
            ],
            "commands": [
                f"python3 scripts/style_eval.py --operator-checklist {run_id}",
                f"python3 scripts/style_eval.py --project-hub {run_id}",
                f"python3 scripts/style_eval.py --codex-queue {run_id}",
                f"python3 scripts/style_eval.py --sync-run {run_id} /path/to/saved/codex/images",
                f"python3 scripts/style_eval.py --intake-audit {run_id} /path/to/saved/codex/images",
                f"python3 scripts/style_eval.py --import-codex-images {run_id} /path/to/saved/codex/images",
                f"python3 scripts/style_eval.py --refresh-run {run_id}"
            ],
            "summary": summary
        }

    if not intake["ready"]:
        blockers = []
        if intake["unreadable"]:
            blockers.append(f"{intake['unreadable']} generated images are unreadable.")
        if intake["ambiguous"]:
            blockers.append(f"{intake['ambiguous']} generated images have ambiguous source matches.")
        if intake["duplicateItemCount"]:
            blockers.append(f"{intake['duplicateItemCount']} generated images are duplicate candidates.")
        return {
            "runId": run_id,
            "phase": "fixImportedImages",
            "title": "Fix imported image audit issues",
            "nextAction": "Resolve unreadable, ambiguous, or duplicate generated files before scoring.",
            "blockers": blockers or ["Imported image audit is not ready."],
            "commands": [
                f"python3 scripts/style_eval.py --operator-checklist {run_id}",
                f"python3 scripts/style_eval.py --intake-audit {run_id}",
                f"python3 scripts/style_eval.py --refresh-run {run_id}"
            ],
            "summary": summary
        }

    if summary["reviewedImageCount"] < summary["generatedImageCount"] or summary["pendingReviewStyles"]:
        return {
            "runId": run_id,
            "phase": "review",
            "title": "Enter manual review scores",
            "nextAction": "Open the review workbench, score candidates against the style guide, export CSV, then apply it.",
            "blockers": [
                f"{summary['generatedImageCount'] - summary['reviewedImageCount']} generated images still need manual scores.",
                f"Pending styles: {', '.join(summary['pendingReviewStyles']) or 'none'}"
            ],
            "commands": [
                f"python3 scripts/style_eval.py --operator-checklist {run_id}",
                f"python3 scripts/style_eval.py --review-workbench {run_id}",
                f"python3 scripts/style_eval.py --review-priorities {run_id}",
                f"python3 scripts/style_eval.py --validate-review-csv {run_id} /path/to/{run_id}_manual_review_from_workbench.csv",
                f"python3 scripts/style_eval.py --apply-review-csv {run_id} /path/to/{run_id}_manual_review_from_workbench.csv",
                f"python3 scripts/style_eval.py --sync-run {run_id}",
                f"python3 scripts/style_eval.py --gate {run_id}"
            ],
            "summary": summary
        }

    return {
        "runId": run_id,
        "phase": "iterate",
        "title": "Prepare next prompt round",
        "nextAction": "The current reviewed candidates did not pass every style. Use the gate report failures to create the next Codex prompt round.",
        "blockers": [
            f"Passed styles: {summary['passedStyleCount']} / {summary['styleCount']}.",
            f"Failed styles: {', '.join(summary['failedStyles']) or 'none'}",
            f"Missing styles: {', '.join(summary['missingStyles']) or 'none'}"
        ],
        "commands": [
            f"python3 scripts/style_eval.py --operator-checklist {run_id}",
            f"python3 scripts/style_eval.py --gate-report {run_id}",
            f"python3 scripts/style_eval.py --prepare-next-round {run_id} {next_run} --variants 3",
            f"python3 scripts/style_eval.py --project-hub {next_run}"
        ],
        "summary": summary
    }


def gate_action_for_style(style_report):
    style_id = style_report["styleId"]
    images = style_report.get("generatedImages", [])
    if not images:
        return {
            "styleId": style_id,
            "status": "missing",
            "bestImage": None,
            "nextAction": "Generate the planned Codex variants for this style, then import them.",
            "commandHint": f"Open prompt_runs/{{run_id}}/codex_prompts and generate the {style_id} prompt files."
        }
    best = best_image_for_style(style_report)
    if best.get("passed"):
        return {
            "styleId": style_id,
            "status": "passed",
            "bestImage": best["path"],
            "nextAction": "Keep this image as the accepted candidate for this style.",
            "commandHint": ""
        }
    if best.get("finalScore") is None:
        return {
            "styleId": style_id,
            "status": "pendingReview",
            "bestImage": best["path"],
            "nextAction": "Enter manual review scores in the review workbench or CSV, then apply the review.",
            "commandHint": "python3 scripts/style_eval.py --review-workbench {run_id}"
        }
    return {
        "styleId": style_id,
        "status": "failed",
        "bestImage": best["path"],
        "nextAction": "Prepare the next round; failure reasons will become prompt constraints.",
        "commandHint": "python3 scripts/style_eval.py --prepare-next-round {run_id} {next_run} --variants 3",
        "failureReasons": best.get("failureReasons", []),
        "finalScore": best.get("finalScore"),
        "targetAutomaticScore": best.get("targetAutomaticScore"),
        "targetRank": best.get("targetRank")
    }


def gate_report_payload(data, run_id, force=False):
    report_json, report_html = write_run_report(data, run_id, force=force)
    report = json.loads(report_json.read_text(encoding="utf-8"))
    audit = completion_audit(data, run_id)
    loop = loop_state(data, run_id)
    next_run = next_run_id(run_id)
    style_actions = []
    for style_report in report["styles"]:
        action = gate_action_for_style(style_report)
        action["commandHint"] = action.get("commandHint", "").format(run_id=run_id, next_run=next_run)
        style_actions.append(action)
    return {
        "runId": run_id,
        "nextRun": next_run,
        "theme": load_run_theme(data, run_id)["ja"],
        "summary": report["summary"],
        "audit": audit,
        "loop": loop,
        "styleActions": style_actions,
        "paths": {
            "evaluationJson": str(report_json),
            "reviewHtml": str(report_html),
            "projectHub": str(ROOT / "reports" / f"{run_id}_project_hub.html"),
            "reviewWorkbench": str(ROOT / "reports" / f"{run_id}_review_workbench.html"),
            "manualReviewCsv": str(ROOT / "reports" / f"{run_id}_manual_review_template.csv"),
            "codexPromptDir": str(ROOT / "prompt_runs" / run_id / "codex_prompts")
        }
    }


def next_run_id(run_id):
    if run_id.endswith("_v1"):
        return run_id[:-1] + "2"
    if "_v" in run_id:
        prefix, suffix = run_id.rsplit("_v", 1)
        if suffix.isdigit():
            return f"{prefix}_v{int(suffix) + 1}"
    return f"{run_id}_next"


def render_gate_report_md(payload):
    summary = payload["summary"]
    loop = payload["loop"]
    lines = [
        f"# Gate Report: {payload['runId']}",
        "",
        f"Theme: {payload['theme']}",
        "",
        "## Summary",
        "",
        f"- Generated images: {summary['generatedImageCount']}",
        f"- Reviewed images: {summary['reviewedImageCount']}",
        f"- Passed styles: {summary['passedStyleCount']} / {summary['styleCount']}",
        f"- Goal ready: {payload['audit']['complete']}",
        "",
        "## Current Loop Step",
        "",
        f"- Phase: `{loop['phase']}`",
        f"- Title: {loop['title']}",
        f"- Next action: {loop['nextAction']}",
        "",
        "Blockers:",
        "",
        *[f"- {item}" for item in loop["blockers"]],
        "",
        "## Next Commands",
        "",
        "```bash",
        *loop["commands"],
        "```",
        "",
        "## Requirement Audit",
        ""
    ]
    for row in payload["audit"]["requirements"]:
        lines.extend([
            f"### {row['requirement']}",
            "",
            f"- Status: `{row['status']}`",
            f"- Evidence: {row['evidence']}",
            ""
        ])
    lines.extend(["## Style Actions", ""])
    for action in payload["styleActions"]:
        lines.extend([
            f"### `{action['styleId']}`",
            "",
            f"- Status: `{action['status']}`",
            f"- Best image: `{action.get('bestImage') or 'none'}`",
            f"- Next action: {action['nextAction']}",
        ])
        if action.get("finalScore") is not None:
            lines.extend([
                f"- Final score: `{action['finalScore']}`",
                f"- Automatic score: `{action['targetAutomaticScore']}/35`",
                f"- Target rank: `{action['targetRank']}`"
            ])
        if action.get("failureReasons"):
            lines.append("- Failure reasons: " + "; ".join(action["failureReasons"]))
        if action.get("commandHint"):
            lines.extend(["", "```bash", action["commandHint"], "```"])
        lines.append("")
    lines.extend(["## Files", ""])
    for label, path in payload["paths"].items():
        lines.append(f"- {label}: `{path}`")
    lines.append("")
    return "\n".join(lines)


def render_gate_report_html(payload):
    md = render_gate_report_md(payload)
    escaped = html.escape(md)
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(payload['runId'])} Gate Report</title>
  <style>
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:#f6f6f1; color:#17191f; }}
    main {{ max-width:980px; margin:0 auto; padding:24px; }}
    pre {{ white-space:pre-wrap; overflow-wrap:anywhere; background:#fff; border:1px solid #dfe3eb; border-radius:8px; padding:16px; line-height:1.5; }}
  </style>
</head>
<body><main><pre>{escaped}</pre></main></body>
</html>
"""


def write_gate_report(data, run_id):
    payload = gate_report_payload(data, run_id)
    out_md = ROOT / "reports" / f"{run_id}_gate_report.md"
    out_html = ROOT / "reports" / f"{run_id}_gate_report.html"
    write_text_atomic(out_md, render_gate_report_md(payload))
    write_text_atomic(out_html, render_gate_report_html(payload))
    return out_md, out_html, payload


def smoke_test(data, run_id):
    results = []

    manifest, _ = write_reference_analysis(data)
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    results.append({
        "check": "reference_manifest_count",
        "passed": manifest_data["referenceCount"] == 37,
        "detail": f"{manifest_data['referenceCount']} references"
    })

    baselines = [baseline_for_style(style) for style in data["styles"]]
    baseline_count = sum(row["referenceCount"] for row in baselines)
    results.append({
        "check": "reference_baseline_count",
        "passed": baseline_count == 37,
        "detail": f"{baseline_count} references across baselines"
    })

    plan_json, _ = write_generation_plan(data, run_id, 3)
    plan = json.loads(plan_json.read_text(encoding="utf-8"))
    results.append({
        "check": "generation_plan_shape",
        "passed": plan["expectedImageCount"] == 15 and len(plan["jobs"]) == 5,
        "detail": f"{len(plan['jobs'])} jobs / {plan['expectedImageCount']} expected images"
    })

    generator_shell = write_generator_shell(run_id)
    run_job_count = sum(
        1 for line in generator_shell.read_text(encoding="utf-8").splitlines()
        if line.startswith("run_job ")
    )
    results.append({
        "check": "generator_shell_shape",
        "passed": generator_shell.exists() and run_job_count == plan["expectedImageCount"],
        "detail": f"{generator_shell} has {run_job_count} run_job calls"
    })

    codex_pack = write_codex_image_pack(data, run_id)
    codex_prompt_files = sorted((ROOT / "prompt_runs" / run_id / "codex_prompts").glob("*.txt"))
    results.append({
        "check": "codex_image_pack_shape",
        "passed": (
            codex_pack.exists()
            and codex_pack.read_text(encoding="utf-8").count("### Variant") == plan["expectedImageCount"]
            and len(codex_prompt_files) == plan["expectedImageCount"]
        ),
        "detail": f"{codex_pack}; prompt files={len(codex_prompt_files)}"
    })

    prompt_builder = write_prompt_builder(data)
    prompt_builder_text = prompt_builder.read_text(encoding="utf-8")
    results.append({
        "check": "prompt_builder_shape",
        "passed": prompt_builder.exists() and "Illustration Prompt Builder" in prompt_builder_text and "Thumbnail Style Selection" in prompt_builder_text,
        "detail": str(prompt_builder)
    })

    project_hub = write_project_hub(data, run_id)
    project_hub_text = project_hub.read_text(encoding="utf-8")
    results.append({
        "check": "project_hub_shape",
        "passed": project_hub.exists() and "Project Hub" in project_hub_text and "Completion Audit" in project_hub_text and "Current Loop Step" in project_hub_text,
        "detail": str(project_hub)
    })

    operator_checklist, operator_payload = write_operator_checklist(data, run_id)
    operator_text = operator_checklist.read_text(encoding="utf-8")
    results.append({
        "check": "operator_checklist_shape",
        "passed": (
            operator_checklist.exists()
            and "Operator Checklist" in operator_text
            and operator_payload["runId"] == run_id
            and "Requirement Audit" in operator_text
        ),
        "detail": str(operator_checklist)
    })

    gate_report_md, gate_report_html, gate_payload = write_gate_report(data, run_id)
    results.append({
        "check": "gate_report_shape",
        "passed": (
            gate_report_md.exists()
            and gate_report_html.exists()
            and "Style Actions" in gate_report_md.read_text(encoding="utf-8")
            and gate_payload["summary"]["styleCount"] == len(data["styles"])
            and gate_payload["loop"]["phase"] in {"generate", "fixImportedImages", "review", "iterate", "complete"}
        ),
        "detail": f"{gate_report_md}; {gate_report_html}"
    })

    loop = loop_state(data, run_id)
    results.append({
        "check": "loop_status_shape",
        "passed": loop["runId"] == run_id and bool(loop["phase"]) and bool(loop["commands"]) and "summary" in loop,
        "detail": f"{loop['phase']}: {loop['title']}"
    })

    sync = sync_run(data, run_id)
    results.append({
        "check": "sync_run_shape",
        "passed": sync["runId"] == run_id and sync["ok"] and "targetAudit" in sync and "refresh" in sync and "loop" in sync,
        "detail": f"{sync['loop']['phase']}: target ready={sync['targetAudit']['ready']}"
    })

    selftest_loop = loop_state(data, "style_selftest")
    results.append({
        "check": "style_selftest_loop_complete",
        "passed": selftest_loop["phase"] == "complete" and selftest_loop["summary"]["allStylesPassed"],
        "detail": f"{selftest_loop['phase']}: {selftest_loop['title']}"
    })

    intake_status = intake_audit(data, run_id)
    results.append({
        "check": "intake_audit_current_state",
        "passed": intake_status["expected"] == plan["expectedImageCount"],
        "detail": (
            f"{intake_status['present']} present / {intake_status['missing']} missing / "
            f"{intake_status['unreadable']} unreadable / {len(intake_status['duplicateGroups'])} duplicate groups"
        ),
        "ready": intake_status["ready"]
    })

    dashboard = write_dashboard(data, run_id)
    results.append({
        "check": "dashboard_shape",
        "passed": dashboard.exists() and "Codex Generation Dashboard" in dashboard.read_text(encoding="utf-8"),
        "detail": str(dashboard)
    })

    review_workbench = write_review_workbench(data, run_id)
    review_workbench_text = review_workbench.read_text(encoding="utf-8")
    results.append({
        "check": "review_workbench_shape",
        "passed": review_workbench.exists() and "Review Workbench" in review_workbench_text and "Export CSV text" in review_workbench_text,
        "detail": str(review_workbench)
    })

    review_priorities_json, review_priorities_md, review_priorities = write_review_priorities(data, run_id)
    results.append({
        "check": "review_priorities_shape",
        "passed": (
            review_priorities_json.exists()
            and review_priorities_md.exists()
            and len(review_priorities["styles"]) == len(data["styles"])
            and "Review Priorities" in review_priorities_md.read_text(encoding="utf-8")
        ),
        "detail": f"{review_priorities_json}; {review_priorities_md}"
    })

    manual_review_csv = write_manual_review_template(data, run_id)
    manual_csv_validation = validate_manual_review_csv(data, run_id, manual_review_csv)
    results.append({
        "check": "manual_review_csv_validation",
        "passed": manual_csv_validation["valid"] and manual_csv_validation["warningCount"] == plan["expectedImageCount"],
        "detail": f"errors={manual_csv_validation['errorCount']} warnings={manual_csv_validation['warningCount']}"
    })

    visual_index, visual_sheets = write_visual_review(data, run_id)
    results.append({
        "check": "visual_review_shape",
        "passed": visual_index.exists() and len(visual_sheets) == len(data["styles"]) and all(path.exists() for path in visual_sheets),
        "detail": f"{visual_index} with {len(visual_sheets)} sheets"
    })

    review_guide = write_review_guide(data, run_id)
    results.append({
        "check": "review_guide_shape",
        "passed": review_guide.exists() and all(style["id"] in review_guide.read_text(encoding="utf-8") for style in data["styles"]),
        "detail": str(review_guide)
    })

    generation_status = check_generation_plan(run_id)
    results.append({
        "check": "generation_plan_current_state",
        "passed": True,
        "detail": f"{generation_status['presentImageCount']} present / {generation_status['missingImageCount']} missing",
        "ready": generation_status["ready"]
    })

    selftest_json, _ = write_run_report(data, "style_selftest")
    selftest = json.loads(selftest_json.read_text(encoding="utf-8"))
    results.append({
        "check": "style_selftest_gate",
        "passed": run_passes(selftest),
        "detail": json.dumps(selftest["summary"], ensure_ascii=False)
    })

    run_json, _ = write_run_report(data, run_id)
    run_report = json.loads(run_json.read_text(encoding="utf-8"))
    results.append({
        "check": f"{run_id}_gate_current_state",
        "passed": True,
        "detail": json.dumps(run_report["summary"], ensure_ascii=False),
        "ready": run_passes(run_report)
    })

    return {
        "runId": run_id,
        "passed": all(row["passed"] for row in results),
        "goalReady": run_passes(run_report),
        "checks": results
    }


def dedupe(items):
    seen = set()
    out = []
    for item in items:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def main():
    parser = argparse.ArgumentParser(description="Build prompts and evaluate generated images against local style references.")
    parser.add_argument("--baselines", action="store_true", help="Write reports/reference_baselines.json")
    parser.add_argument("--analyze-references", action="store_true", help="Write reports/reference_manifest.json and reports/reference_analysis.md")
    parser.add_argument("--prompts", action="store_true", help="Write prompt_runs/coffee_walk_v1/*.md")
    parser.add_argument("--prompt-builder", action="store_true", help="Write reports/prompt_builder.html for form-driven prompt composition")
    parser.add_argument("--style", help="Style id for generated image evaluation")
    parser.add_argument("--generated", help="Generated image path to evaluate")
    parser.add_argument("--classify", help="Generated image path to score against every style")
    parser.add_argument("--report", nargs="?", const="coffee_walk_v1", help="Write reports/{run_id}_evaluation.json and review HTML")
    parser.add_argument("--next-round", nargs=2, metavar=("SOURCE_RUN", "TARGET_RUN"), help="Write improved prompt pack for the next run")
    parser.add_argument("--prepare-next-round", nargs=2, metavar=("SOURCE_RUN", "TARGET_RUN"), help="Write improved prompt pack plus generation plan, Codex pack, dashboard, and iteration plan for the next run")
    parser.add_argument("--gate", metavar="RUN_ID", help="Exit 0 only when every style has at least one passing reviewed image")
    parser.add_argument("--set-review", nargs=3, metavar=("RUN_ID", "STYLE_ID", "IMAGE"), help="Set manual review scores for one generated image")
    parser.add_argument("--scores", nargs=6, metavar=("SUBJECT", "LINE", "TEXTURE", "COMPOSITION", "PURITY", "USEFULNESS"), help="Manual review scores: 15 15 15 8 10 2 max")
    parser.add_argument("--notes", default="", help="Manual review notes used with --set-review")
    parser.add_argument("--hard-cap", type=float, help="Optional hard cap used with --set-review")
    parser.add_argument("--override", type=float, help="Optional final score override used with --set-review")
    parser.add_argument("--generation-plan", nargs="?", const="coffee_walk_v1", metavar="RUN_ID", help="Write prompt_runs/{run_id}/generation_plan.json and .md")
    parser.add_argument("--variants", type=int, default=3, help="Number of variants per style for --generation-plan")
    parser.add_argument("--export-generator-shell", metavar="RUN_ID", help="Write prompt_runs/{run_id}/run_generation_jobs.sh for an external image generator command")
    parser.add_argument("--codex-image-pack", nargs="?", const="coffee_walk_v1", metavar="RUN_ID", help="Write prompt_runs/{run_id}/codex_image_prompts.md for Codex subscription image generation")
    parser.add_argument("--codex-queue", nargs="?", const="coffee_walk_v1", metavar="RUN_ID", help="Print Codex prompt files, save names, and present/missing status")
    parser.add_argument("--intake-audit", nargs="+", metavar="RUN_ID [SOURCE_DIR]", help="Audit Codex-saved images before import, or planned evaluation paths after import")
    parser.add_argument("--import-codex-images", nargs=2, metavar=("RUN_ID", "SOURCE_DIR"), help="Copy Codex-saved images into the planned generated/{run_id} output paths")
    parser.add_argument("--dashboard", nargs="?", const="coffee_walk_v1", metavar="RUN_ID", help="Write reports/{run_id}_dashboard.html for Codex generation and review progress")
    parser.add_argument("--project-hub", nargs="?", const="coffee_walk_v1", metavar="RUN_ID", help="Write reports/{run_id}_project_hub.html with end-to-end workflow links and audit")
    parser.add_argument("--refresh-run", nargs="?", const="coffee_walk_v1", metavar="RUN_ID", help="Regenerate all prompt, report, review, visual, and dashboard artifacts for a run")
    parser.add_argument("--sync-run", nargs="+", metavar="RUN_ID [SOURCE_DIR]", help="Optionally import Codex images, refresh artifacts, and print the current loop state")
    parser.add_argument("--check-generation-plan", metavar="RUN_ID", help="Check whether all planned outputs exist")
    parser.add_argument("--smoke-test", nargs="?", const="coffee_walk_v1", metavar="RUN_ID", help="Run non-destructive pipeline checks")
    parser.add_argument("--review-sheet", nargs="?", const="coffee_walk_v1", metavar="RUN_ID", help="Write reports/{run_id}_review_sheet.csv and .md")
    parser.add_argument("--manual-review-template", nargs="?", const="coffee_walk_v1", metavar="RUN_ID", help="Write reports/{run_id}_manual_review_template.csv for batch manual scoring")
    parser.add_argument("--validate-review-csv", nargs=2, metavar=("RUN_ID", "CSV_PATH"), help="Validate manual review CSV rows before applying them")
    parser.add_argument("--apply-review-csv", nargs=2, metavar=("RUN_ID", "CSV_PATH"), help="Apply manual review scores from a CSV template")
    parser.add_argument("--review-priorities", nargs="?", const="coffee_walk_v1", metavar="RUN_ID", help="Write reports/{run_id}_review_priorities.md/json with suggested manual review order")
    parser.add_argument("--review-workbench", nargs="?", const="coffee_walk_v1", metavar="RUN_ID", help="Write reports/{run_id}_review_workbench.html for visual scoring and CSV export")
    parser.add_argument("--review-guide", nargs="?", const="coffee_walk_v1", metavar="RUN_ID", help="Write reports/{run_id}_review_guide.md with style-specific manual review guidance")
    parser.add_argument("--visual-review", "--visual-review-sheet", nargs="?", const="coffee_walk_v1", metavar="RUN_ID", help="Write reports/{run_id}_visual_review/*.jpg comparison sheets")
    parser.add_argument("--audit", nargs="?", const="coffee_walk_v1", metavar="RUN_ID", help="Print completion audit for the run")
    parser.add_argument("--loop-status", nargs="?", const="coffee_walk_v1", metavar="RUN_ID", help="Print current phase, blockers, and next commands for the 90-point loop")
    parser.add_argument("--operator-checklist", nargs="?", const="coffee_walk_v1", metavar="RUN_ID", help="Write reports/{run_id}_operator_checklist.md with the current human workflow")
    parser.add_argument("--gate-report", nargs="?", const="coffee_walk_v1", metavar="RUN_ID", help="Write reports/{run_id}_gate_report.md/html with blockers and next actions")
    parser.add_argument("--status", nargs="?", const="coffee_walk_v1", metavar="RUN_ID", help="Print concise run status")
    args = parser.parse_args()

    data = load_data()
    styles = {s["id"]: s for s in data["styles"]}

    if args.baselines:
        baselines = [baseline_for_style(style) for style in data["styles"]]
        out = ROOT / "reports" / "reference_baselines.json"
        out.parent.mkdir(exist_ok=True)
        write_text_atomic(out, json.dumps(baselines, ensure_ascii=False, indent=2))
        print(out)

    if args.analyze_references:
        out_json, out_md = write_reference_analysis(data)
        print(out_json)
        print(out_md)

    if args.prompts:
        out_dir = ROOT / "prompt_runs" / "coffee_walk_v1"
        write_prompt_pack(data, out_dir)
        print(out_dir)

    if args.prompt_builder:
        out_path = write_prompt_builder(data)
        print(out_path)

    if args.generation_plan:
        out_json, out_md = write_generation_plan(data, args.generation_plan, args.variants)
        print(out_json)
        print(out_md)

    if args.export_generator_shell:
        out_script = write_generator_shell(args.export_generator_shell)
        print(out_script)

    if args.codex_image_pack:
        out_path = write_codex_image_pack(data, args.codex_image_pack)
        print(out_path)

    if args.codex_queue:
        result = codex_queue(data, args.codex_queue)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.intake_audit:
        if len(args.intake_audit) > 2:
            raise SystemExit("--intake-audit accepts RUN_ID and optional SOURCE_DIR")
        run_id = args.intake_audit[0]
        source_dir = args.intake_audit[1] if len(args.intake_audit) == 2 else None
        result = intake_audit(data, run_id, source_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result["ready"]:
            raise SystemExit(1)

    if args.import_codex_images:
        run_id, source_dir = args.import_codex_images
        result = import_codex_images(data, run_id, source_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["missingCount"]:
            raise SystemExit(1)

    if args.dashboard:
        out_path = write_dashboard(data, args.dashboard)
        print(out_path)

    if args.project_hub:
        out_path = write_project_hub(data, args.project_hub)
        print(out_path)

    if args.refresh_run:
        result = refresh_run(data, args.refresh_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.sync_run:
        if len(args.sync_run) > 2:
            raise SystemExit("--sync-run accepts RUN_ID and optional SOURCE_DIR")
        run_id = args.sync_run[0]
        source_dir = args.sync_run[1] if len(args.sync_run) == 2 else None
        result = sync_run(data, run_id, source_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result["ok"]:
            raise SystemExit(1)

    if args.check_generation_plan:
        result = check_generation_plan(args.check_generation_plan)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result["ready"]:
            raise SystemExit(1)

    if args.smoke_test:
        result = smoke_test(data, args.smoke_test)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result["passed"]:
            raise SystemExit(1)

    if args.review_sheet:
        out_csv, out_md = write_review_sheet(data, args.review_sheet)
        print(out_csv)
        print(out_md)

    if args.manual_review_template:
        out_csv = write_manual_review_template(data, args.manual_review_template)
        print(out_csv)

    if args.validate_review_csv:
        run_id, csv_path = args.validate_review_csv
        result = validate_manual_review_csv(data, run_id, csv_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result["valid"]:
            raise SystemExit(1)

    if args.apply_review_csv:
        run_id, csv_path = args.apply_review_csv
        result = apply_manual_review_csv(data, run_id, csv_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("validation") and not result["validation"]["valid"]:
            raise SystemExit(1)

    if args.review_priorities:
        out_json, out_md, payload = write_review_priorities(data, args.review_priorities)
        print(out_json)
        print(out_md)

    if args.review_workbench:
        out_path = write_review_workbench(data, args.review_workbench)
        print(out_path)

    if args.review_guide:
        out_path = write_review_guide(data, args.review_guide)
        print(out_path)

    if args.visual_review:
        index_path, sheet_paths = write_visual_review(data, args.visual_review)
        print(index_path)
        for sheet_path in sheet_paths:
            print(sheet_path)

    if args.audit:
        result = completion_audit(data, args.audit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result["complete"]:
            raise SystemExit(1)

    if args.loop_status:
        result = loop_state(data, args.loop_status)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.operator_checklist:
        out_md, payload = write_operator_checklist(data, args.operator_checklist)
        print(out_md)

    if args.gate_report:
        out_md, out_html, payload = write_gate_report(data, args.gate_report)
        print(out_md)
        print(out_html)
        if not payload["audit"]["complete"]:
            raise SystemExit(1)

    if args.status:
        print(json.dumps(run_status(data, args.status), ensure_ascii=False, indent=2))

    if args.style or args.generated:
        if not args.style or not args.generated:
            raise SystemExit("--style and --generated must be used together")
        if args.style not in styles:
            raise SystemExit(f"Unknown style: {args.style}")
        result = score_generated(styles[args.style], Path(args.generated))
        print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.classify:
        generated_path = Path(args.classify)
        results = classify_generated(data, generated_path)
        print(json.dumps({"generated": str(generated_path), "styleRanking": results}, ensure_ascii=False, indent=2))

    if args.report:
        out_json, out_html = write_run_report(data, args.report)
        print(out_json)
        print(out_html)

    if args.next_round:
        source_run, target_run = args.next_round
        out_dir = write_next_round(data, source_run, target_run)
        print(out_dir)

    if args.prepare_next_round:
        source_run, target_run = args.prepare_next_round
        result = prepare_next_round(data, source_run, target_run, args.variants)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.gate:
        out_json, _ = write_run_report(data, args.gate)
        report = json.loads(out_json.read_text(encoding="utf-8"))
        summary = report["summary"]
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        raise SystemExit(0 if run_passes(report) else 1)

    if args.set_review:
        if not args.scores:
            raise SystemExit("--set-review requires --scores")
        run_id, style_id, image_selector = args.set_review
        if style_id not in styles:
            raise SystemExit(f"Unknown style: {style_id}")
        scores = parse_review_scores(args.scores)
        out_json, out_html = set_manual_review(data, run_id, style_id, image_selector, scores, args.notes, args.hard_cap, args.override)
        print(out_json)
        print(out_html)


if __name__ == "__main__":
    main()
