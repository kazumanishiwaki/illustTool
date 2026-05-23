from __future__ import annotations

import fnmatch
import json
import shutil
import subprocess
import time
import unicodedata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_FILE = ROOT / "data" / "style_fingerprints.json"
REPORTS_DIR = ROOT / "reports"
SCRIPT_FILE = ROOT / "scripts" / "style_eval.py"


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
    style_positive = ", ".join(positive_fragments)
    positive = ", ".join(p for p in (base_positive, style_positive) if p)

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
        "variants": variants,
    }
