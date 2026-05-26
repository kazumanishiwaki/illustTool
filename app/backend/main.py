from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .runner import (
    compose_prompt,
    compose_prompts_batch,
    create_run,
    delete_run,
    export_run_artifacts,
    gate_report,
    gate_summary,
    generation_slots,
    get_run_meta,
    intake_audit,
    list_runs,
    load_style,
    load_styles,
    loop_status,
    prepare_next_round,
    project_root,
    refresh_evaluation,
    refresh_run,
    review_workbench_data,
    set_review,
    set_reviews_batch,
    style_preview_image,
    style_reference_images,
    sync_run,
    update_style,
    write_generation_plan,
    write_prompt_pack,
)
from .schemas import (
    BatchReviewRequest,
    ComposeBatchRequest,
    ComposeBatchResult,
    ComposeRequest,
    ComposeResult,
    CommandResult,
    CreateRunRequest,
    IntakeAuditRequest,
    PrepareNextRoundRequest,
    ReviewRequest,
    RunSummary,
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


@app.post("/api/prompts/compose-batch", response_model=ComposeBatchResult)
def post_compose_batch(req: ComposeBatchRequest) -> ComposeBatchResult:
    payload = compose_prompts_batch(req.model_dump())
    return ComposeBatchResult(
        styleIds=payload["styleIds"],
        results=[ComposeResult(**row) for row in payload["results"]],
    )


@app.get("/api/runs", response_model=list[RunSummary])
def get_runs() -> list[RunSummary]:
    return [RunSummary(**row) for row in list_runs()]


@app.post("/api/runs")
def post_create_run(req: CreateRunRequest) -> dict:
    try:
        return create_run(req.model_dump())
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/runs/{run_id}/meta")
def get_run_meta_endpoint(run_id: str) -> dict:
    meta = get_run_meta(run_id)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"unknown run: {run_id}")
    return meta


@app.post("/api/runs/{run_id}/export")
def post_export_run(run_id: str) -> dict:
    if get_run_meta(run_id) is None and not (project_root() / "prompt_runs" / run_id).exists():
        raise HTTPException(status_code=404, detail=f"unknown run: {run_id}")
    try:
        return export_run_artifacts(run_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


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


@app.get("/api/runs/{run_id}/gate/summary")
def get_gate_summary(run_id: str, refresh: bool = False) -> dict:
    try:
        return gate_summary(run_id, force=refresh)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/runs/{run_id}/reviews/workbench")
def get_review_workbench(run_id: str, refresh: bool = False) -> dict:
    try:
        return review_workbench_data(run_id, force=refresh)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/runs/{run_id}/evaluation/refresh")
def post_refresh_evaluation(run_id: str) -> dict:
    try:
        return refresh_evaluation(run_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/runs/{run_id}/next-round")
def post_prepare_next_round(run_id: str, req: PrepareNextRoundRequest) -> dict:
    try:
        if req.overwrite and req.targetRun.strip():
            target = req.targetRun.strip()
            if (project_root() / "prompt_runs" / target).exists():
                delete_run(target)
            return prepare_next_round(run_id, target, req.variants)
        return prepare_next_round(
            run_id,
            req.targetRun.strip() or None,
            req.variants,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.delete("/api/runs/{run_id}")
def delete_run_endpoint(run_id: str) -> dict:
    try:
        return delete_run(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/runs/{run_id}/intake-audit")
def post_intake_audit(run_id: str, req: IntakeAuditRequest) -> dict:
    source_dir = req.sourceDir.strip() or None
    try:
        return intake_audit(run_id, source_dir)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


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


@app.post("/api/runs/{run_id}/reviews/batch")
def post_reviews_batch(run_id: str, req: BatchReviewRequest) -> dict:
    try:
        return set_reviews_batch(
            run_id,
            [item.model_dump() for item in req.reviews],
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


generated_dir = project_root() / "generated"
generated_dir.mkdir(exist_ok=True)
REPORTS_DIR = project_root() / "reports"
REPORTS_DIR.mkdir(exist_ok=True)
FRONTEND_DIST_DIR = project_root() / "app" / "frontend" / "dist"
PROMPT_RUNS_DIR = project_root() / "prompt_runs"
PROMPT_RUNS_DIR.mkdir(exist_ok=True)

app.mount("/references", StaticFiles(directory=str(project_root())), name="references")
app.mount("/generated", StaticFiles(directory=str(generated_dir)), name="generated")
app.mount("/reports", StaticFiles(directory=str(REPORTS_DIR)), name="reports")
app.mount("/prompt_runs", StaticFiles(directory=str(PROMPT_RUNS_DIR)), name="prompt_runs")

if FRONTEND_DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST_DIR), html=True), name="frontend")
