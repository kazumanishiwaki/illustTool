import { useEffect, useState } from "react";
import { api, type StyleSummary } from "./api";
import PromptBuilder from "./pages/PromptBuilder";
import RunDashboard from "./pages/RunDashboard";
import StyleSource from "./pages/StyleSource";
import "./App.css";

type Tab = "run" | "builder" | "source";

export default function App() {
  const [tab, setTab] = useState<Tab>("run");
  const [styles, setStyles] = useState<StyleSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function reloadStyles() {
    try {
      setStyles(await api.styles());
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    reloadStyles();
  }, []);

  return (
    <div className="app">
      <header>
        <h1>イラスト プロンプト工房</h1>
        <p className="sub">汎用イラスト生成プロンプト＋スタイル設定</p>
      </header>

      <nav className="tabs">
        <button
          className={tab === "run" ? "active" : ""}
          onClick={() => setTab("run")}
        >
          1. 評価ループ
        </button>
        <button
          className={tab === "builder" ? "active" : ""}
          onClick={() => setTab("builder")}
        >
          2. プロンプト作成
        </button>
        <button
          className={tab === "source" ? "active" : ""}
          onClick={() => {
            setTab("source");
            reloadStyles();
          }}
        >
          3. スタイル設定
        </button>
      </nav>

      {error && <div className="error global">{error}</div>}

      {tab === "run" && <RunDashboard />}
      {tab === "builder" && <PromptBuilder styles={styles} />}
      {tab === "source" && <StyleSource styles={styles} />}
    </div>
  );
}
