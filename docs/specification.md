# Illustration Tool Specification

## Objective

任意のイラスト用に、ユーザーが入力した題材（Subject）と必須／禁止要素を、
5つの解析済みリファレンススタイルに沿って **生成プロンプトに変換**し、
**生成済み画像をローカルで取り込み・採点・改善ループ**できる状態にする。

固定テーマ "コーヒーを持って散歩している人" は **ループ機構の検証フィクスチャ**で
あり、製品仕様ではない（`coffee_walk_v*` runs と `style_selftest` がそれにあたる）。

Supporting product and market documents:

- `docs/market_research.md`
- `docs/product_requirements.md`
- `docs/evaluation_loop.md`

ローカル基盤の責務:

- 37枚の参考画像をスタイル別に解析する
- スタイル特徴を、ユーザー入力（Subject／Required／Avoid／UseCase／Format／Tone）と
  合成して、ポジティブ／ネガティブプロンプトに変換する
- バリアント A/B/C 別の生成プランを作る
- ユーザーが Codex/ChatGPT サブスクで生成した画像を取り込み、自動・手動で評価する
- 弱点を踏まえた次ラウンドプロンプトを作る

生成AIは外部ツール扱い。本ツールは API キーを要求しない。

## Source References

参考画像はワークスペース直下の37枚で、5スタイル群を構成する。

| Style ID | Style | Count |
|---|---|---:|
| `naive_wobbly` | ナイーブ／ワブリー手描き | 7 |
| `grain_flat` | グレイン入りフラット | 6 |
| `print_relief` | 印刷・版画（リソ／リノカット／木版） | 10 |
| `editorial_outline` | エディトリアル・アウトライン | 8 |
| `flat_vector` | フラットベクター（コーポレート） | 6 |

Authoritative analysis outputs:

- `reports/reference_manifest.json`
- `reports/reference_analysis.md`
- `reports/reference_baselines.json`

## Input Model

各 run は次の入力を受け取る:

| Field | 役割 | 例 |
|---|---|---|
| Subject | 主題 | 猫が窓辺で本を読んでいる |
| Required elements | 必須要素 | cat, window, book |
| Avoid elements | 禁止要素 | text, logo |
| Use case | 用途 | SaaS LP, article hero |
| Format | フォーマット制約 | square, web hero, transparent background |
| Tone | 感情方向 | warm, morning |
| Style | スタイル（5つから視覚選択） | `naive_wobbly` 等 |

Subject は **可変** で、run ごとに任意に変えられる。
Style は5スタイルの fingerprint（`data/style_fingerprints.json`）と紐づく。

## Data Model

正本データ:

```text
data/style_fingerprints.json
```

各スタイルは以下を持つ:

- `id`
- `labelJa`
- `referenceGlob`
- `visualFingerprint`
- `styleScoringWeights`
- `promptFragments`
- `negativeFragments`
- `improvementRules`

このファイルから、プロンプトパック、生成プラン、レポート、次ラウンドプロンプトが
派生する。

## GUI (FastAPI + Vite/React)

汎用運用のメイン UI は `app/` 配下の Web アプリ:

```bash
# backend (port 8765)
app/.venv/bin/uvicorn app.backend.main:app --host 127.0.0.1 --port 8765

# frontend (port 5173)
cd app/frontend && npm run dev
```

2タブで構成:

1. **Prompt Builder** — Subject／要素／用途／スタイルを入力 → ポジティブ／ネガティブと
   バリアント A/B/C をプレビュー＋コピー。生成と評価は **Codex/ChatGPT 上で行う**
2. **Style Source** — 5スタイルそれぞれの分析済みプロンプトソース
   （`labelJa`, `promptFragments`, `negativeFragments`, `visualFingerprint`,
   `improvementRules`）の表示・編集。保存時は `data/style_fingerprints.json` を
   上書きし、既存ファイルは `data/_backups/` に自動退避する

GUI は `data/style_fingerprints.json` を正本として読み書きする。CLI ロジックは
`scripts/style_eval.py` に残り、GUI からは参照のみ。生成画像の取り込み・採点・
ゲートは GUI 側には設けず、Codex/ChatGPT 上のワークフローで完結させる。

## CLI (legacy / backbone)

`scripts/style_eval.py` には42個前後のサブフラグがあり、GUI もここを叩く。
代表コマンド:

```bash
python3 scripts/style_eval.py --analyze-references
python3 scripts/style_eval.py --baselines
python3 scripts/style_eval.py --generation-plan {run_id} --variants 3
python3 scripts/style_eval.py --codex-image-pack {run_id}
python3 scripts/style_eval.py --intake-audit {run_id} [SOURCE_DIR]
python3 scripts/style_eval.py --import-codex-images {run_id} SOURCE_DIR
python3 scripts/style_eval.py --refresh-run {run_id}
python3 scripts/style_eval.py --set-review {run_id} {style_id} {image} --scores ...
python3 scripts/style_eval.py --gate-report {run_id}
python3 scripts/style_eval.py --prepare-next-round {source_run} {target_run}
```

## Workflow

1. 参考解析（一度だけ）
2. **Prompt Builder で Subject を入力、Style を選択 → プロンプト確定**
3. 生成プラン作成（5×3=15）
4. Codex/ChatGPT サブスクで15枚生成（外部）
5. Dashboard から取り込み（インポート）
6. Review で6軸採点（CSV往復なし、直接保存）
7. Gate で構築検証スコアを確認
8. 必要なら次ラウンドプロンプトを準備

## Scoring (reference rubric)

スコアは **構築期の自己検証用**として参考設定。汎用運用では運用者の判断材料。

Total 100:

- Automatic 35: saturation, brightness, near-white, dark, edge density（同スタイル群の最近接参照と比較）
- Manual 65:

| Axis | Max |
|---|---:|
| `subjectAdherence` | 15 |
| `lineShapeLanguage` | 15 |
| `textureMediumVisual` | 15 |
| `compositionIntent` | 8 |
| `stylePurity` | 10 |
| `productionUsefulness` | 2 |

`subjectAdherence` は Subject が run ごとに変わるため、自動化せず人間レビュアーが
判定する。

## Pass Criteria (initial build only)

下記は **ツール構築完了の自己検証** として使う。汎用運用での合否ではない。

スタイル合格条件:

- `finalScore >= 90`
- target style ranks first in automatic classification
- manual review present
- `subjectAdherence >= 12`
- `textureMediumVisual >= 12`
- `stylePurity >= 8`
- no hard cap reduces the score below 90

すべて5スタイルが通った時点で **ツール基盤としての完成** とみなす。
以後の通常運用では gate は無視してよい。

```bash
python3 scripts/style_eval.py --gate coffee_walk_v1
```

## Improvement Loop

run が gate を通らないときに次ラウンドプロンプトを作る:

```bash
python3 scripts/style_eval.py --prepare-next-round coffee_walk_v1 coffee_walk_v2 --variants 3
```

次ラウンドは以下を反映する:

- 自動指標の弱点
- target-style ranking の失敗
- 手動採点の弱軸
- レビュアーメモ
- スタイル固有の `improvementRules`

## Verification Commands

```bash
python3 -m py_compile scripts/style_eval.py
python3 -m json.tool data/style_fingerprints.json >/tmp/style_fingerprints.ok
python3 scripts/style_eval.py --analyze-references
python3 scripts/style_eval.py --baselines
python3 scripts/style_eval.py --generation-plan coffee_walk_v1 --variants 3
python3 scripts/style_eval.py --codex-image-pack coffee_walk_v1
python3 scripts/style_eval.py --refresh-run coffee_walk_v1
python3 scripts/style_eval.py --gate-report coffee_walk_v1
```

GUI 側:

```bash
app/.venv/bin/python -c "from app.backend import main; print('ok')"
cd app/frontend && npm run build
```

## Completion Evidence (initial build)

ツール構築完了の判定材料（汎用運用の達成度ではない）:

- `reports/reference_manifest.json` に37枚が含まれる
- `coffee_walk_v1` または後続の検証 run で5スタイル全てに生成画像がある
- 各スタイルに `finalScore >= 90` のレビュー済み画像が1枚以上ある
- `python3 scripts/style_eval.py --gate {run_id}` が exit 0

`style_selftest` は採点・レビュー保存・ゲートロジックの配管テストであり、
プロンプト品質を保証するものではない。
