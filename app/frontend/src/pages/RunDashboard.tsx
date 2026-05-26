import { useCallback, useEffect, useState } from "react";
import {
  api,
  mediaUrl,
  type CommandResult,
  type GenerationSlot,
  type GenerationSlots,
  type IntakeAudit,
  type SyncResult,
  type RunStatus,
} from "../api";
import {
  summarizeIntakeAudit,
} from "../utils/intakeAuditSummary";

type Props = {
  runId: string;
  sourceDir: string;
  onSourceDirChange: (value: string) => void;
  onGoReview?: () => void;
  onImportComplete?: (presentCount: number) => void;
};

function AuditSummary({ audit }: { audit: IntakeAudit }) {
  const summary = summarizeIntakeAudit(audit);
  return (
    <div className={summary.ok ? "ok-banner audit-summary" : "blockers audit-summary"}>
      <strong>{summary.headline}</strong>
      {summary.bullets.length > 0 && (
        <ul>
          {summary.bullets.map((b) => (
            <li key={b}>{b}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function RunDashboard({
  runId,
  sourceDir,
  onSourceDirChange,
  onGoReview,
  onImportComplete,
}: Props) {
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [slots, setSlots] = useState<GenerationSlots | null>(null);
  const [lastCommand, setLastCommand] = useState<CommandResult | null>(null);
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null);
  const [auditResult, setAuditResult] = useState<IntakeAudit | null>(null);
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!runId) return;
    setError(null);
    try {
      setStatus(await api.runStatus(runId));
      setSlots(await api.generationSlots(runId));
    } catch (e) {
      setError(String(e));
    }
  }, [runId]);

  async function audit() {
    if (!runId) return;
    setBusy("audit");
    setError(null);
    setImportMsg(null);
    try {
      setAuditResult(await api.intakeAudit(runId, sourceDir));
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }

  async function sync() {
    if (!runId) return;
    setBusy("sync");
    setError(null);
    setImportMsg(null);
    const beforePresent = slots?.present ?? 0;
    try {
      const result = await api.syncRun(runId, sourceDir);
      setSyncResult(result);
      const newStatus = await api.runStatus(runId);
      const newSlots = await api.generationSlots(runId);
      setStatus(newStatus);
      setSlots(newSlots);

      const sourceAudit = result.sourceAudit as IntakeAudit | undefined;
      if (sourceAudit) {
        setAuditResult(sourceAudit);
      }

      if (result.imported === false && result.blockingRows) {
        setError("監査で問題があり、取り込みをスキップしました。上の監査結果を確認してください。");
        return;
      }

      if (newSlots.present > beforePresent) {
        setImportMsg(
          `${newSlots.present - beforePresent} 枚を取り込みました（合計 ${newSlots.present}/${newSlots.expected}）`,
        );
        onImportComplete?.(newSlots.present);
      } else if (newSlots.present > 0) {
        setImportMsg(`取り込み済み ${newSlots.present}/${newSlots.expected} 枚`);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }

  async function run(label: string, action: () => Promise<CommandResult>) {
    setBusy(label);
    setError(null);
    try {
      const result = await action();
      setLastCommand(result);
      await reload();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }

  useEffect(() => {
    reload();
  }, [reload]);

  if (!runId) {
    return (
      <div className="page">
        <p className="hint">
          上部で run を選択するか、イラスト生成タブで「5スタイル run を作成」してください。
        </p>
      </div>
    );
  }

  return (
    <div className="page import-page">
      <div className="page-head">
        <div>
          <h2>取り込み</h2>
          <p className="hint">
            外部ツールで生成した画像を監査・取り込み。run: <code>{runId}</code>
          </p>
        </div>
        <button type="button" onClick={reload} disabled={!!busy}>
          状態を更新
        </button>
      </div>

      <ol className="workflow-steps compact" aria-label="取り込みの流れ">
        <li>プロンプトで画像生成</li>
        <li className="current">監査・取り込み</li>
        <li>採点・ゲート</li>
      </ol>

      {error && <div className="error global">{error}</div>}
      {importMsg && (
        <div className="ok-banner import-complete">
          <span>{importMsg}</span>
          {onGoReview && (slots?.present ?? 0) > 0 && (
            <button type="button" className="btn-primary" onClick={onGoReview}>
              採点タブへ進む（評価を再計算）
            </button>
          )}
        </div>
      )}

      <section className="step-section" aria-labelledby="import-section">
        <div className="step-head">
          <span className="step-num">1</span>
          <div>
            <h3 id="import-section">保存フォルダ</h3>
            <p className="hint">
              Codex / ChatGPT で保存した画像フォルダのパス。次回も記憶されます。
            </p>
          </div>
        </div>
        <div className="sync-row">
          <input
            value={sourceDir}
            onChange={(e) => onSourceDirChange(e.target.value)}
            placeholder="/path/to/saved/codex/images"
          />
          <button
            type="button"
            onClick={audit}
            disabled={!!busy || !sourceDir.trim()}
          >
            {busy === "audit" ? "監査中…" : "取り込み前監査"}
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={sync}
            disabled={!!busy || !sourceDir.trim()}
          >
            {busy === "sync" ? "取り込み中…" : "監査・取り込み"}
          </button>
        </div>
        {auditResult && <AuditSummary audit={auditResult} />}
        {syncResult && (
          <details className="log-details">
            <summary>詳細ログ（開発者向け）</summary>
            <pre>{JSON.stringify(syncResult, null, 2)}</pre>
          </details>
        )}
      </section>

      {slots && (
        <section className="step-section" aria-labelledby="slots-section">
          <div className="step-head">
            <span className="step-num">2</span>
            <div>
              <h3 id="slots-section">生成スロット</h3>
              <p className="hint">
                {slots.present}/{slots.expected} 枚取り込み済み
                {slots.missing > 0 && `、${slots.missing} 枚不足`}
              </p>
            </div>
            <div className="head-actions">
              {onGoReview && slots.present > 0 && (
                <button type="button" className="btn-primary" onClick={onGoReview}>
                  採点へ進む
                </button>
              )}
              <a
                className="link-button"
                href={`/reports/${runId}_project_hub.html`}
                target="_blank"
                rel="noreferrer"
              >
                Project Hub
              </a>
            </div>
          </div>
          <div className="slot-grid">
            {slots.slots.map((slot) => (
              <SlotCard key={`${slot.styleId}-${slot.variantLabel}`} slot={slot} />
            ))}
          </div>
        </section>
      )}

      {status && (
        <section className="step-section" aria-labelledby="status-section">
          <div className="step-head">
            <span className="step-num">3</span>
            <div>
              <h3 id="status-section">ループ状態</h3>
              <p className="hint">{status.nextAction}</p>
            </div>
          </div>

          <div className="run-status-bar">
            <div className={`phase phase-${status.phase}`}>
              <span>{status.phase}</span>
              <strong>{status.title}</strong>
            </div>
            <div className="metrics">
              <div>
                <strong>{status.summary.generatedImageCount}</strong>
                <small>生成済み</small>
              </div>
              <div>
                <strong>{status.summary.reviewedImageCount}</strong>
                <small>レビュー済み</small>
              </div>
              <div>
                <strong>
                  {status.summary.passedStyleCount}/{status.summary.styleCount}
                </strong>
                <small>合格スタイル</small>
              </div>
            </div>
          </div>

          {status.blockers.length > 0 && (
            <div className="blockers">
              <strong>進行を止めている項目</strong>
              <ul>
                {status.blockers.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            </div>
          )}

          <details className="operator-panel">
            <summary>運用コマンド（上級者向け）</summary>
            <div className="operator-actions">
              <button
                type="button"
                onClick={() =>
                  run("generationPlan", () => api.generationPlan(runId))
                }
                disabled={!!busy}
              >
                生成計画を再作成
              </button>
              <button
                type="button"
                onClick={() => run("promptPack", () => api.promptPack(runId))}
                disabled={!!busy}
              >
                Codexプロンプトパック作成
              </button>
              <button
                type="button"
                onClick={() => run("refresh", () => api.refreshRun(runId))}
                disabled={!!busy}
              >
                レポート更新
              </button>
            </div>
            {busy && <p className="hint">実行中: {busy}</p>}
            {lastCommand && (
              <details className="log-details">
                <summary>直近の CLI 実行結果</summary>
                <pre>{lastCommand.command}</pre>
                <pre>
                  {lastCommand.stdout || lastCommand.stderr || "(no output)"}
                </pre>
              </details>
            )}
          </details>
        </section>
      )}
    </div>
  );
}

function SlotCard({ slot }: { slot: GenerationSlot }) {
  const [copied, setCopied] = useState(false);

  async function copyPrompt() {
    try {
      await navigator.clipboard.writeText(slot.positivePrompt);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore
    }
  }

  return (
    <article className={slot.exists ? "slot-card ready" : "slot-card"}>
      {slot.exists && slot.imageUrl && (
        <img
          className="slot-thumb"
          src={mediaUrl(slot.imageUrl)}
          alt={slot.outputName}
        />
      )}
      <div className="slot-head">
        <strong>
          {String(slot.sequence).padStart(2, "0")} {slot.labelJa}
        </strong>
        <span>{slot.exists ? "取り込み済" : "未取り込み"}</span>
      </div>
      <small>
        {slot.styleId} / {slot.variantLabel}
      </small>
      <p>{slot.variantFocus}</p>
      <button type="button" className="btn-primary" onClick={copyPrompt}>
        {copied ? "コピー済み" : "プロンプトをコピー"}
      </button>
      <code>{slot.outputName}</code>
    </article>
  );
}
