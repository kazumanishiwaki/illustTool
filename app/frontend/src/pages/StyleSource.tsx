import { useEffect, useState } from "react";
import {
  api,
  assetUrl,
  projectAssetUrl,
  type StyleDetail,
  type StyleSummary,
} from "../api";

type Editable = {
  labelJa: string;
  promptFragments: string[];
  promptFragmentsJa: string[];
  negativeFragments: string[];
  negativeFragmentsJa: string[];
  visualFingerprint: Record<string, string>;
  visualFingerprintJa: Record<string, string>;
  improvementRules: Record<string, string>;
  improvementRulesJa: Record<string, string>;
};

const FP_KEYS = ["line", "shape", "color", "texture", "composition", "person"];
const FP_LABELS: Record<string, string> = {
  line: "線",
  shape: "形",
  color: "色",
  texture: "質感",
  composition: "構図",
  person: "人物",
};

function toEditable(d: StyleDetail): Editable {
  return {
    labelJa: d.labelJa,
    promptFragments: [...d.promptFragments],
    promptFragmentsJa: [...d.promptFragmentsJa],
    negativeFragments: [...d.negativeFragments],
    negativeFragmentsJa: [...d.negativeFragmentsJa],
    visualFingerprint: { ...d.visualFingerprint },
    visualFingerprintJa: { ...d.visualFingerprintJa },
    improvementRules: { ...d.improvementRules },
    improvementRulesJa: { ...d.improvementRulesJa },
  };
}

function linesToArray(text: string): string[] {
  return text
    .split("\n")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

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

function FragmentBlock({
  title,
  hint,
  enText,
  jaText,
  onChangeEn,
  onChangeJa,
}: {
  title: string;
  hint: string;
  enText: string;
  jaText: string;
  onChangeEn: (v: string) => void;
  onChangeJa: (v: string) => void;
}) {
  return (
    <div className="block">
      <div className="block-head">
        <strong>{title}</strong>
        <small className="hint">{hint}</small>
      </div>
      <textarea
        rows={Math.max(4, enText.split("\n").length + 1)}
        value={enText}
        onChange={(e) => onChangeEn(e.target.value)}
        placeholder="1行に1要素（英語推奨）"
      />
      <label className="ja-label">日本語訳（任意・1行ずつ対応）</label>
      <textarea
        className="ja"
        rows={Math.max(3, jaText.split("\n").length + 1)}
        value={jaText}
        onChange={(e) => onChangeJa(e.target.value)}
        placeholder="1行に1要素の日本語訳"
      />
    </div>
  );
}

function DictBlock({
  title,
  fixedKeys,
  keyLabels,
  enData,
  jaData,
  onChangeEn,
  onChangeJa,
  allowAddKeys = false,
}: {
  title: string;
  fixedKeys?: string[];
  keyLabels?: Record<string, string>;
  enData: Record<string, string>;
  jaData: Record<string, string>;
  onChangeEn: (next: Record<string, string>) => void;
  onChangeJa: (next: Record<string, string>) => void;
  allowAddKeys?: boolean;
}) {
  const keys = fixedKeys ?? Array.from(new Set([...Object.keys(enData), ...Object.keys(jaData)]));
  const [newKey, setNewKey] = useState("");
  return (
    <div className="block">
      <div className="block-head">
        <strong>{title}</strong>
        {allowAddKeys && (
          <div className="add-key">
            <input
              value={newKey}
              placeholder="新しいキー"
              onChange={(e) => setNewKey(e.target.value)}
            />
            <button
              disabled={!newKey.trim() || newKey in enData}
              onClick={() => {
                onChangeEn({ ...enData, [newKey.trim()]: "" });
                setNewKey("");
              }}
            >
              + 追加
            </button>
          </div>
        )}
      </div>
      {keys.map((k) => (
        <div className="dict-row" key={k}>
          <div className="dict-key">
            <code>{k}</code>
            {keyLabels?.[k] && <small>{keyLabels[k]}</small>}
          </div>
          <div className="dict-vals">
            <textarea
              rows={2}
              value={enData[k] ?? ""}
              onChange={(e) => onChangeEn({ ...enData, [k]: e.target.value })}
              placeholder="英語"
            />
            <textarea
              className="ja"
              rows={2}
              value={jaData[k] ?? ""}
              onChange={(e) => onChangeJa({ ...jaData, [k]: e.target.value })}
              placeholder="日本語訳（任意）"
            />
          </div>
          {allowAddKeys && (
            <button
              className="ghost"
              title="削除"
              onClick={() => {
                const e1 = { ...enData };
                const e2 = { ...jaData };
                delete e1[k];
                delete e2[k];
                onChangeEn(e1);
                onChangeJa(e2);
              }}
            >
              ×
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

export default function StyleSource({ styles }: { styles: StyleSummary[] }) {
  const [styleId, setStyleId] = useState<string>("");
  const [detail, setDetail] = useState<StyleDetail | null>(null);
  const [draft, setDraft] = useState<Editable | null>(null);
  // Local text buffer for textareas so empty lines don't disappear while typing
  const [pfText, setPfText] = useState("");
  const [pfJaText, setPfJaText] = useState("");
  const [nfText, setNfText] = useState("");
  const [nfJaText, setNfJaText] = useState("");

  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!styleId && styles.length > 0) setStyleId(styles[0].id);
  }, [styles, styleId]);

  useEffect(() => {
    if (!styleId) return;
    setError(null);
    setMsg(null);
    api
      .style(styleId)
      .then((d) => {
        setDetail(d);
        const e = toEditable(d);
        setDraft(e);
        setPfText(e.promptFragments.join("\n"));
        setPfJaText(e.promptFragmentsJa.join("\n"));
        setNfText(e.negativeFragments.join("\n"));
        setNfJaText(e.negativeFragmentsJa.join("\n"));
      })
      .catch((e) => setError(String(e)));
  }, [styleId]);

  // Sync text buffers → draft arrays on every keystroke
  useEffect(() => {
    if (!draft) return;
    setDraft({
      ...draft,
      promptFragments: linesToArray(pfText),
      promptFragmentsJa: linesToArray(pfJaText),
      negativeFragments: linesToArray(nfText),
      negativeFragmentsJa: linesToArray(nfJaText),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pfText, pfJaText, nfText, nfJaText]);

  const dirty =
    !!detail &&
    !!draft &&
    JSON.stringify(draft) !== JSON.stringify(toEditable(detail));
  const styleGroups = groupStyles(styles);

  async function save() {
    if (!draft || !styleId) return;
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      const updated = await api.updateStyle(styleId, draft);
      setDetail(updated);
      const e = toEditable(updated);
      setDraft(e);
      setPfText(e.promptFragments.join("\n"));
      setPfJaText(e.promptFragmentsJa.join("\n"));
      setNfText(e.negativeFragments.join("\n"));
      setNfJaText(e.negativeFragmentsJa.join("\n"));
      setMsg("保存しました（バックアップは data/_backups/ に保存）");
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    if (!detail) return;
    const e = toEditable(detail);
    setDraft(e);
    setPfText(e.promptFragments.join("\n"));
    setPfJaText(e.promptFragmentsJa.join("\n"));
    setNfText(e.negativeFragments.join("\n"));
    setNfJaText(e.negativeFragmentsJa.join("\n"));
  }

  return (
    <div className="page">
      <h2>スタイル設定</h2>
      <p className="hint">
        5つのスタイルを解析したプロンプト断片。値を編集して「保存」を押すと
        <code>data/style_fingerprints.json</code>{" "}
        に書き戻されます（既存ファイルは
        <code>data/_backups/</code> に自動退避）。
      </p>

      <div className="ss-groups">
        {styleGroups.map((group) => (
          <section className="ss-group" key={group.family}>
            <div className="style-group-head">
              <strong>{group.family}</strong>
              <small>{group.styles.length} 件</small>
            </div>
            <div className="ss-tabs">
              {group.styles.map((s) => (
                <button
                  key={s.id}
                  className={styleId === s.id ? "active" : ""}
                  onClick={() => setStyleId(s.id)}
                >
                  {s.labelJa}
                  <small>{s.id}</small>
                </button>
              ))}
            </div>
          </section>
        ))}
      </div>

      {error && <div className="error global">{error}</div>}
      {msg && <div className="ok-banner">{msg}</div>}

      {detail && draft && (
        <div className="ss-layout">
          <aside className="ss-meta">
            <h3>{detail.labelJa}</h3>
            {detail.styleFamilyJa && (
              <span className="family-pill">{detail.styleFamilyJa}</span>
            )}
            <small>
              {detail.id} · 参照グロブ: <code>{detail.referenceGlob}</code>
            </small>
            {detail.styleDifferentiator && (
              <p className="differentiator">{detail.styleDifferentiator}</p>
            )}
            <div className="refs small">
              {detail.previewImage && (
                <img src={projectAssetUrl(detail.previewImage)} alt="" />
              )}
              {detail.referenceImages.slice(0, 12).map((p) => (
                <img key={p} src={assetUrl(p)} alt="" />
              ))}
            </div>
            <details>
              <summary>採点ウェイト（読み取り専用）</summary>
              <pre>{JSON.stringify(detail.styleScoringWeights, null, 2)}</pre>
            </details>
            <div className="ss-actions">
              <button onClick={save} disabled={!dirty || busy}>
                {busy ? "..." : dirty ? "保存" : "変更なし"}
              </button>
              <button
                onClick={reset}
                disabled={!dirty || busy}
                className="ghost"
              >
                リセット
              </button>
            </div>
          </aside>

          <main className="ss-form">
            <label className="row1">
              <strong>表示名</strong>
              <input
                value={draft.labelJa}
                onChange={(e) =>
                  setDraft({ ...draft, labelJa: e.target.value })
                }
              />
            </label>

            <FragmentBlock
              title="プロンプト断片（ポジティブ）"
              hint="1行に1要素。Compose 時に主題のあとに連結される"
              enText={pfText}
              jaText={pfJaText}
              onChangeEn={setPfText}
              onChangeJa={setPfJaText}
            />

            <FragmentBlock
              title="プロンプト断片（ネガティブ）"
              hint="1行に1要素。Compose 時に negative 末尾に連結される"
              enText={nfText}
              jaText={nfJaText}
              onChangeEn={setNfText}
              onChangeJa={setNfJaText}
            />

            <DictBlock
              title="ビジュアル特徴"
              fixedKeys={FP_KEYS.filter(
                (k) =>
                  k in draft.visualFingerprint ||
                  k in draft.visualFingerprintJa ||
                  k in detail.visualFingerprint,
              )}
              keyLabels={FP_LABELS}
              enData={draft.visualFingerprint}
              jaData={draft.visualFingerprintJa}
              onChangeEn={(next) =>
                setDraft({ ...draft, visualFingerprint: next })
              }
              onChangeJa={(next) =>
                setDraft({ ...draft, visualFingerprintJa: next })
              }
            />

            <DictBlock
              title="改善ルール"
              allowAddKeys
              enData={draft.improvementRules}
              jaData={draft.improvementRulesJa}
              onChangeEn={(next) =>
                setDraft({ ...draft, improvementRules: next })
              }
              onChangeJa={(next) =>
                setDraft({ ...draft, improvementRulesJa: next })
              }
            />
          </main>
        </div>
      )}
    </div>
  );
}
