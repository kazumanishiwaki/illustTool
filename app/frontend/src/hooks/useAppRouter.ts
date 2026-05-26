import { useCallback, useEffect, useState } from "react";
import { APP_TABS, type AppTab } from "../constants/runStyles";

function parseHash(): { tab: AppTab; runId: string | null } {
  const raw = window.location.hash.replace(/^#\/?/, "");
  const [pathPart, queryPart] = raw.split("?");
  const tab = APP_TABS.includes(pathPart as AppTab) ? (pathPart as AppTab) : "generate";
  const params = new URLSearchParams(queryPart || "");
  return { tab, runId: params.get("run") };
}

function buildHash(tab: AppTab, runId?: string): string {
  const query = runId?.trim() ? `?run=${encodeURIComponent(runId.trim())}` : "";
  return `#/${tab}${query}`;
}

export function useAppRouter(
  runId: string,
  setRunId: (value: string) => void,
) {
  const [tab, setTabState] = useState<AppTab>(() => parseHash().tab);

  const syncFromHash = useCallback(() => {
    const parsed = parseHash();
    setTabState(parsed.tab);
    if (parsed.runId && parsed.runId !== runId) {
      setRunId(parsed.runId);
    }
  }, [runId, setRunId]);

  useEffect(() => {
    if (!window.location.hash) {
      window.location.hash = buildHash("generate", runId);
      return;
    }
    syncFromHash();
    window.addEventListener("hashchange", syncFromHash);
    return () => window.removeEventListener("hashchange", syncFromHash);
  }, [syncFromHash, runId]);

  useEffect(() => {
    const parsed = parseHash();
    if (parsed.runId === runId) return;
    const next = buildHash(tab, runId);
    if (window.location.hash !== next) {
      window.location.hash = next;
    }
  }, [runId, tab]);

  const setTab = useCallback(
    (nextTab: AppTab) => {
      window.location.hash = buildHash(nextTab, runId);
      setTabState(nextTab);
    },
    [runId],
  );

  return { tab, setTab };
}
