import { useEffect, useState } from "react";
import {
  api,
  type CommandResult,
  type GenerationSlot,
  type GenerationSlots,
  type RunStatus,
} from "../api";

const RUN_ID = "coffee_walk_v1";

export default function RunDashboard() {
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [slots, setSlots] = useState<GenerationSlots | null>(null);
  const [lastCommand, setLastCommand] = useState<CommandResult | null>(null);
  const [syncResult, setSyncResult] = useState<Record<string, unknown> | null>(null);
  const [sourceDir, setSourceDir] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function reload() {
    setError(null);
    try {
      setStatus(await api.runStatus(RUN_ID));
      setSlots(await api.generationSlots(RUN_ID));
    } catch (e) {
      setError(String(e));
    }
  }

  async function sync() {
    setBusy("sync");
    setError(null);
    try {
      const result = await api.syncRun(RUN_ID, sourceDir);
      setSyncResult(result);
      await reload();
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
  }, []);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2>評価ループ</h2>
          <p className="hint">
            coffee_walk_v1 の生成・レビュー・90点ゲートの現在状態。
          </p>
        </div>
        <button onClick={reload} disabled={!!busy}>
          更新
        </button>
      </div>

      {error && <div className="error global">{error}</div>}

      {status && (
        <div className="run-grid">
          <section className="run-main">
            <div className={`phase phase-${status.phase}`}>
              <span>{status.phase}</span>
              <strong>{status.title}</strong>
            </div>
            <p>{status.nextAction}</p>
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
            {status.blockers.length > 0 && (
              <div className="blockers">
                <strong>Blockers</strong>
                <ul>
                  {status.blockers.map((b) => (
                    <li key={b}>{b}</li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          <aside className="run-side">
            <button
              onClick={() =>
                run("generationPlan", () => api.generationPlan(RUN_ID))
              }
              disabled={!!busy}
            >
              生成計画を再作成
            </button>
            <button
              onClick={() => run("promptPack", () => api.promptPack(RUN_ID))}
              disabled={!!busy}
            >
              Codexプロンプトパック作成
            </button>
            <button
              onClick={() => run("refresh", () => api.refreshRun(RUN_ID))}
              disabled={!!busy}
            >
              レポート更新
            </button>
            <button
              onClick={() => run("gate", () => api.gateReport(RUN_ID))}
              disabled={!!busy}
            >
              ゲートレポート作成
            </button>
            {busy && <small className="hint">実行中: {busy}</small>}
          </aside>
        </div>
      )}

      {slots && (
        <section className="slot-panel">
          <div className="page-head">
            <div>
              <h3>生成スロット</h3>
              <p className="hint">
                {slots.present}/{slots.expected} 生成済み、{slots.missing} 枚不足
              </p>
            </div>
            <a
              className="link-button"
              href="/reports/coffee_walk_v1_project_hub.html"
              target="_blank"
            >
              Project Hub
            </a>
          </div>
          <div className="sync-row">
            <input
              value={sourceDir}
              onChange={(e) => setSourceDir(e.target.value)}
              placeholder="/path/to/saved/codex/images"
            />
            <button onClick={sync} disabled={!!busy}>
              監査・取り込み
            </button>
          </div>
          <div className="slot-grid">
            {slots.slots.map((slot) => (
              <SlotCard key={`${slot.styleId}-${slot.variantLabel}`} slot={slot} />
            ))}
          </div>
        </section>
      )}

      {status && (
        <details>
          <summary>次に使うコマンド</summary>
          <pre>{status.commands.join("\n")}</pre>
        </details>
      )}

      {lastCommand && (
        <details open>
          <summary>直近の実行結果</summary>
          <pre>{lastCommand.command}</pre>
          <pre>{lastCommand.stdout || lastCommand.stderr || "(no output)"}</pre>
        </details>
      )}

      {syncResult && (
        <details open>
          <summary>取り込み結果</summary>
          <pre>{JSON.stringify(syncResult, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}

function SlotCard({ slot }: { slot: GenerationSlot }) {
  return (
    <article className={slot.exists ? "slot-card ready" : "slot-card"}>
      <div className="slot-head">
        <strong>
          {String(slot.sequence).padStart(2, "0")} {slot.labelJa}
        </strong>
        <span>{slot.exists ? "OK" : "missing"}</span>
      </div>
      <small>{slot.styleId} / {slot.variantLabel}</small>
      <p>{slot.variantFocus}</p>
      <button onClick={() => navigator.clipboard.writeText(slot.positivePrompt)}>
        プロンプトコピー
      </button>
      <code>{slot.promptFile}</code>
      <code>{slot.outputName}</code>
    </article>
  );
}
