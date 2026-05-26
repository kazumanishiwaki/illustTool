const BASE = import.meta.env.VITE_API_BASE ?? "";

export type StyleSummary = {
  id: string;
  labelJa: string;
  styleFamilyJa: string;
  referenceImages: string[];
  previewImage: string;
  styleDifferentiator: string;
  visualFingerprint: Record<string, string>;
};

export type StyleDetail = {
  id: string;
  labelJa: string;
  styleFamilyJa: string;
  referenceGlob: string;
  referenceImages: string[];
  previewImage: string;
  styleDifferentiator: string;
  visualFingerprint: Record<string, string>;
  visualFingerprintJa: Record<string, string>;
  promptFragments: string[];
  promptFragmentsJa: string[];
  negativeFragments: string[];
  negativeFragmentsJa: string[];
  improvementRules: Record<string, string>;
  improvementRulesJa: Record<string, string>;
  styleScoringWeights: Record<string, number>;
};

export type StyleUpdate = {
  labelJa?: string;
  visualFingerprint?: Record<string, string>;
  visualFingerprintJa?: Record<string, string>;
  promptFragments?: string[];
  promptFragmentsJa?: string[];
  negativeFragments?: string[];
  negativeFragmentsJa?: string[];
  improvementRules?: Record<string, string>;
  improvementRulesJa?: Record<string, string>;
};

export type ComposeRequest = {
  styleId: string;
  subject: string;
  requiredElements: string[];
  avoidElements: string[];
  useCase: string;
  format: string;
  tone: string;
  strength?: number;
};

export type ComposeBatchRequest = Omit<ComposeRequest, "styleId"> & {
  styleIds?: string[];
};

export type ComposeResult = {
  styleId: string;
  positive: string;
  negative: string;
  strength?: number;
  variants: { label: string; focus: string; positive: string; negative: string }[];
};

export type ComposeBatchResult = {
  styleIds: string[];
  results: ComposeResult[];
};

export type CreateRunRequest = {
  runId?: string;
  subject: string;
  requiredElements: string[];
  avoidElements: string[];
  useCase: string;
  format: string;
  tone: string;
  strength?: number;
  overwrite?: boolean;
};

export type RunSummary = {
  runId: string;
  subject: string;
  createdAt: string;
  hasPlan: boolean;
  updatedAt: string;
};

export type RunMeta = CreateRunRequest & {
  runId: string;
  basePromptEn?: string;
  createdAt?: string;
  styleIds?: string[];
};

export type RunStatus = {
  runId: string;
  phase: string;
  title: string;
  nextAction: string;
  blockers: string[];
  commands: string[];
  summary: {
    styleCount: number;
    generatedImageCount: number;
    reviewedImageCount: number;
    passedStyleCount: number;
    allStylesPassed: boolean;
    missingStyles: string[];
    pendingReviewStyles: string[];
    failedStyles: string[];
  };
};

export type CommandResult = {
  ok: boolean;
  returnCode: number;
  command: string;
  stdout: string;
  stderr: string;
};

export type GenerationSlot = {
  sequence: number;
  styleId: string;
  labelJa: string;
  variant: number;
  variantLabel: string;
  variantFocus: string;
  positivePrompt: string;
  negativePrompt: string;
  outputPath: string;
  outputName: string;
  exists: boolean;
  imageUrl?: string;
  promptPath: string;
  promptFile: string;
};

export type GenerationSlots = {
  runId: string;
  expected: number;
  present: number;
  missing: number;
  slots: GenerationSlot[];
};

export type ReviewRequest = {
  styleId: string;
  image: string;
  scores: number[];
  notes?: string;
  hardCap?: number;
  override?: number;
};

export type WorkbenchRow = {
  styleId: string;
  labelJa: string;
  variant: number;
  variantFocus: string;
  imageName: string;
  imagePath: string;
  imageUrl: string;
  exists: boolean;
  targetAutomaticScore: number | null;
  targetRank: number | null;
  finalScore: number | null;
  passed: boolean | null;
  failureReasons: string[];
  manualAxes: Record<string, number>;
  scoreValues: (number | null)[];
  notes: string;
  hardCap: number | null;
  override: number | null;
  referenceUrls: string[];
  fingerprint: Record<string, string>;
  negativeFragments: string[];
};

export type WorkbenchPayload = {
  runId: string;
  theme: { ja?: string } | string;
  manualAxes: Record<string, number>;
  axisOrder: string[];
  passScore: number;
  rows: WorkbenchRow[];
};

export type IntakeAudit = {
  runId?: string;
  expected?: number;
  present?: number;
  missing?: number;
  unreadable?: number;
  ambiguous?: number;
  duplicateItemCount?: number;
  ready?: boolean;
  rows?: {
    sequence?: number;
    labelJa?: string;
    expectedFileName?: string;
    issues?: string[];
    actionNeeded?: string;
  }[];
};

export type SyncResult = {
  runId?: string;
  imported?: boolean;
  sourceAudit?: IntakeAudit;
  blockingRows?: unknown[];
  import?: Record<string, unknown>;
};

export type GateStyleAction = {
  styleId: string;
  status: string;
  bestImage: string | null;
  nextAction: string;
  commandHint?: string;
  failureReasons?: string[];
  finalScore?: number | null;
  targetAutomaticScore?: number | null;
  targetRank?: number | null;
};

export type GateSummary = {
  runId: string;
  nextRun: string;
  theme: string;
  summary: RunStatus["summary"];
  audit: { complete: boolean };
  loop: Partial<RunStatus>;
  styleActions: GateStyleAction[];
};

async function parseError(r: Response): Promise<string> {
  try {
    const body = (await r.json()) as { detail?: string };
    if (body.detail) return body.detail;
  } catch {
    // ignore
  }
  return `${r.status} ${r.statusText}`;
}

async function jdelete<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { method: "DELETE" });
  if (!r.ok) throw new Error(await parseError(r));
  return r.json() as Promise<T>;
}

async function jget<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(await parseError(r));
  return r.json() as Promise<T>;
}

async function jpost<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(await parseError(r));
  return r.json() as Promise<T>;
}

async function jput<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await parseError(r));
  return r.json() as Promise<T>;
}

export const api = {
  health: () => jget<{ status: string }>("/api/health"),
  styles: () => jget<StyleSummary[]>("/api/styles"),
  style: (id: string) => jget<StyleDetail>(`/api/styles/${id}`),
  updateStyle: (id: string, patch: StyleUpdate) =>
    jput<StyleDetail>(`/api/styles/${id}`, patch),
  compose: (req: ComposeRequest) =>
    jpost<ComposeResult>("/api/prompts/compose", req),
  composeBatch: (req: ComposeBatchRequest) =>
    jpost<ComposeBatchResult>("/api/prompts/compose-batch", req),
  runs: () => jget<RunSummary[]>("/api/runs"),
  createRun: (req: CreateRunRequest) =>
    jpost<{ runId: string; meta: RunMeta }>("/api/runs", req),
  runMeta: (runId: string) => jget<RunMeta>(`/api/runs/${runId}/meta`),
  exportRun: (runId: string) =>
    jpost<{ runId: string; exported: boolean }>(`/api/runs/${runId}/export`),
  runStatus: (runId: string) => jget<RunStatus>(`/api/runs/${runId}/status`),
  generationSlots: (runId: string) =>
    jget<GenerationSlots>(`/api/runs/${runId}/slots`),
  promptPack: (runId: string) =>
    jpost<CommandResult>(`/api/runs/${runId}/prompt-pack`),
  generationPlan: (runId: string, variants = 3) =>
    jpost<CommandResult>(`/api/runs/${runId}/plan?variants=${variants}`),
  refreshRun: (runId: string) =>
    jpost<CommandResult>(`/api/runs/${runId}/refresh`),
  gateReport: (runId: string) =>
    jget<CommandResult>(`/api/runs/${runId}/gate`),
  gateSummary: (runId: string, refresh = false) =>
    jget<GateSummary>(
      `/api/runs/${runId}/gate/summary${refresh ? "?refresh=true" : ""}`,
    ),
  reviewWorkbench: (runId: string, refresh = false) =>
    jget<WorkbenchPayload>(
      `/api/runs/${runId}/reviews/workbench${refresh ? "?refresh=true" : ""}`,
    ),
  refreshEvaluation: (runId: string) =>
    jpost<{ runId: string; refreshed: boolean }>(
      `/api/runs/${runId}/evaluation/refresh`,
    ),
  prepareNextRound: (
    runId: string,
    req: { targetRun?: string; variants?: number; overwrite?: boolean } = {},
  ) =>
    jpost<{
      sourceRun: string;
      targetRun: string;
      requestedTarget?: string;
      variantsPerStyle: number;
      sourceSummary: RunStatus["summary"];
      paths: Record<string, string>;
    }>(`/api/runs/${runId}/next-round`, {
      targetRun: req.targetRun ?? "",
      variants: req.variants ?? 3,
      overwrite: req.overwrite ?? false,
    }),
  deleteRun: (runId: string) =>
    jdelete<{ runId: string; deleted: boolean }>(`/api/runs/${runId}`),
  submitReview: (runId: string, req: ReviewRequest) =>
    jpost<CommandResult>(`/api/runs/${runId}/reviews`, req),
  submitReviewsBatch: (runId: string, reviews: ReviewRequest[]) =>
    jpost<{
      runId: string;
      saved: number;
      failed: number;
      results: { styleId: string; image: string; ok: boolean }[];
      errors: string[];
      ok: boolean;
    }>(`/api/runs/${runId}/reviews/batch`, { reviews }),
  intakeAudit: (runId: string, sourceDir: string) =>
    jpost<IntakeAudit>(`/api/runs/${runId}/intake-audit`, {
      sourceDir,
    }),
  syncRun: (runId: string, sourceDir: string) =>
    jpost<SyncResult>(`/api/runs/${runId}/sync`, { sourceDir }),
};

export const assetUrl = (relPath: string) =>
  `${BASE}/references/${relPath.split("/").map(encodeURIComponent).join("/")}`;

export const projectAssetUrl = (relPath: string) =>
  `${BASE}/${relPath.split("/").map(encodeURIComponent).join("/")}`;

export const mediaUrl = (url: string) =>
  url.startsWith("http") ? url : `${BASE}${url}`;
