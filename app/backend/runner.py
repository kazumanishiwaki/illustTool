from __future__ import annotations

import fnmatch
import importlib.util
import json
import re
import shutil
import subprocess
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_FILE = ROOT / "data" / "style_fingerprints.json"
REPORTS_DIR = ROOT / "reports"
RUNS_DIR = ROOT / "prompt_runs"
SCRIPT_FILE = ROOT / "scripts" / "style_eval.py"
_STYLE_EVAL = None

DEFAULT_RUN_STYLE_IDS = [
    "naive_wobbly_line",
    "grain_flat",
    "print_relief_lino",
    "editorial_outline_minimal",
    "flat_vector",
]


def project_root() -> Path:
    return ROOT


def run_style_eval(*args: str, json_output: bool = False, allow_failure: bool = False) -> dict[str, Any]:
    cmd = ["python3", str(SCRIPT_FILE), *args]
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    payload: dict[str, Any] = {
        "ok": proc.returncode == 0,
        "returnCode": proc.returncode,
        "command": " ".join(cmd),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
    if json_output and proc.stdout.strip():
        try:
            payload["data"] = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            payload["parseError"] = str(exc)
    if proc.returncode != 0 and not allow_failure:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"style_eval exited {proc.returncode}")
    return payload


def loop_status(run_id: str) -> dict[str, Any]:
    result = run_style_eval("--loop-status", run_id, json_output=True)
    return result.get("data", {})


def write_prompt_pack(run_id: str) -> dict[str, Any]:
    return run_style_eval("--codex-image-pack", run_id)


def write_generation_plan(run_id: str, variants: int = 3) -> dict[str, Any]:
    return run_style_eval("--generation-plan", run_id, "--variants", str(variants))


def refresh_run(run_id: str) -> dict[str, Any]:
    return run_style_eval("--refresh-run", run_id)


def gate_report(run_id: str) -> dict[str, Any]:
    return run_style_eval("--gate-report", run_id, allow_failure=True)


def sync_run(run_id: str, source_dir: str | None = None) -> dict[str, Any]:
    args = ["--sync-run", run_id]
    if source_dir:
        args.append(source_dir)
    return run_style_eval(*args, json_output=True, allow_failure=True)


def generation_slots(run_id: str) -> dict[str, Any]:
    plan_path = ROOT / "prompt_runs" / run_id / "generation_plan.json"
    if not plan_path.exists():
        write_generation_plan(run_id)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    slots: list[dict[str, Any]] = []
    sequence = 1
    for job in plan.get("jobs", []):
        variants = job.get("variants") or []
        for variant in variants:
            output = Path(variant["outputPath"])
            prompt_path = ROOT / "prompt_runs" / run_id / "codex_prompts" / f"{sequence:02d}_{job['styleId']}_round_01_{variant.get('variantLabel', '')}.txt"
            slots.append({
                "sequence": sequence,
                "styleId": job["styleId"],
                "labelJa": job.get("labelJa", job["styleId"]),
                "variant": variant.get("variant", sequence),
                "variantLabel": variant.get("variantLabel", ""),
                "variantFocus": variant.get("variantFocus", ""),
                "positivePrompt": variant.get("positivePrompt", job.get("positivePrompt", "")),
                "negativePrompt": variant.get("negativePrompt", job.get("negativePrompt", "")),
                "outputPath": str(output),
                "outputName": output.name,
                "exists": output.exists(),
                "imageUrl": f"/generated/{output.relative_to(ROOT / 'generated')}".replace("\\", "/") if output.exists() else "",
                "promptPath": str(prompt_path),
                "promptFile": prompt_path.name,
            })
            sequence += 1
    return {
        "runId": run_id,
        "expected": len(slots),
        "present": sum(1 for slot in slots if slot["exists"]),
        "missing": sum(1 for slot in slots if not slot["exists"]),
        "slots": slots,
    }


def set_review(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    args = [
        "--set-review",
        run_id,
        payload["styleId"],
        payload["image"],
        "--scores",
        *[str(x) for x in payload["scores"]],
    ]
    notes = payload.get("notes")
    if notes:
        args.extend(["--notes", notes])
    if payload.get("hardCap") is not None:
        args.extend(["--hard-cap", str(payload["hardCap"])])
    if payload.get("override") is not None:
        args.extend(["--override", str(payload["override"])])
    return run_style_eval(*args)


def set_reviews_batch(run_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    for item in items:
        try:
            result = set_review(run_id, item)
            results.append({
                "styleId": item["styleId"],
                "image": item["image"],
                "ok": result.get("ok", False),
            })
        except RuntimeError as exc:
            errors.append(f"{item['styleId']}/{item['image']}: {exc}")
    refresh_run(run_id)
    return {
        "runId": run_id,
        "saved": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors,
        "ok": not errors,
    }


def _load_data() -> dict[str, Any]:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def _save_data(data: dict[str, Any]) -> None:
    backup_dir = DATA_FILE.parent / "_backups"
    backup_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    shutil.copy2(DATA_FILE, backup_dir / f"style_fingerprints.{stamp}.json")
    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_styles() -> list[dict[str, Any]]:
    return _load_data().get("styles", [])


def load_style(style_id: str) -> dict[str, Any] | None:
    for s in load_styles():
        if s.get("id") == style_id:
            return s
    return None


def style_reference_images(style_id: str) -> list[str]:
    style = load_style(style_id)
    if style is None:
        return []
    globs = style.get("referenceGlobs") or [style.get("referenceGlob", "")]
    globs = [glob for glob in globs if glob]
    if not globs:
        return []
    patterns_nfc = [unicodedata.normalize("NFC", glob) for glob in globs]
    matches: list[str] = []
    for child in ROOT.iterdir():
        if not child.is_file():
            continue
        name_nfc = unicodedata.normalize("NFC", child.name)
        if any(fnmatch.fnmatch(name_nfc, pattern_nfc) for pattern_nfc in patterns_nfc):
            matches.append(str(child.relative_to(ROOT)))
    return sorted(matches)


def style_preview_image(style_id: str) -> str:
    preview_dir = ROOT / "generated" / "style_previews"
    for ext in (".png", ".webp", ".jpg", ".jpeg"):
        path = preview_dir / f"{style_id}{ext}"
        if path.exists():
            return str(path.relative_to(ROOT))
    return ""


def update_style(style_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    data = _load_data()
    styles = data.get("styles", [])
    target = None
    for s in styles:
        if s.get("id") == style_id:
            target = s
            break
    if target is None:
        raise KeyError(style_id)

    list_keys = {
        "promptFragments",
        "promptFragmentsJa",
        "negativeFragments",
        "negativeFragmentsJa",
    }
    dict_keys = {
        "visualFingerprint",
        "visualFingerprintJa",
        "improvementRules",
        "improvementRulesJa",
    }
    editable = {"labelJa"} | list_keys | dict_keys
    for key, value in patch.items():
        if value is None:
            continue
        if key not in editable:
            continue
        if key in list_keys:
            target[key] = [str(x).strip() for x in value if str(x).strip()]
        elif key in dict_keys:
            target[key] = {
                str(k): str(v).strip() for k, v in value.items() if str(v).strip()
            }
        else:
            target[key] = value

    _save_data(data)
    return target


def apply_style_strength(positive_fragments: list[str], strength: int) -> tuple[str, list[str]]:
    strength = max(1, min(100, int(strength or 70)))
    if not positive_fragments:
        return "", []

    if strength <= 40:
        count = max(1, round(len(positive_fragments) * strength / 40))
        selected = positive_fragments[:count]
        prefix = "Loosely inspired by the reference style. "
    elif strength <= 70:
        selected = positive_fragments
        prefix = ""
    elif strength <= 90:
        selected = positive_fragments + positive_fragments[-1:]
        prefix = "Faithfully follow the reference style. "
    else:
        tail = positive_fragments[-2:] if len(positive_fragments) >= 2 else positive_fragments
        selected = positive_fragments + tail
        prefix = "Strictly match the reference style. "
    return prefix, selected


def compose_prompt(req: dict[str, Any]) -> dict[str, Any]:
    style = load_style(req["styleId"])
    if style is None:
        raise KeyError(req["styleId"])

    positive_fragments = list(style.get("promptFragments", []))
    negative_fragments = list(style.get("negativeFragments", []))

    subject = req.get("subject", "").strip()
    required = [s for s in req.get("requiredElements", []) if s.strip()]
    avoid = [s for s in req.get("avoidElements", []) if s.strip()]
    use_case = req.get("useCase", "").strip()
    fmt = req.get("format", "").strip()
    tone = req.get("tone", "").strip()
    strength = int(req.get("strength", 70) or 70)

    base_parts: list[str] = []
    if subject:
        base_parts.append(subject)
    if required:
        base_parts.append(", ".join(required))
    if tone:
        base_parts.append(tone)
    if use_case:
        base_parts.append(f"intended for {use_case}")
    if fmt:
        base_parts.append(fmt)

    base_positive = ", ".join(base_parts) if base_parts else ""
    prefix, selected_fragments = apply_style_strength(positive_fragments, strength)
    style_positive = ", ".join(selected_fragments)
    positive_parts = [part for part in (prefix.strip(), base_positive, style_positive) if part]
    positive = ", ".join(positive_parts)

    base_negative = ", ".join(avoid)
    style_negative = ", ".join(negative_fragments)
    negative = ", ".join(p for p in (base_negative, style_negative) if p)

    variant_specs = [
        ("A", "subject clarity", "clear subject, full body visible, focal pose readable, primary props legible"),
        ("B", "composition and palette", "balanced composition, intentional whitespace, palette-faithful color blocking"),
        ("C", "style technique", "style technique foregrounded, characteristic line/texture/medium emphasis"),
    ]
    variants = []
    for label, focus, emphasis in variant_specs:
        variants.append({
            "label": label,
            "focus": focus,
            "positive": f"{emphasis}, {positive}" if positive else emphasis,
            "negative": negative,
        })

    return {
        "styleId": style["id"],
        "positive": positive,
        "negative": negative,
        "strength": strength,
        "variants": variants,
    }


def compose_prompts_batch(req: dict[str, Any]) -> dict[str, Any]:
    style_ids = req.get("styleIds") or DEFAULT_RUN_STYLE_IDS
    shared = {
        key: req.get(key)
        for key in (
            "subject",
            "requiredElements",
            "avoidElements",
            "useCase",
            "format",
            "tone",
            "strength",
        )
    }
    results = []
    for style_id in style_ids:
        try:
            results.append(compose_prompt({**shared, "styleId": style_id}))
        except KeyError:
            continue
    return {"results": results, "styleIds": style_ids}


def _style_eval_module():
    global _STYLE_EVAL
    if _STYLE_EVAL is None:
        spec = importlib.util.spec_from_file_location("style_eval", SCRIPT_FILE)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot load style_eval from {SCRIPT_FILE}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _STYLE_EVAL = mod
    return _STYLE_EVAL


def _run_meta_path(run_id: str) -> Path:
    return RUNS_DIR / run_id / "run_meta.json"


def _slugify_run_id(subject: str) -> str:
    safe = unicodedata.normalize("NFC", subject.strip())
    safe = re.sub(r'[\\/:*?"<>|]', "", safe)
    safe = re.sub(r"\s+", "_", safe)[:32].strip("_")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if safe:
        return f"{safe}_{stamp}"
    return f"run_{stamp}"


def _meta_from_legacy_plan(run_id: str) -> dict[str, Any] | None:
    plan_path = RUNS_DIR / run_id / "generation_plan.json"
    if not plan_path.exists():
        return None
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    theme = plan.get("theme", {})
    style_ids = [job["styleId"] for job in plan.get("jobs", []) if job.get("styleId")]
    if not theme.get("ja") and not style_ids:
        return None
    return {
        "runId": run_id,
        "subject": theme.get("ja", ""),
        "requiredElements": list(theme.get("mustContain", [])),
        "avoidElements": list(theme.get("mustAvoid", [])),
        "useCase": "",
        "format": "",
        "tone": "",
        "basePromptEn": theme.get("basePromptEn", theme.get("ja", "")),
        "styleIds": style_ids,
        "legacy": True,
        "createdAt": datetime.fromtimestamp(
            plan_path.stat().st_mtime,
            tz=timezone.utc,
        ).isoformat(),
    }


def ensure_run_meta(run_id: str, write: bool = True) -> dict[str, Any] | None:
    path = _run_meta_path(run_id)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    meta = _meta_from_legacy_plan(run_id)
    if meta is None:
        return None
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return meta


def _build_base_prompt_en(payload: dict[str, Any]) -> str:
    subject = str(payload.get("subject", "")).strip()
    required = [s for s in payload.get("requiredElements", []) if str(s).strip()]
    avoid = payload.get("avoidElements", [])
    tone = str(payload.get("tone", "")).strip()
    use_case = str(payload.get("useCase", "")).strip()
    fmt = str(payload.get("format", "")).strip()
    parts: list[str] = []
    if subject:
        parts.append(subject)
    if required:
        parts.append(", ".join(required))
    if tone:
        parts.append(tone)
    if use_case:
        parts.append(f"intended for {use_case}")
    if fmt:
        parts.append(fmt)
    return ", ".join(parts)


def _write_style_prompt_md(
    style: dict[str, Any],
    positive: str,
    negative: str,
    meta: dict[str, Any],
    out_path: Path,
) -> None:
    required = meta.get("requiredElements", [])
    body = f"""# {style["labelJa"]} / {style["id"]}

## Theme
{meta.get("subject", "")}

## Positive Prompt
{positive}

## Negative Prompt
{negative}

## Must Contain
{chr(10).join(f"- {item}" for item in required)}

## Style Fingerprint
- Line: {style["visualFingerprint"]["line"]}
- Shape: {style["visualFingerprint"]["shape"]}
- Color: {style["visualFingerprint"]["color"]}
- Texture: {style["visualFingerprint"]["texture"]}
- Composition: {style["visualFingerprint"]["composition"]}
- Person: {style["visualFingerprint"]["person"]}

## Improvement Rules
{chr(10).join(f"- {key}: {value}" for key, value in style.get("improvementRules", {}).items())}

## Style Scoring Weights
{chr(10).join(f"- {key}: {value}" for key, value in style.get("styleScoringWeights", {}).items())}
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body, encoding="utf-8")


def list_runs() -> list[dict[str, Any]]:
    if not RUNS_DIR.exists():
        return []
    rows: list[dict[str, Any]] = []
    for child in RUNS_DIR.iterdir():
        if not child.is_dir():
            continue
        run_id = child.name
        ensure_run_meta(run_id, write=True)
        meta_path = child / "run_meta.json"
        plan_path = child / "generation_plan.json"
        meta = None
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        subject = meta.get("subject", "") if meta else ""
        if not subject and plan_path.exists():
            try:
                plan = json.loads(plan_path.read_text(encoding="utf-8"))
                subject = plan.get("theme", {}).get("ja", "")
            except json.JSONDecodeError:
                subject = ""
        mtime = max(
            (p.stat().st_mtime for p in child.rglob("*") if p.is_file()),
            default=child.stat().st_mtime,
        )
        rows.append({
            "runId": run_id,
            "subject": subject,
            "createdAt": meta.get("createdAt", "") if meta else "",
            "hasPlan": plan_path.exists(),
            "updatedAt": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
        })
    rows.sort(key=lambda row: row.get("updatedAt", ""), reverse=True)
    return rows


def get_run_meta(run_id: str) -> dict[str, Any] | None:
    return ensure_run_meta(run_id, write=True)


def create_run(payload: dict[str, Any]) -> dict[str, Any]:
    subject = str(payload.get("subject", "")).strip()
    if not subject:
        raise ValueError("subject is required")

    run_id = str(payload.get("runId", "")).strip() or _slugify_run_id(subject)
    if (RUNS_DIR / run_id).exists() and not payload.get("overwrite"):
        raise FileExistsError(f"run already exists: {run_id}")

    required = [str(s).strip() for s in payload.get("requiredElements", []) if str(s).strip()]
    avoid = [str(s).strip() for s in payload.get("avoidElements", []) if str(s).strip()]
    meta = {
        "runId": run_id,
        "subject": subject,
        "requiredElements": required,
        "avoidElements": avoid,
        "useCase": str(payload.get("useCase", "")).strip(),
        "format": str(payload.get("format", "")).strip(),
        "tone": str(payload.get("tone", "")).strip(),
        "strength": max(1, min(100, int(payload.get("strength", 70) or 70))),
        "basePromptEn": _build_base_prompt_en(payload),
        "styleIds": list(DEFAULT_RUN_STYLE_IDS),
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    _run_meta_path(run_id).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    styles = [s for s in load_styles() if s["id"] in DEFAULT_RUN_STYLE_IDS]
    missing = [sid for sid in DEFAULT_RUN_STYLE_IDS if sid not in {s["id"] for s in styles}]
    if missing:
        raise ValueError(f"unknown run styles: {', '.join(missing)}")
    for style in styles:
        composed = compose_prompt({
            "styleId": style["id"],
            "subject": subject,
            "requiredElements": required,
            "avoidElements": avoid,
            "useCase": meta["useCase"],
            "format": meta["format"],
            "tone": meta["tone"],
            "strength": meta["strength"],
        })
        _write_style_prompt_md(
            style,
            composed["positive"],
            composed["negative"],
            meta,
            run_dir / f"{style['id']}.md",
        )

    export_run_artifacts(run_id)
    return {"runId": run_id, "meta": meta}


def export_run_artifacts(run_id: str) -> dict[str, Any]:
    write_generation_plan(run_id)
    write_prompt_pack(run_id)
    return {"runId": run_id, "exported": True}


def review_workbench_data(run_id: str, force: bool = False) -> dict[str, Any]:
    mod = _style_eval_module()
    data = mod.load_data()
    payload = mod.review_workbench_payload(data, run_id, force=force)
    axis_order = list(payload["manualAxes"].keys())
    for row in payload.get("rows", []):
        row["imageUrl"] = ""
        if row.get("exists") and row.get("imagePath"):
            image_path = Path(row["imagePath"])
            try:
                rel = image_path.relative_to(ROOT / "generated")
                row["imageUrl"] = f"/generated/{rel}".replace("\\", "/")
            except ValueError:
                row["imageUrl"] = ""
        refs = []
        for ref in row.get("references", []):
            ref_path = Path(ref)
            if ref_path.is_absolute():
                try:
                    rel = ref_path.relative_to(ROOT)
                    refs.append(f"/references/{rel}".replace("\\", "/"))
                except ValueError:
                    refs.append(ref)
            else:
                refs.append(f"/references/{ref}".replace("\\", "/"))
        row["referenceUrls"] = refs
        manual_axes = row.get("manualAxes") or {}
        row["scoreValues"] = [manual_axes.get(axis) for axis in axis_order]
    payload["axisOrder"] = axis_order
    return payload


def gate_summary(run_id: str, force: bool = False) -> dict[str, Any]:
    mod = _style_eval_module()
    data = mod.load_data()
    return mod.gate_report_payload(data, run_id, force=force)


def refresh_evaluation(run_id: str) -> dict[str, Any]:
    mod = _style_eval_module()
    data = mod.load_data()
    mod.write_run_report(data, run_id, force=True)
    return {"runId": run_id, "refreshed": True}


def find_available_run_id(source_run: str, preferred: str | None = None) -> str:
    mod = _style_eval_module()
    candidates: list[str] = []
    if preferred:
        candidates.append(preferred)
    candidates.append(mod.next_run_id(source_run))

    if "_v" in source_run:
        prefix, suffix = source_run.rsplit("_v", 1)
        if suffix.isdigit():
            start = int(suffix) + 1
            for i in range(start, start + 30):
                candidates.append(f"{prefix}_v{i}")

    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if not (RUNS_DIR / candidate).exists():
            return candidate

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{source_run}_round_{stamp}"


def prepare_next_round(
    source_run: str,
    target_run: str | None = None,
    variants: int = 3,
) -> dict[str, Any]:
    mod = _style_eval_module()
    data = mod.load_data()
    preferred = target_run or mod.next_run_id(source_run)
    resolved_target = find_available_run_id(source_run, preferred)
    result = mod.prepare_next_round(data, source_run, resolved_target, variants)
    result["requestedTarget"] = preferred
    result["targetRun"] = resolved_target
    return result


def delete_run(run_id: str) -> dict[str, Any]:
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"unknown run: {run_id}")
    shutil.rmtree(run_dir)
    generated_run_dir = ROOT / "generated" / run_id
    if generated_run_dir.exists():
        shutil.rmtree(generated_run_dir)
    for path in REPORTS_DIR.glob(f"{run_id}_*"):
        if path.is_file():
            path.unlink()
    return {"runId": run_id, "deleted": True}


def intake_audit(run_id: str, source_dir: str | None = None) -> dict[str, Any]:
    mod = _style_eval_module()
    data = mod.load_data()
    return mod.intake_audit(data, run_id, source_dir)
