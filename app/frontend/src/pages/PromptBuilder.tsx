import { useEffect, useState } from "react";
import {
  api,
  assetUrl,
  projectAssetUrl,
  type ComposeBatchResult,
  type ComposeResult,
  type StyleSummary,
} from "../api";
import { DEFAULT_RUN_STYLE_IDS } from "../constants/runStyles";
import { useLocalStorage } from "../hooks/useLocalStorage";

type Form = {
  subject: string;
  required: string;
  avoid: string;
  useCase: string;
  format: string;
  tone: string;
  strength: number;
};

const EMPTY_FORM: Form = {
  subject: "",
  required: "",
  avoid: "",
  useCase: "",
  format: "",
  tone: "",
  strength: 70,
};

const USE_CASE_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "（指定なし）" },
  { value: "SaaS landing page", label: "SaaS LP / ランディングページ" },
  { value: "article hero illustration", label: "記事ヘッダ / ブログヘッダ" },
  { value: "social media campaign", label: "SNSバナー / キャンペーン" },
  { value: "presentation slide deck", label: "スライド資料 / プレゼン" },
  { value: "newsletter / email", label: "メルマガ / ニュースレター" },
  { value: "in-app illustration", label: "アプリ内イラスト" },
  { value: "print flyer / poster", label: "印刷物 / フライヤー" },
  { value: "advertising banner", label: "広告バナー" },
  { value: "book cover / editorial", label: "書籍カバー / 雑誌" },
  { value: "icon / avatar", label: "アイコン / アバター" },
];

const FORMAT_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "（指定なし）" },
  { value: "square 1:1", label: "正方形（square 1:1）" },
  { value: "web hero 16:9", label: "ワイド（web hero 16:9）" },
  { value: "portrait 9:16", label: "縦長（portrait 9:16）" },
  { value: "banner 3:1", label: "横長バナー（banner 3:1）" },
  { value: "thumbnail-readable", label: "サムネで読める（thumbnail-readable）" },
  { value: "transparent background", label: "透明背景（transparent background）" },
  { value: "print-ready CMYK", label: "印刷向け（print-ready CMYK）" },
  { value: "vertical mobile hero", label: "モバイル縦（vertical mobile hero）" },
];

const TONE_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "（指定なし）" },
  { value: "warm, morning", label: "温かみ・朝（warm, morning）" },
  { value: "calm, soft", label: "落ち着き・やわらか（calm, soft）" },
  { value: "playful, cheerful", label: "遊び心・陽気（playful, cheerful）" },
  { value: "minimal, quiet", label: "ミニマル・静か（minimal, quiet）" },
  { value: "professional, confident", label: "端正・自信（professional, confident）" },
  { value: "friendly, casual", label: "親しみ・カジュアル（friendly, casual）" },
  { value: "modern, clean", label: "モダン・クリーン（modern, clean）" },
  { value: "elegant, refined", label: "上品・洗練（elegant, refined）" },
  { value: "energetic, dynamic", label: "活発・躍動（energetic, dynamic）" },
  { value: "nostalgic, retro", label: "ノスタルジック・レトロ（nostalgic, retro）" },
  { value: "mysterious, moody", label: "ミステリアス・陰影（mysterious, moody）" },
];

function groupStyles(styles: StyleSummary[]) {
  const groups: { family: string; styles: StyleSummary[] }[] = [];
  for (const style of styles) {
    const family = style.styleFamilyJa || "その他";
    const last = groups[groups.length - 1];
    if (last?.family === family) {
      last.styles.push(style);
    } else {
      groups.push({ family, styles: [style] });
    }
  }
  return groups;
}

function CopyButton({
  text,
  label = "コピー",
}: {
  text: string;
  label?: string;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore
    }
  }

  return (
    <button type="button" className="btn-primary" onClick={copy}>
      {copied ? "コピー済み" : label}
    </button>
  );
}

export default function PromptBuilder({
  styles,
  runId,
  onRunCreated,
  onGoImport,
}: {
  styles: StyleSummary[];
  runId?: string;
  onRunCreated?: (runId: string) => void;
  onGoImport?: () => void;
}) {
  const [styleId, setStyleId] = useState<string>("");
  const [form, setForm] = useLocalStorage<Form>(
    "illustration-tool:generateForm",
    EMPTY_FORM,
  );
  const [result, setResult] = useState<ComposeResult | null>(null);
  const [batchResults, setBatchResults] = useState<ComposeBatchResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (!styleId && styles.length > 0) setStyleId(styles[0].id);
  }, [styles, styleId]);

  useEffect(() => {
    if (!runId) return;
    api
      .runMeta(runId)
      .then((meta) => {
        setForm({
          subject: meta.subject ?? "",
          required: (meta.requiredElements ?? []).join(", "),
          avoid: (meta.avoidElements ?? []).join(", "),
          useCase: meta.useCase ?? "",
          format: meta.format ?? "",
          tone: meta.tone ?? "",
          strength: meta.strength ?? 70,
        });
      })
      .catch(() => {
        // legacy run without meta — ignore
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  function formPayload() {
    return {
      subject: form.subject,
      requiredElements: form.required
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      avoidElements: form.avoid
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
      useCase: form.useCase,
      format: form.format,
      tone: form.tone,
      strength: form.strength,
    };
  }

  async function onCompose() {
    if (!form.subject.trim()) {
      setError("主題を入力してください");
      return;
    }
    setBusy("compose");
    setError(null);
    setMsg(null);
    setBatchResults(null);
    try {
      const out = await api.compose({ styleId, ...formPayload() });
      setResult(out);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }

  async function onComposeAll() {
    if (!form.subject.trim()) {
      setError("主題を入力してください");
      return;
    }
    setBusy("composeAll");
    setError(null);
    setMsg(null);
    setResult(null);
    try {
      const out = await api.composeBatch({
        ...formPayload(),
        styleIds: [...DEFAULT_RUN_STYLE_IDS],
      });
      setBatchResults(out);
      setMsg(`${out.results.length} スタイル分のプロンプトをプレビューしました`);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }

  async function onCreateRun() {
    if (!form.subject.trim()) {
      setError("主題を入力してください");
      return;
    }
    setBusy("createRun");
    setError(null);
    setMsg(null);
    try {
      const created = await api.createRun(formPayload());
      onRunCreated?.(created.runId);
      setMsg(`run「${created.runId}」を作成し、5スタイル分のプロンプトパックを出力しました`);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }

  async function onExportRun() {
    if (!runId) {
      setError("先に run を作成するか、上部で run を選択してください");
      return;
    }
    setBusy("export");
    setError(null);
    setMsg(null);
    try {
      await api.exportRun(runId);
      setMsg(`run「${runId}」の生成計画と Codex プロンプトを再出力しました`);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }

  const current = styles.find((s) => s.id === styleId);
  const styleGroups = groupStyles(styles);
  const canGenerate = Boolean(styleId) && Boolean(form.subject.trim());

  return (
    <div className="page generate-page">
      <ol className="workflow-steps" aria-label="生成の流れ">
        <li className="done">スタイルを選ぶ</li>
        <li className={form.subject.trim() ? "done" : "current"}>題材を入力</li>
        <li className={result ? "done" : ""}>プロンプトをコピーして生成</li>
        <li>取り込み・評価</li>
      </ol>

      {/* Step 1: Style */}
      <section className="step-section" aria-labelledby="step-style">
        <div className="step-head">
          <span className="step-num">1</span>
          <div>
            <h2 id="step-style">スタイルを選ぶ</h2>
            <p className="hint">
              参考画像から解析した5スタイル。サムネイルをクリックして選択。
            </p>
          </div>
          {current && (
            <span className="step-selection">
              選択中: <strong>{current.labelJa}</strong>
            </span>
          )}
        </div>

        <div className="style-groups">
          {styleGroups.map((group) => (
            <section className="style-group" key={group.family}>
              <div className="style-group-head">
                <strong>{group.family}</strong>
                <small>{group.styles.length} 件</small>
              </div>
              <div className="grid">
                {group.styles.map((s) => (
                  <button
                    type="button"
                    key={s.id}
                    className={styleId === s.id ? "card selected" : "card"}
                    onClick={() => {
                      setStyleId(s.id);
                      setResult(null);
                      setBatchResults(null);
                    }}
                  >
                    <div className="thumb">
                      {(s.previewImage || s.referenceImages[0]) && (
                        <img
                          src={
                            s.previewImage
                              ? projectAssetUrl(s.previewImage)
                              : assetUrl(s.referenceImages[0])
                          }
                          alt=""
                        />
                      )}
                    </div>
                    <div className="meta">
                      <strong>{s.labelJa}</strong>
                      <small>{s.referenceImages.length} 枚の参考</small>
                      {s.styleDifferentiator && (
                        <span>{s.styleDifferentiator}</span>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            </section>
          ))}
        </div>

        {current && current.referenceImages.length > 0 && (
          <details className="refs-panel">
            <summary>
              選択スタイルの参考画像（{current.referenceImages.length}枚）
            </summary>
            <div className="refs">
              {current.referenceImages.slice(0, 8).map((p) => (
                <img key={p} src={assetUrl(p)} alt="" />
              ))}
            </div>
          </details>
        )}
      </section>

      {/* Step 2: Subject */}
      <section className="step-section" aria-labelledby="step-subject">
        <div className="step-head">
          <span className="step-num">2</span>
          <div>
            <h2 id="step-subject">題材と用途を入力</h2>
            <p className="hint">
              描きたい内容を書く。スタイル用語は自動付加されるので入力不要。
            </p>
          </div>
        </div>

        <div className="generate-form-layout">
          <div className="form">
            <label>
              主題 <span className="required-mark">必須</span>
              <textarea
                rows={3}
                value={form.subject}
                onChange={(e) => setForm({ ...form, subject: e.target.value })}
                placeholder="例: 猫が窓辺で本を読んでいる"
              />
            </label>
            <label>
              必須要素（カンマ区切り）
              <input
                value={form.required}
                onChange={(e) => setForm({ ...form, required: e.target.value })}
                placeholder="例: cat, window, book"
              />
            </label>
            <label>
              禁止要素（カンマ区切り）
              <input
                value={form.avoid}
                onChange={(e) => setForm({ ...form, avoid: e.target.value })}
                placeholder="例: text, logo"
              />
            </label>
            <div className="row">
              <label>
                用途
                <select
                  value={form.useCase}
                  onChange={(e) => setForm({ ...form, useCase: e.target.value })}
                >
                  {USE_CASE_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                フォーマット
                <select
                  value={form.format}
                  onChange={(e) => setForm({ ...form, format: e.target.value })}
                >
                  {FORMAT_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                トーン
                <select
                  value={form.tone}
                  onChange={(e) => setForm({ ...form, tone: e.target.value })}
                >
                  {TONE_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label className="strength-control">
              スタイル強度（Strength）
              <div className="strength-row">
                <input
                  type="range"
                  min={1}
                  max={100}
                  step={1}
                  value={form.strength ?? 70}
                  onChange={(e) =>
                    setForm({ ...form, strength: Number(e.target.value) })
                  }
                />
                <output>{form.strength ?? 70}</output>
              </div>
              <small className="hint">
                低=スタイル語彙を弱く / 高=参照スタイルを強く適用（70 が標準）
              </small>
            </label>
            <div className="form-actions">
              <button
                type="button"
                className="btn-primary btn-large"
                onClick={onCompose}
                disabled={!!busy || !canGenerate}
              >
                {busy === "compose" ? "生成中…" : "選択スタイルをプレビュー"}
              </button>
              <button
                type="button"
                className="btn-secondary"
                onClick={onComposeAll}
                disabled={!!busy || !canGenerate}
              >
                {busy === "composeAll" ? "生成中…" : "5スタイル一括プレビュー"}
              </button>
              <button
                type="button"
                className="btn-secondary"
                onClick={onCreateRun}
                disabled={!!busy || !canGenerate}
              >
                {busy === "createRun" ? "作成中…" : "5スタイル run を作成"}
              </button>
              {!form.subject.trim() && (
                <span className="hint inline-hint">主題を入力すると有効になります</span>
              )}
            </div>
            {runId && (
              <div className="export-bar">
                <span className="hint">
                  選択中 run: <code>{runId}</code>
                </span>
                <button
                  type="button"
                  onClick={onExportRun}
                  disabled={!!busy}
                >
                  {busy === "export" ? "出力中…" : "生成計画・Codexパック再出力"}
                </button>
                <a
                  className="link-button"
                  href={`/prompt_runs/${runId}/codex_image_prompts.md`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Codex パック
                </a>
              </div>
            )}
            {msg && <div className="ok-banner">{msg}</div>}
            {error && <div className="error">{error}</div>}
          </div>
        </div>
      </section>

      {batchResults && batchResults.results.length > 0 && (
        <section className="step-section" aria-labelledby="step-batch-preview">
          <div className="step-head">
            <span className="step-num">3</span>
            <div>
              <h2 id="step-batch-preview">5スタイル一括プレビュー</h2>
              <p className="hint">
                同じ題材・強度で5スタイル分のポジティブプロンプト。run 作成前の比較用。
              </p>
            </div>
          </div>
          <div className="batch-preview-grid">
            {batchResults.results.map((row) => {
              const style = styles.find((s) => s.id === row.styleId);
              return (
                <article className="batch-preview-card" key={row.styleId}>
                  <div className="batch-preview-head">
                    <strong>{style?.labelJa ?? row.styleId}</strong>
                    <CopyButton text={row.positive} label="コピー" />
                  </div>
                  {style?.previewImage && (
                    <img
                      className="batch-preview-thumb"
                      src={projectAssetUrl(style.previewImage)}
                      alt=""
                    />
                  )}
                  <pre>{row.positive}</pre>
                </article>
              );
            })}
          </div>
        </section>
      )}

      {/* Step 3/4: Single style output */}
      {result && (
        <section className="step-section" aria-labelledby="step-prompts">
          <div className="step-head">
            <span className="step-num">{batchResults ? "4" : "3"}</span>
            <div>
              <h2 id="step-prompts">プロンプトをコピーして画像生成</h2>
              <p className="hint">
                Codex / ChatGPT の画像生成に貼り付け。バリアント A/B/C は用途に応じて使い分け。
              </p>
            </div>
          </div>

          <div className="prompt-output">
            <div className="prompt-block">
              <div className="prompt-block-head">
                <strong>ポジティブ</strong>
                <CopyButton text={result.positive} label="ポジティブをコピー" />
              </div>
              <pre>{result.positive}</pre>
            </div>
            <div className="prompt-block">
              <div className="prompt-block-head">
                <strong>ネガティブ</strong>
                <CopyButton text={result.negative} label="ネガティブをコピー" />
              </div>
              <pre>{result.negative}</pre>
            </div>
          </div>

          <h3 className="subsection-title">バリアント A / B / C</h3>
          <div className="variants">
            {result.variants.map((v) => (
              <article className="variant-card" key={v.label}>
                <div className="prompt-block-head">
                  <div>
                    <strong>{v.label}</strong>
                    <span className="variant-focus">{v.focus}</span>
                  </div>
                  <CopyButton
                    text={v.positive}
                    label={`${v.label} をコピー`}
                  />
                </div>
                <pre>{v.positive}</pre>
              </article>
            ))}
          </div>

          <aside className="next-steps">
            <strong>画像を保存したら</strong>
            <ol>
              <li>Codex / ChatGPT で画像を生成し、ローカルフォルダに保存</li>
              <li>
                {onGoImport ? (
                  <>
                    <button type="button" className="linkish" onClick={onGoImport}>
                      取り込み
                    </button>
                    タブでパスを指定して取り込み
                  </>
                ) : (
                  "取り込みタブでパスを指定して取り込み"
                )}
              </li>
              <li>レビュー・90点ゲートでスタイル再現を確認</li>
            </ol>
            <div className="next-steps-links">
              {runId && (
                <a
                  className="link-button"
                  href={`/reports/${runId}_project_hub.html`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Project Hub を開く
                </a>
              )}
            </div>
          </aside>
        </section>
      )}
    </div>
  );
}
