import { useEffect, useState } from "react";
import { api, type RunSummary } from "../api";

type Props = {
  runId: string;
  onRunIdChange: (runId: string) => void;
  onRunsLoaded?: (runs: RunSummary[]) => void;
};

export default function RunSelector({ runId, onRunIdChange, onRunsLoaded }: Props) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  async function reload() {
    setBusy(true);
    setError(null);
    try {
      const list = await api.runs();
      setRuns(list);
      onRunsLoaded?.(list);
      if (!runId && list.length > 0) {
        onRunIdChange(list[0].runId);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setConfirmDelete(false);
    setMsg(null);
  }, [runId]);

  async function deleteCurrentRun() {
    if (!runId) return;
    if (!confirmDelete) {
      setConfirmDelete(true);
      setError(null);
      setMsg(null);
      return;
    }

    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      await api.deleteRun(runId);
      const list = await api.runs();
      setRuns(list);
      onRunsLoaded?.(list);
      const next = list.find((r) => r.runId !== runId)?.runId ?? list[0]?.runId ?? "";
      onRunIdChange(next);
      setConfirmDelete(false);
      setMsg(`run「${runId}」を削除しました`);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const current = runs.find((r) => r.runId === runId);

  return (
    <div className="run-selector">
      <label className="run-selector-label">
        <span>Run</span>
        <select
          value={runId}
          onChange={(e) => onRunIdChange(e.target.value)}
          disabled={busy || runs.length === 0}
        >
          {runs.length === 0 && <option value="">（run なし）</option>}
          {runs.map((r) => (
            <option key={r.runId} value={r.runId}>
              {r.runId}
              {r.subject ? ` — ${r.subject}` : ""}
            </option>
          ))}
        </select>
      </label>
      {current?.subject && (
        <span className="run-selector-subject">題材: {current.subject}</span>
      )}
      <button type="button" className="ghost" onClick={reload} disabled={busy}>
        一覧更新
      </button>
      {runId && (
        <button
          type="button"
          className={confirmDelete ? "btn-danger" : "ghost danger-text"}
          onClick={deleteCurrentRun}
          disabled={busy}
        >
          {confirmDelete ? "本当に削除" : "run を削除"}
        </button>
      )}
      {confirmDelete && (
        <button
          type="button"
          className="ghost"
          onClick={() => setConfirmDelete(false)}
          disabled={busy}
        >
          キャンセル
        </button>
      )}
      {msg && <span className="ok-inline">{msg}</span>}
      {error && <span className="error inline">{error}</span>}
    </div>
  );
}
