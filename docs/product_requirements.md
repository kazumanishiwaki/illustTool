# Product Requirements

## Product Goal

Build a local prompt-and-evaluation tool for illustration generation.

The user writes what they want in the illustration and where it will be used. The user does not need to write style vocabulary manually. Instead, style, taste, and technique are selected visually from thumbnails backed by analyzed reference images.

The tool then prepares Codex/ChatGPT image-generation prompts, imports generated files, evaluates style reproduction, and produces next-round prompts until the output reaches the 90-point gate.

## Core Value

The core value is not image generation itself.

The core value is:

- extracting style fingerprints from 37 reference images
- turning those fingerprints into generator-ready prompts
- testing whether the same fixed subject can be rendered in the reference style
- scoring outputs with a repeatable 100-point rubric
- producing concrete prompt fixes until every style reaches 90+

## Input Model

### User-Written Fields

These fields describe the illustration content and usage.

| Field | Purpose | Example |
|---|---|---|
| Subject | Main scene or object | コーヒーを持って散歩している人 |
| Required elements | Must appear in the image | walking person, takeaway coffee cup, outdoor street |
| Avoid elements | Must not appear | sitting person, indoor cafe-only, text, logo |
| Use case | Where the illustration will be used | SaaS LP, article hero, SNS campaign, slide deck |
| Format | Canvas or production constraint | square, web hero, transparent background, thumbnail-readable |
| Tone | Emotional direction not covered by style | relaxed, morning, casual, warm |

### Thumbnail-Selected Fields

These fields should be selected visually.

| Selection | Backing Data | Current Source |
|---|---|---|
| Style group | `styleId`, label, reference thumbnails | `data/style_fingerprints.json`, local reference images |
| Taste | palette, density, finish discipline | `visualFingerprint`, reference baselines |
| Technique | line, texture, medium, shape language | `visualFingerprint`, `promptFragments` |
| Strength | how strongly style terms are enforced | future UI control, maps to prompt emphasis |

The first production scope is the 5 analyzed 2D styles:

- `naive_wobbly`
- `grain_flat`
- `print_relief`
- `editorial_outline`
- `flat_vector`

The broader 14-style HTML board remains useful as a discovery catalog, but only styles with local reference images and baselines can participate in the 90-point gate.

## Main Workflow

1. Analyze reference images.
2. Select a style from thumbnails.
3. Enter subject, elements, use case, and format constraints.
4. Generate prompt variants:
   - A: subject clarity
   - B: composition and palette
   - C: technique and texture
5. Generate images in Codex/ChatGPT under subscription use.
6. Run intake audit before import.
7. Import images into `generated/{run_id}/{style_id}/`.
8. Review candidates in the workbench.
9. Apply manual scores from CSV.
10. Run the gate.
11. If any style fails, prepare the next round.

## Current MVP Artifacts

| Need | Artifact |
|---|---|
| Reference analysis | `reports/reference_manifest.json`, `reports/reference_analysis.md`, `reports/reference_baselines.json` |
| Prompt source | `prompt_runs/{run_id}/{style_id}.md` |
| Generation plan | `prompt_runs/{run_id}/generation_plan.json`, `.md`, `generation_jobs.csv` |
| Codex prompt pack | `prompt_runs/{run_id}/codex_image_prompts.md`, `codex_prompts/*.txt` |
| Project hub | `reports/{run_id}_project_hub.html` |
| Operator checklist | `reports/{run_id}_operator_checklist.md` |
| Loop status | `python3 scripts/style_eval.py --loop-status {run_id}` |
| Run sync | `python3 scripts/style_eval.py --sync-run {run_id} [SOURCE_DIR]` |
| Intake audit | `python3 scripts/style_eval.py --intake-audit {run_id} [SOURCE_DIR]` |
| Review priority | `reports/{run_id}_review_priorities.md`, `reports/{run_id}_review_priorities.json` |
| Visual scoring | `reports/{run_id}_review_workbench.html` |
| Manual score validation/import | `reports/{run_id}_manual_review_template.csv`, `--validate-review-csv`, `--apply-review-csv` |
| Pass gate | `python3 scripts/style_eval.py --gate {run_id}` |
| Gate report | `reports/{run_id}_gate_report.md`, `reports/{run_id}_gate_report.html` |
| Next round | `python3 scripts/style_eval.py --prepare-next-round {source_run} {target_run}` |

## Scoring Requirements

A style is accepted only when at least one generated image for that style satisfies all conditions:

- final score is at least 90
- target style ranks first in automatic classification
- manual review exists
- `subjectAdherence >= 12`
- `textureMediumVisual >= 12`
- `stylePurity >= 8`
- no hard cap lowers the score below 90

The whole run is complete only when all 5 analyzed styles pass.

## UX Requirements

### Project Hub

The project hub is the operational entry point for a run:

```bash
python3 scripts/style_eval.py --project-hub coffee_walk_v1
```

Output:

```text
reports/coffee_walk_v1_project_hub.html
```

It links the prompt builder, Codex prompt pack, generation queue, dashboard, review workbench, visual review, evaluation report, and completion audit. It also shows the current loop phase and the next commands from `--loop-status`, so the user can proceed without guessing whether the run is waiting on generation, import cleanup, manual scoring, or a new prompt round.

### Prompt Builder Screen

The prompt builder should be the first screen when turning this into a UI. The current static implementation is:

```bash
python3 scripts/style_eval.py --prompt-builder
```

Output:

```text
reports/prompt_builder.html
```

Required regions:

- Subject form: user-written subject, required elements, avoid elements, use case, format, tone
- Style thumbnail grid: select one or more style cards
- Reference preview: local reference images for selected style
- Prompt preview: generated positive and negative prompt
- Variant preview: A/B/C variant focus
- Export controls: copy Codex prompt, write prompt pack, create generation plan

### Review Workbench Screen

Already implemented as a static artifact:

```text
reports/{run_id}_review_workbench.html
```

Required regions:

- generated candidate
- same-style reference thumbnails
- style fingerprint
- automatic score/rank/failure reasons
- 6 manual score inputs
- CSV export compatible with `--apply-review-csv`

## Non-Goals

- Do not depend on an OpenAI API key for generation.
- Do not train a model.
- Do not claim success from `style_selftest`; it only proves pipeline mechanics.
- Do not treat broad style preset selection as enough. The gate must compare generated images against the local reference set.

## Completion Definition

The active goal is complete only when:

1. `reports/reference_manifest.json` contains 37 references.
2. A real run has generated images for all 5 analyzed styles.
3. At least one image per style has manual review scores.
4. At least one image per style reaches the 90-point gate.
5. `python3 scripts/style_eval.py --gate {run_id}` exits `0`.

Until then, the tool can be considered usable infrastructure, but the goal is not complete.
