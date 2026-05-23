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
};

export type ComposeResult = {
  styleId: string;
  positive: string;
  negative: string;
  variants: { label: string; focus: string; positive: string; negative: string }[];
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

async function jget<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json() as Promise<T>;
}

async function jpost<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json() as Promise<T>;
}

async function jput<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
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
  syncRun: (runId: string, sourceDir: string) =>
    jpost<Record<string, unknown>>(`/api/runs/${runId}/sync`, { sourceDir }),
};

export const assetUrl = (relPath: string) =>
  `${BASE}/references/${relPath.split("/").map(encodeURIComponent).join("/")}`;

export const projectAssetUrl = (relPath: string) =>
  `${BASE}/${relPath.split("/").map(encodeURIComponent).join("/")}`;
