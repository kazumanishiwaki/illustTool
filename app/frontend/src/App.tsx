import { useEffect, useState } from "react";
import { api, type StyleSummary } from "./api";
import RunSelector from "./components/RunSelector";
import { useLocalStorage } from "./hooks/useLocalStorage";
import { useAppRouter } from "./hooks/useAppRouter";
import PromptBuilder from "./pages/PromptBuilder";
import RunDashboard from "./pages/RunDashboard";
import ReviewWorkbench, { GatePanel } from "./pages/ReviewWorkbench";
import StyleSource from "./pages/StyleSource";
import "./App.css";

const TABS = [
  { id: "generate" as const, label: "イラスト生成", desc: "スタイル選択とプロンプト作成" },
  { id: "import" as const, label: "取り込み", desc: "生成画像の監査・取り込み" },
  { id: "review" as const, label: "採点・ゲート", desc: "手動採点と90点判定" },
  { id: "styles" as const, label: "スタイル設定", desc: "プロンプト断片の編集" },
];

export default function App() {
  const [styles, setStyles] = useState<StyleSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const [reviewAutoRefresh, setReviewAutoRefresh] = useState(false);
  const [runId, setRunId] = useLocalStorage("illustration-tool:runId", "");
  const [sourceDir, setSourceDir] = useLocalStorage(
    "illustration-tool:sourceDir",
    "",
  );
  const { tab, setTab } = useAppRouter(runId, setRunId);

  async function reloadStyles() {
    try {
      setStyles(await api.styles());
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    reloadStyles();
    api.health().then(
      () => setBackendOk(true),
      () => setBackendOk(false),
    );
  }, []);

  function goReview() {
    setReviewAutoRefresh(true);
    setTab("review");
  }

  return (
    <div className="app min-h-screen bg-stone-100 text-stone-900">
      <header className="app-header mb-4 rounded-lg border border-stone-200 bg-white p-5 shadow-sm">
        <div>
          <h1 className="text-xl font-bold tracking-tight">イラスト プロンプト工房</h1>
          <p className="sub mt-1 text-sm text-stone-500">
            題材を入力し、参考スタイルから生成プロンプトを作る。取り込み後に採点・90点ゲートへ進む。
          </p>
        </div>
        {backendOk === false && (
          <div className="error global backend-error mt-3">
            バックエンドに接続できません。8765 番ポートで API を起動してください。
          </div>
        )}
      </header>

      <RunSelector
        runId={runId}
        onRunIdChange={setRunId}
        onRunsLoaded={(runs) => {
          if (!runId && runs.length > 0) setRunId(runs[0].runId);
        }}
      />

      <nav className="tabs mb-4" aria-label="メイン">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={tab === t.id ? "active" : ""}
            onClick={() => {
              setTab(t.id);
              if (t.id === "styles") reloadStyles();
            }}
          >
            <span className="tab-label">{t.label}</span>
            <span className="tab-desc">{t.desc}</span>
          </button>
        ))}
      </nav>

      {error && <div className="error global">{error}</div>}

      {tab === "generate" && (
        <PromptBuilder
          styles={styles}
          runId={runId}
          onRunCreated={setRunId}
          onGoImport={() => setTab("import")}
        />
      )}
      {tab === "import" && (
        <RunDashboard
          runId={runId}
          sourceDir={sourceDir}
          onSourceDirChange={setSourceDir}
          onGoReview={goReview}
          onImportComplete={goReview}
        />
      )}
      {tab === "review" && runId && (
        <>
          <ReviewWorkbench
            runId={runId}
            autoRefresh={reviewAutoRefresh}
            onAutoRefreshDone={() => setReviewAutoRefresh(false)}
          />
          <div className="page gate-page">
            <GatePanel runId={runId} onRunSwitch={setRunId} />
          </div>
        </>
      )}
      {tab === "review" && !runId && (
        <div className="page">
          <p className="hint">Run を選択するか、イラスト生成タブで run を作成してください。</p>
        </div>
      )}
      {tab === "styles" && <StyleSource styles={styles} />}
    </div>
  );
}
