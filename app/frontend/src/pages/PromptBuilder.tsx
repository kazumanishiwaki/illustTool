import { useEffect, useState } from "react";
import {
  api,
  assetUrl,
  projectAssetUrl,
  type ComposeResult,
  type StyleSummary,
} from "../api";

type Form = {
  subject: string;
  required: string;
  avoid: string;
  useCase: string;
  format: string;
  tone: string;
};

const EMPTY_FORM: Form = {
  subject: "",
  required: "",
  avoid: "",
  useCase: "",
  format: "",
  tone: "",
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

export default function PromptBuilder({
  styles,
}: {
  styles: StyleSummary[];
}) {
  const [styleId, setStyleId] = useState<string>("");
  const [form, setForm] = useState<Form>(EMPTY_FORM);
  const [result, setResult] = useState<ComposeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!styleId && styles.length > 0) setStyleId(styles[0].id);
  }, [styles, styleId]);

  async function onCompose() {
    setBusy(true);
    setError(null);
    try {
      const out = await api.compose({
        styleId,
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
      });
      setResult(out);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // ignore
    }
  }

  const current = styles.find((s) => s.id === styleId);
  const styleGroups = groupStyles(styles);

  return (
    <div className="page">
      <h2>プロンプト作成</h2>
      <p className="hint">
        主題と必須／禁止要素を入力して「生成」を押すと、選んだスタイルの断片が
        自動付加されたポジティブ／ネガティブのプロンプトが出力されます。
      </p>

      <div className="two-col">
        <div className="form">
          <label>
            主題
            <textarea
              rows={2}
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
          <button onClick={onCompose} disabled={busy || !styleId}>
            {busy ? "..." : "生成"}
          </button>
          {error && <div className="error">{error}</div>}
        </div>

        <div className="style-pick">
          <h3>スタイル</h3>
          <div className="style-groups">
            {styleGroups.map((group) => (
              <section className="style-group" key={group.family}>
                <div className="style-group-head">
                  <strong>{group.family}</strong>
                  <small>{group.styles.length} 件</small>
                </div>
                <div className="grid small">
                  {group.styles.map((s) => (
                    <button
                      key={s.id}
                      className={styleId === s.id ? "card selected" : "card"}
                      onClick={() => setStyleId(s.id)}
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
                        <small>{s.referenceImages.length} 枚</small>
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
            <details>
              <summary>参考画像 ({current.referenceImages.length})</summary>
              <div className="refs small">
                {current.referenceImages.slice(0, 6).map((p) => (
                  <img key={p} src={assetUrl(p)} alt="" />
                ))}
              </div>
            </details>
          )}
        </div>
      </div>

      {result && (
        <div className="result">
          <h3>プロンプト</h3>
          <div className="prompt-row">
            <strong>ポジティブ</strong>
            <button onClick={() => copy(result.positive)}>コピー</button>
          </div>
          <pre>{result.positive}</pre>
          <div className="prompt-row">
            <strong>ネガティブ</strong>
            <button onClick={() => copy(result.negative)}>コピー</button>
          </div>
          <pre>{result.negative}</pre>
          <h3>バリエーション</h3>
          <div className="variants">
            {result.variants.map((v) => (
              <div className="variant" key={v.label}>
                <div className="prompt-row">
                  <strong>{v.label}: {v.focus}</strong>
                  <button onClick={() => copy(v.positive)}>
                    ポジティブをコピー
                  </button>
                </div>
                <pre>{v.positive}</pre>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
