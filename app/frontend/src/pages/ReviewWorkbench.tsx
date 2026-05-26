import { useCallback, useEffect, useState } from "react";
import {
  api,
  mediaUrl,
  type GateSummary,
  type ReviewRequest,
  type WorkbenchPayload,
  type WorkbenchRow,
} from "../api";

const AXIS_LABELS: Record<string, string> = {
  subjectAdherence: "主題",
  lineShapeLanguage: "線・形",
  textureMediumVisual: "質感",
  compositionIntent: "構図",
  stylePurity: "スタイル純度",
  productionUsefulness: "実用性",
};

type ScoreDraft = {
  scores: Record<string, string>;
  notes: string;
  hardCap: string;
  override: string;
};

function emptyDraft(axisOrder: string[]): ScoreDraft {
  const scores: Record<string, string> = {};
  for (const axis of axisOrder) scores[axis] = "";
  return { scores, notes: "", hardCap: "", override: "" };
}

function rowIsScored(row: WorkbenchRow, axisOrder: string[]): boolean {
  return axisOrder.every((_, index) => row.scoreValues[index] != null);
}

function draftIsComplete(draft: ScoreDraft, axisOrder: string[]): boolean {
  return axisOrder.every((axis) => draft.scores[axis]?.trim() !== "");
}

function maxScoreDraft(axisOrder: string[], manualAxes: Record<string, number>): Record<string, string> {
  const scores: Record<string, string> = {};
  for (const axis of axisOrder) {
    scores[axis] = String(manualAxes[axis]);
  }
  return scores;
}

function rowDraft(row: WorkbenchRow, axisOrder: string[]): ScoreDraft {
  const scores: Record<string, string> = {};
  axisOrder.forEach((axis, index) => {
    const value = row.scoreValues[index];
    scores[axis] = value == null ? "" : String(value);
  });
  return {
    scores,
    notes: row.notes ?? "",
    hardCap: row.hardCap == null ? "" : String(row.hardCap),
    override: row.override == null ? "" : String(row.override),
  };
}

function buildReviewItemFromDraft(
  row: WorkbenchRow,
  payload: WorkbenchPayload,
  draft: ScoreDraft,
): { item: ReviewRequest } | { error: string } {
  const scores: number[] = [];
  for (const axis of payload.axisOrder) {
    const raw = draft.scores[axis]?.trim();
    if (!raw) {
      return {
        error: `${row.labelJa} / ${row.imageName}: ${AXIS_LABELS[axis] ?? axis} の点数を入力してください`,
      };
    }
    scores.push(Number(raw));
  }

  return {
    item: {
      styleId: row.styleId,
      image: row.imageName,
      scores,
      notes: draft.notes,
      hardCap: draft.hardCap.trim() ? Number(draft.hardCap) : undefined,
      override: draft.override.trim() ? Number(draft.override) : undefined,
    },
  };
}

export default function ReviewWorkbench({
  runId,
  autoRefresh = false,
  onAutoRefreshDone,
}: {
  runId: string;
  autoRefresh?: boolean;
  onAutoRefreshDone?: () => void;
}) {
  const [payload, setPayload] = useState<WorkbenchPayload | null>(null);
  const [drafts, setDrafts] = useState<Record<string, ScoreDraft>>({});
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const reload = useCallback(async (refresh = false) => {
    if (!runId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.reviewWorkbench(runId, refresh);
      setPayload(data);
      const next: Record<string, ScoreDraft> = {};
      for (const row of data.rows) {
        next[row.imagePath] = rowDraft(row, data.axisOrder);
      }
      setDrafts(next);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [runId]);

  async function forceRefresh() {
    setBusyKey("__refresh__");
    try {
      await api.refreshEvaluation(runId);
      await reload(true);
      setMsg("評価レポートを再計算しました");
    } catch (e) {
      setError(String(e));
    } finally {
      setBusyKey(null);
    }
  }

  useEffect(() => {
    if (!runId) return;
    if (autoRefresh) {
      (async () => {
        setBusyKey("__refresh__");
        try {
          await api.refreshEvaluation(runId);
          await reload(true);
          setMsg("取り込み後の評価を再計算しました。6軸採点を入力してください。");
        } catch (e) {
          setError(String(e));
        } finally {
          setBusyKey(null);
          onAutoRefreshDone?.();
        }
      })();
      return;
    }
    reload();
  }, [runId, autoRefresh, reload, onAutoRefreshDone]);

  function updateDraft(imagePath: string, patch: Partial<ScoreDraft>) {
    setDrafts((prev) => ({
      ...prev,
      [imagePath]: { ...prev[imagePath], ...patch },
    }));
  }

  function fillMaxRow(imagePath: string) {
    if (!payload) return;
    const draft = drafts[imagePath] ?? emptyDraft(payload.axisOrder);
    updateDraft(imagePath, {
      scores: maxScoreDraft(payload.axisOrder, payload.manualAxes),
      notes: draft.notes,
      hardCap: draft.hardCap,
      override: draft.override,
    });
  }

  function clearRowDraft(imagePath: string) {
    if (!payload) return;
    const draft = drafts[imagePath] ?? emptyDraft(payload.axisOrder);
    updateDraft(imagePath, {
      ...emptyDraft(payload.axisOrder),
      notes: draft.notes,
      hardCap: draft.hardCap,
      override: draft.override,
    });
  }

  function fillMaxAllUnscored() {
    if (!payload) return;
    setDrafts((prev) => {
      const next = { ...prev };
      for (const row of payload.rows) {
        if (!row.exists || rowIsScored(row, payload.axisOrder)) continue;
        const current = next[row.imagePath] ?? rowDraft(row, payload.axisOrder);
        next[row.imagePath] = {
          ...current,
          scores: maxScoreDraft(payload.axisOrder, payload.manualAxes),
        };
      }
      return next;
    });
    setMsg("未採点行に満点を入力しました。内容を確認して保存してください。");
    setError(null);
  }

  function buildReviewItem(row: WorkbenchRow): ReviewRequest | null {
    if (!payload) return null;
    const draft = drafts[row.imagePath];
    if (!draft) return null;

    const result = buildReviewItemFromDraft(row, payload, draft);
    if ("error" in result) {
      setError(result.error);
      return null;
    }
    return result.item;
  }

  async function saveRow(row: WorkbenchRow) {
    if (!payload) return;
    const item = buildReviewItem(row);
    if (!item) return;

    setBusyKey(row.imagePath);
    setError(null);
    setMsg(null);
    try {
      await api.submitReview(runId, item);
      setMsg(`${row.labelJa} / ${row.imageName} を保存しました`);
      await reload();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusyKey(null);
    }
  }

  async function saveBatch(onlyUnscored = false) {
    if (!payload) return;
    const targets = payload.rows.filter((row) => {
      if (!row.exists) return false;
      if (onlyUnscored && rowIsScored(row, payload.axisOrder)) return false;
      return true;
    });

    if (targets.length === 0) {
      setError(
        onlyUnscored
          ? "保存対象の未採点行がありません"
          : "取り込み済みで採点入力がある行がありません",
      );
      return;
    }

    const reviews: ReviewRequest[] = [];
    for (const row of targets) {
      const draft = drafts[row.imagePath] ?? rowDraft(row, payload.axisOrder);
      const result = buildReviewItemFromDraft(row, payload, draft);
      if ("error" in result) {
        setError(result.error);
        return;
      }
      reviews.push(result.item);
    }

    setBusyKey(onlyUnscored ? "__batch_unscored__" : "__batch__");
    setError(null);
    setMsg(null);
    try {
      const result = await api.submitReviewsBatch(runId, reviews);
      if (result.failed > 0) {
        setError(result.errors.join("\n"));
      }
      setMsg(
        onlyUnscored
          ? `未採点 ${result.saved} 件を保存しました`
          : `${result.saved} 件を一括保存しました`,
      );
      await reload();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusyKey(null);
    }
  }

  const presentRows = payload?.rows.filter((row) => row.exists) ?? [];
  const scoredCount =
    payload?.rows.filter(
      (row) => row.exists && rowIsScored(row, payload.axisOrder),
    ).length ?? 0;
  const unscoredPresentCount = presentRows.length - scoredCount;
  const unscoredReadyCount =
    payload?.rows.filter((row) => {
      if (!row.exists || rowIsScored(row, payload.axisOrder)) return false;
      const draft = drafts[row.imagePath] ?? rowDraft(row, payload.axisOrder);
      return draftIsComplete(draft, payload.axisOrder);
    }).length ?? 0;
  const batchReady = presentRows.length > 0;
  const unscoredBatchReady = unscoredReadyCount > 0;

  const themeText =
    typeof payload?.theme === "string"
      ? payload.theme
      : payload?.theme?.ja ?? "";

  return (
    <div className="review-page">
      <div className="page-head">
        <div>
          <h2>採点</h2>
          <p className="hint">
            取り込み済み画像を6軸で採点。保存後にゲート判定へ進む。
            {themeText && <> 題材: {themeText}</>}
            {payload && presentRows.length > 0 && (
              <>
                {" "}
                採点済み {scoredCount}/{presentRows.length}
                {unscoredPresentCount > 0 && `（未採点 ${unscoredPresentCount}）`}
              </>
            )}
          </p>
        </div>
        <div className="head-actions review-toolbar">
          <button
            type="button"
            className="btn-primary"
            onClick={() => saveBatch(true)}
            disabled={!!busyKey || !unscoredBatchReady}
            title="サーバー上で未採点の行だけを保存（採点済みは上書きしません）"
          >
            {busyKey === "__batch_unscored__"
              ? "保存中…"
              : `未採点のみ保存${unscoredReadyCount > 0 ? ` (${unscoredReadyCount})` : ""}`}
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => saveBatch(false)}
            disabled={!!busyKey || !batchReady}
            title="取り込み済みの全行を保存（採点済みも上書き）"
          >
            {busyKey === "__batch__" ? "保存中…" : "すべて一括保存"}
          </button>
          <button
            type="button"
            onClick={fillMaxAllUnscored}
            disabled={!!busyKey || unscoredPresentCount === 0}
            title="未採点行の6軸すべてに満点を入力"
          >
            未採点に満点
          </button>
          <button
            type="button"
            onClick={() => forceRefresh()}
            disabled={!!busyKey}
          >
            {busyKey === "__refresh__" ? "再計算中…" : "評価を再計算"}
          </button>
          <button type="button" onClick={() => reload()} disabled={!!busyKey || loading}>
            更新
          </button>
        </div>
      </div>

      {loading && !payload && (
        <p className="hint loading-banner">採点データを読み込み中…（初回は数十秒かかることがあります）</p>
      )}

      {error && <div className="error global">{error}</div>}
      {msg && <div className="ok-banner">{msg}</div>}

      {payload && (
        <div className="review-grid">
          {payload.rows.map((row, index) => {
            const draft = drafts[row.imagePath] ?? emptyDraft(payload.axisOrder);
            const saving = busyKey === row.imagePath;
            const scored = rowIsScored(row, payload.axisOrder);
            const draftComplete = draftIsComplete(draft, payload.axisOrder);
            return (
              <article
                key={row.imagePath}
                className={
                  row.exists
                    ? scored
                      ? "review-card present scored"
                      : draftComplete
                        ? "review-card present ready"
                        : "review-card present unscored"
                    : "review-card missing"
                }
              >
                <div className="review-media">
                  <h3>
                    {String(index + 1).padStart(2, "0")}. {row.labelJa}{" "}
                    <code>{row.imageName}</code>
                  </h3>
                  <p className="hint">
                    variant {row.variant} / {row.variantFocus || "base"}
                  </p>
                  {row.exists && row.imageUrl ? (
                    <img
                      className="review-candidate"
                      src={mediaUrl(row.imageUrl)}
                      alt={row.imageName}
                    />
                  ) : (
                    <div className="review-missing">未取り込み</div>
                  )}
                  {row.referenceUrls.length > 0 && (
                    <div className="refs small">
                      {row.referenceUrls.slice(0, 6).map((url) => (
                        <img key={url} src={mediaUrl(url)} alt="" />
                      ))}
                    </div>
                  )}
                </div>

                <div className="review-form">
                  <div className="scoreline">
                    <span
                      className={
                        scored
                          ? row.passed
                            ? "pill pass"
                            : "pill fail"
                          : draftComplete
                            ? "pill ready"
                            : "pill pending"
                      }
                    >
                      {scored
                        ? row.passed
                          ? "合格"
                          : "未合格"
                        : draftComplete
                          ? "入力済・未保存"
                          : "未採点"}
                    </span>
                    <span>自動: {row.targetAutomaticScore ?? "-"} / 35</span>
                    <span>順位: {row.targetRank ?? "-"}</span>
                    <span>最終: {row.finalScore ?? "-"}</span>
                  </div>
                  {row.failureReasons.length > 0 && (
                    <p className="error">{row.failureReasons.join(", ")}</p>
                  )}

                  <div className="axis-grid">
                    {payload.axisOrder.map((axis) => (
                      <label key={axis}>
                        {AXIS_LABELS[axis] ?? axis}
                        <small> / {payload.manualAxes[axis]}</small>
                        <input
                          type="number"
                          min={0}
                          max={payload.manualAxes[axis]}
                          step={0.5}
                          value={draft.scores[axis]}
                          disabled={!row.exists || saving}
                          onChange={(e) =>
                            updateDraft(row.imagePath, {
                              scores: {
                                ...draft.scores,
                                [axis]: e.target.value,
                              },
                            })
                          }
                        />
                      </label>
                    ))}
                  </div>

                  <label>
                    メモ
                    <textarea
                      rows={2}
                      value={draft.notes}
                      disabled={!row.exists || saving}
                      onChange={(e) =>
                        updateDraft(row.imagePath, { notes: e.target.value })
                      }
                    />
                  </label>

                  <div className="row">
                    <label>
                      hardCap
                      <input
                        value={draft.hardCap}
                        disabled={!row.exists || saving}
                        onChange={(e) =>
                          updateDraft(row.imagePath, { hardCap: e.target.value })
                        }
                      />
                    </label>
                    <label>
                      override
                      <input
                        value={draft.override}
                        disabled={!row.exists || saving}
                        onChange={(e) =>
                          updateDraft(row.imagePath, { override: e.target.value })
                        }
                      />
                    </label>
                  </div>

                  <div className="review-row-actions">
                    <button
                      type="button"
                      disabled={!row.exists || saving}
                      onClick={() => fillMaxRow(row.imagePath)}
                    >
                      満点入力
                    </button>
                    <button
                      type="button"
                      className="ghost"
                      disabled={!row.exists || saving}
                      onClick={() => clearRowDraft(row.imagePath)}
                    >
                      点数クリア
                    </button>
                    <button
                      type="button"
                      className="btn-primary"
                      disabled={!row.exists || saving}
                      onClick={() => saveRow(row)}
                    >
                      {saving ? "保存中…" : scored ? "採点を更新" : "採点を保存"}
                    </button>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function GatePanel({
  runId,
  onRunSwitch,
}: {
  runId: string;
  onRunSwitch?: (runId: string) => void;
}) {
  const [gate, setGate] = useState<GateSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [targetRunId, setTargetRunId] = useState("");
  const [overwriteTarget, setOverwriteTarget] = useState(false);

  useEffect(() => {
    if (gate?.nextRun) {
      setTargetRunId(gate.nextRun);
    }
  }, [gate?.nextRun]);

  const reload = useCallback(async (refresh = false) => {
    if (!runId) return;
    setLoading(true);
    setError(null);
    try {
      setGate(await api.gateSummary(runId, refresh));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [runId]);

  async function runGateCli() {
    setBusy("gate");
    setError(null);
    setMsg(null);
    try {
      const result = await api.gateReport(runId);
      if (!result.ok) {
        setError(result.stderr || result.stdout || "ゲート判定に失敗しました");
      }
      await reload(true);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }

  async function prepareNext() {
    if (!gate) return;
    const trimmed = targetRunId.trim();
    if (!trimmed) {
      setError("次ラウンドの run ID を入力してください");
      return;
    }
    setBusy("next");
    setError(null);
    setMsg(null);
    try {
      const result = await api.prepareNextRound(runId, {
        targetRun: trimmed,
        overwrite: overwriteTarget,
      });
      const resolved =
        result.requestedTarget && result.requestedTarget !== result.targetRun
          ? `（「${result.requestedTarget}」は使用中のため「${result.targetRun}」を使用）`
          : "";
      setMsg(`次ラウンド「${result.targetRun}」を準備しました${resolved}`);
      onRunSwitch?.(result.targetRun);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }

  useEffect(() => {
    reload();
  }, [reload]);

  return (
    <section className="step-section gate-panel">
      <div className="step-head">
        <span className="step-num">4</span>
        <div>
          <h3>90点ゲート</h3>
          <p className="hint">
            全スタイルで90点以上・手動採点済みの候補が必要。合格:{" "}
            {gate?.summary.passedStyleCount ?? "-"} / {gate?.summary.styleCount ?? "-"}
          </p>
        </div>
        <button type="button" onClick={() => reload()} disabled={!!busy || loading}>
          状態更新
        </button>
      </div>

      {loading && !gate && (
        <p className="hint loading-banner">ゲート状態を読み込み中…</p>
      )}

      {error && <div className="error">{error}</div>}
      {msg && <div className="ok-banner">{msg}</div>}

      {gate && (
        <>
          <div
            className={
              gate.audit.complete ? "ok-banner gate-complete" : "blockers"
            }
          >
            {gate.audit.complete
              ? "全スタイル合格 — この run は完了です"
              : `未完了 — 合格 ${gate.summary.passedStyleCount}/${gate.summary.styleCount} スタイル`}
          </div>

          <div className="gate-styles">
            {gate.styleActions.map((action) => (
              <article
                key={action.styleId}
                className={`gate-style gate-${action.status}`}
              >
                <strong>{action.styleId}</strong>
                <span className="pill">{action.status}</span>
                <p>{action.nextAction}</p>
                {action.finalScore != null && (
                  <small>最終点: {action.finalScore}</small>
                )}
                {action.failureReasons && action.failureReasons.length > 0 && (
                  <p className="error">{action.failureReasons.join(", ")}</p>
                )}
              </article>
            ))}
          </div>

          <div className="form-actions">
            <button
              type="button"
              className="btn-primary"
              onClick={runGateCli}
              disabled={!!busy}
            >
              {busy === "gate" ? "実行中…" : "ゲートレポートを更新"}
            </button>
            {gate && !gate.audit.complete && (
              <div className="next-round-form">
                <label className="next-round-label">
                  <span>次ラウンド run ID</span>
                  <input
                    value={targetRunId}
                    onChange={(e) => setTargetRunId(e.target.value)}
                    placeholder={gate.nextRun}
                    disabled={!!busy}
                  />
                </label>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={overwriteTarget}
                    onChange={(e) => setOverwriteTarget(e.target.checked)}
                    disabled={!!busy}
                  />
                  同名 run があれば上書き
                </label>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={prepareNext}
                  disabled={!!busy || !targetRunId.trim()}
                >
                  {busy === "next" ? "準備中…" : "次ラウンドを準備"}
                </button>
              </div>
            )}
            <a
              className="link-button"
              href={`/reports/${runId}_gate_report.html`}
              target="_blank"
              rel="noreferrer"
            >
              詳細レポート
            </a>
          </div>
        </>
      )}
    </section>
  );
}
