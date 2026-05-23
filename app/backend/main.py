from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .runner import (
    compose_prompt,
    gate_report,
    generation_slots,
    load_style,
    load_styles,
    loop_status,
    project_root,
    refresh_run,
    set_review,
    style_preview_image,
    style_reference_images,
    sync_run,
    update_style,
    write_generation_plan,
    write_prompt_pack,
)
from .schemas import (
    ComposeRequest,
    ComposeResult,
    CommandResult,
    ReviewRequest,
    StyleDetail,
    StyleSummary,
    StyleUpdate,
    SyncRequest,
)

app = FastAPI(title="illustration-tool", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/styles", response_model=list[StyleSummary])
def get_styles() -> list[StyleSummary]:
    return [
        StyleSummary(
            id=s["id"],
            labelJa=s.get("labelJa", s["id"]),
            styleFamilyJa=s.get("styleFamilyJa", ""),
            referenceImages=style_reference_images(s["id"]),
            previewImage=style_preview_image(s["id"]),
            styleDifferentiator=s.get("styleDifferentiator", ""),
            visualFingerprint=s.get("visualFingerprint", {}),
        )
        for s in load_styles()
    ]


def _to_detail(style: dict, style_id: str) -> StyleDetail:
    return StyleDetail(
        id=style["id"],
        labelJa=style.get("labelJa", style["id"]),
        styleFamilyJa=style.get("styleFamilyJa", ""),
        referenceGlob=", ".join(style.get("referenceGlobs") or [style.get("referenceGlob", "")]),
        referenceImages=style_reference_images(style_id),
        previewImage=style_preview_image(style_id),
        styleDifferentiator=style.get("styleDifferentiator", ""),
        visualFingerprint=style.get("visualFingerprint", {}),
        visualFingerprintJa=style.get("visualFingerprintJa", {}),
        promptFragments=style.get("promptFragments", []),
        promptFragmentsJa=style.get("promptFragmentsJa", []),
        negativeFragments=style.get("negativeFragments", []),
        negativeFragmentsJa=style.get("negativeFragmentsJa", []),
        improvementRules=style.get("improvementRules", {}),
        improvementRulesJa=style.get("improvementRulesJa", {}),
        styleScoringWeights=style.get("styleScoringWeights", {}),
    )


@app.get("/api/styles/{style_id}", response_model=StyleDetail)
def get_style_detail(style_id: str) -> StyleDetail:
    style = load_style(style_id)
    if style is None:
        raise HTTPException(status_code=404, detail=f"unknown style: {style_id}")
    return _to_detail(style, style_id)


@app.put("/api/styles/{style_id}", response_model=StyleDetail)
def put_style(style_id: str, patch: StyleUpdate) -> StyleDetail:
    try:
        updated = update_style(style_id, patch.model_dump(exclude_none=True))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown style: {style_id}")
    return _to_detail(updated, style_id)


@app.post("/api/prompts/compose", response_model=ComposeResult)
def post_compose(req: ComposeRequest) -> ComposeResult:
    try:
        result = compose_prompt(req.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown style: {exc.args[0]}")
    return ComposeResult(**result)


@app.get("/api/runs/{run_id}/status")
def get_run_status(run_id: str) -> dict:
    try:
        return loop_status(run_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/runs/{run_id}/slots")
def get_generation_slots(run_id: str) -> dict:
    try:
        return generation_slots(run_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/runs/{run_id}/prompt-pack", response_model=CommandResult)
def post_prompt_pack(run_id: str) -> CommandResult:
    try:
        return CommandResult(**write_prompt_pack(run_id))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/runs/{run_id}/plan", response_model=CommandResult)
def post_generation_plan(run_id: str, variants: int = 3) -> CommandResult:
    try:
        return CommandResult(**write_generation_plan(run_id, variants))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/runs/{run_id}/refresh", response_model=CommandResult)
def post_refresh_run(run_id: str) -> CommandResult:
    try:
        return CommandResult(**refresh_run(run_id))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/runs/{run_id}/gate", response_model=CommandResult)
def get_gate_report(run_id: str) -> CommandResult:
    return CommandResult(**gate_report(run_id))


@app.post("/api/runs/{run_id}/sync")
def post_sync_run(run_id: str, req: SyncRequest) -> dict:
    source_dir = req.sourceDir.strip() or None
    return sync_run(run_id, source_dir).get("data", {})


@app.post("/api/runs/{run_id}/reviews", response_model=CommandResult)
def post_review(run_id: str, req: ReviewRequest) -> CommandResult:
    try:
        return CommandResult(**set_review(run_id, req.model_dump()))
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


generated_dir = project_root() / "generated"
generated_dir.mkdir(exist_ok=True)
REPORTS_DIR = project_root() / "reports"
REPORTS_DIR.mkdir(exist_ok=True)
FRONTEND_DIST_DIR = project_root() / "app" / "frontend" / "dist"

app.mount("/references", StaticFiles(directory=str(project_root())), name="references")
app.mount("/generated", StaticFiles(directory=str(generated_dir)), name="generated")
app.mount("/reports", StaticFiles(directory=str(REPORTS_DIR)), name="reports")

if FRONTEND_DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST_DIR), html=True), name="frontend")
