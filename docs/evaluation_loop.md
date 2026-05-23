# 90点達成までの評価・改善ループ

## 目的

37枚の参考画像から抽出したスタイル特徴を、別テーマ「コーヒーを持って散歩している人」に移植できているかを評価する。合格点は100点満点中90点。

## 固定テーマ

日本語:

```text
コーヒーを持って散歩している人
```

英語ベース:

```text
A single person walking outside while holding a takeaway coffee cup, full body visible, clear walking pose, one hand holding a lidded paper coffee cup, simple outdoor street setting, relaxed morning mood, casual outfit, no extra main characters
```

## 評価配点

| 軸 | 点 | 内容 |
|---|---:|---|
| Subject adherence | 15 | 人、歩行、テイクアウトコーヒー、屋外、リラックス感が成立しているか |
| Line and shape | 20 | 元スタイルの線の太さ、揺れ、幾何性、輪郭の扱いが再現されているか |
| Color palette | 15 | 色数、彩度、背景色、アクセント色が近いか |
| Texture technique | 20 | 紙感、グレイン、版ズレ、線画の清潔さ、ベクター感などが出ているか |
| Composition density | 10 | 余白、密度、主役配置、ポスター性などが近いか |
| Style purity | 15 | 写実化、3D化、別ジャンル混入がないか |
| Production usefulness | 5 | LP、記事、SNS、資料などに使える完成度があるか |

## 自動評価と人間評価

自動評価は35点相当の補助指標として使う。

- 彩度
- 明度
- 白背景/余白率
- 黒ベタ率
- 線量/エッジ密度
- 代表色パレット

残り65点は目視評価で付ける。最終判定では、主観だけで90点を出さないため、自動指標の大きなズレがある場合は必ずプロンプトを修正する。

## ループ手順

1. 参考画像の基準値を作る。

```bash
python3 scripts/style_eval.py --baselines
```

画像別の解析マニフェストと読み物用レポートも作る。

```bash
python3 scripts/style_eval.py --analyze-references
```

出力:

```text
reports/reference_manifest.json
reports/reference_analysis.md
```

`reference_manifest.json` は37枚すべてのスタイルID、ファイル名、画像特徴量、プロンプト断片を持つ。`reference_analysis.md` はスタイル別の視覚指紋、指標範囲、画像別特徴を確認するためのレポート。

2. 固定テーマの初期プロンプトを作る。

```bash
python3 scripts/style_eval.py --prompts
```

フォーム入力とサムネイル選択で単発プロンプトを組み立てる場合は、プロンプトビルダーを使う。

```bash
python3 scripts/style_eval.py --prompt-builder
```

出力:

```text
reports/prompt_builder.html
```

3. `prompt_runs/coffee_walk_v1/{style_id}.md` の Positive Prompt / Negative Prompt で画像を生成する。

生成前にジョブシートを作る。標準は各スタイル3候補。

```bash
python3 scripts/style_eval.py --generation-plan coffee_walk_v1 --variants 3
```

3候補は同一プロンプトの単純な再生成ではなく、以下の役割を持つ。

- A: 主題の明確さ。歩行ポーズ、全身、屋外、コーヒーカップを強める
- B: 構図・余白・色。参照画像の密度、余白、色傾向を強める
- C: 技法・質感。線、形、印刷感、グレイン、ベクター感などを強める

出力:

```text
prompt_runs/coffee_walk_v1/generation_plan.json
prompt_runs/coffee_walk_v1/generation_plan.md
prompt_runs/coffee_walk_v1/generation_jobs.csv
```

`generation_jobs.csv` は外部生成ツールに渡すための1画像1行のCSV。`positivePrompt`、`negativePrompt`、`outputPath` を持つ。

4. 外部画像生成コマンドで、planに記載された15出力を保存する。

Codex上のサブスク生成を使う場合は、まずCodex用プロンプトパックを作る。

```bash
python3 scripts/style_eval.py --codex-image-pack coffee_walk_v1
python3 scripts/style_eval.py --project-hub coffee_walk_v1
```

出力:

```text
prompt_runs/coffee_walk_v1/codex_image_prompts.md
prompt_runs/coffee_walk_v1/codex_prompts/{01..15}_*.txt
prompt_runs/coffee_walk_v1/codex_prompts/manifest.csv
reports/coffee_walk_v1_project_hub.html
```

Markdownまたは `codex_prompts/*.txt` の15個のプロンプトをCodex/ChatGPTの画像生成に1つずつ渡す。生成画像は、各ブロックに書かれた名前で同じフォルダに保存する。

```text
naive_wobbly_round_01_a.png
naive_wobbly_round_01_b.png
...
flat_vector_round_01_c.png
```

ブラウザ側で保存名が変わる場合は、`codex_prompts/manifest.csv` の連番に合わせた `01.png`、`02.webp` のような名前でも取り込める。`01_naive_wobbly_round_01_a.png` のようなプロンプトファイルstem形式も受け付ける。各ジョブで受け付けるstemは、manifestの `acceptedSourceStems` にも出力する。

保存後、評価用の `generated/` 配下に取り込む。

```bash
python3 scripts/style_eval.py --loop-status coffee_walk_v1
python3 scripts/style_eval.py --operator-checklist coffee_walk_v1
python3 scripts/style_eval.py --codex-queue coffee_walk_v1
python3 scripts/style_eval.py --dashboard coffee_walk_v1
python3 scripts/style_eval.py --intake-audit coffee_walk_v1 /path/to/saved/codex/images
python3 scripts/style_eval.py --import-codex-images coffee_walk_v1 /path/to/saved/codex/images
python3 scripts/style_eval.py --sync-run coffee_walk_v1 /path/to/saved/codex/images
python3 scripts/style_eval.py --refresh-run coffee_walk_v1
```

`--loop-status` は、現在が `generate`、`fixImportedImages`、`review`、`iterate`、`complete` のどこかを返す。迷ったらこのコマンドを見て、返された `commands` を上から実行する。
`--operator-checklist` は、現在のブロッカー、次コマンド、生成チェック、レビュー確認、完了監査、主要ファイルを1つのMarkdownにまとめる。
`--sync-run` は取り込み前監査、取り込み、成果物再生成、ループ状態確認をまとめて実行する。保存フォルダを指定しない場合は、現在の評価用パスを監査して成果物を再生成する。

`--intake-audit` は取り込み前に、15個の保存名、画像として読めるか、同一画像を複数保存していないか、PNG以外から変換されるかを確認する。`--import-codex-images` は `.png`, `.webp`, `.jpg`, `.jpeg` を受け付ける。Codexの保存形式がPNG以外でも、評価用の予定パスにはPNGとして保存する。

取り込み後の評価パスを確認する場合:

```bash
python3 scripts/style_eval.py --intake-audit coffee_walk_v1
```

生成・保存・レビュー進行は静的HTMLでも確認できる。

```text
reports/coffee_walk_v1_dashboard.html
```

`--refresh-run` は、取り込み後または採点後に、評価JSON、レビューHTML、レビューシート、目視比較シート、レビューガイド、ダッシュボードをまとめて更新する。

標準の実行スクリプトを書き出す。

```bash
python3 scripts/style_eval.py --export-generator-shell coffee_walk_v1
```

`ILLUSTRATION_GENERATOR_CMD` に任意の画像生成コマンドを指定して実行する。コマンド内では `run_id`、`style_id`、`variant`、`positive`、`negative`、`output` を使える。

```bash
ILLUSTRATION_GENERATOR_CMD='python3 tools/generate.py --prompt "$positive" --negative "$negative" --out "$output"' \
  prompt_runs/coffee_walk_v1/run_generation_jobs.sh
```

このコマンドは例。実際の生成器はローカルCLI、APIラッパー、社内ツールなどに差し替える。重要なのは、各ジョブが `$output` に非空の画像を書き出すこと。

CSVバッチに対応した外部ツールなら、以下を直接読ませてもよい。

```text
prompt_runs/coffee_walk_v1/generation_jobs.csv
```

5. 生成画像をジョブシートの保存先に置く。

```text
generated/coffee_walk_v1/{style_id}/round_01_a.png
generated/coffee_walk_v1/{style_id}/round_01_b.png
generated/coffee_walk_v1/{style_id}/round_01_c.png
```

不足画像の確認:

```bash
python3 scripts/style_eval.py --status coffee_walk_v1
python3 scripts/style_eval.py --check-generation-plan coffee_walk_v1
```

15枚すべて揃っている場合のみ終了コード0。足りない場合は不足パスを表示して終了コード1。

6. 自動評価を実行する。

```bash
python3 scripts/style_eval.py --style naive_wobbly --generated generated/coffee_walk_v1/naive_wobbly/round_01_a.png
```

7. 全スタイル照合で、狙ったスタイルが1位になるか確認する。

```bash
python3 scripts/style_eval.py --classify generated/coffee_walk_v1/naive_wobbly/round_01_a.png
```

8. 全体比較レポートを作る。

```bash
python3 scripts/style_eval.py --report coffee_walk_v1
```

出力:

```text
reports/coffee_walk_v1_evaluation.json
reports/coffee_walk_v1_review.html
```

9. 参照画像と生成候補を並べた目視比較シートを作る。

```bash
python3 scripts/style_eval.py --visual-review coffee_walk_v1
```

出力:

```text
reports/coffee_walk_v1_visual_review/index.md
reports/coffee_walk_v1_visual_review/{style_id}.jpg
```

実生成前は未生成枠がプレースホルダーで表示される。生成後に再実行すると、同じシート上で参考画像群と3候補を見比べられる。

10. `reports/coffee_walk_v1_evaluation.json` の `manualReview.axes` を目視評価で埋める。

スタイル別の採点ガイドを作る。

```bash
python3 scripts/style_eval.py --review-guide coffee_walk_v1
```

出力:

```text
reports/coffee_walk_v1_review_guide.md
```

このガイドは、各スタイルの `visualFingerprint`、`negativeFragments`、`improvementRules` を採点軸に翻訳する。点数を入れる前に、減点理由と次ラウンドで強める語をここで確認する。

レビュー対象とコマンドテンプレートはレビューシートから確認する。

```bash
python3 scripts/style_eval.py --review-sheet coffee_walk_v1
```

出力:

```text
reports/coffee_walk_v1_review_sheet.csv
reports/coffee_walk_v1_review_sheet.md
```

15枚をまとめて採点する場合は、手動採点CSVを使う。

```bash
python3 scripts/style_eval.py --manual-review-template coffee_walk_v1
```

出力:

```text
reports/coffee_walk_v1_manual_review_template.csv
```

CSVの6軸スコア、`notes`、必要なら `hardCap` / `override` を埋めて反映する。

```bash
python3 scripts/style_eval.py --review-priorities coffee_walk_v1
python3 scripts/style_eval.py --validate-review-csv coffee_walk_v1 reports/coffee_walk_v1_manual_review_template.csv
python3 scripts/style_eval.py --apply-review-csv coffee_walk_v1 reports/coffee_walk_v1_manual_review_template.csv
python3 scripts/style_eval.py --refresh-run coffee_walk_v1
```

`--review-priorities` は、自動スコア、対象スタイル順位、未レビュー状態を使って、各スタイルで先に目視採点すべき候補を並べる。生成直後はこの優先順位を見て、優先度1から採点する。

`--validate-review-csv` は、列不足、画像指定ミス、スコア範囲外、`hardCap` / `override` の0〜100範囲外を検出する。スコア列が未入力の行は警告として扱い、適用時はスキップされるため、全15枚を一度に埋めなくてもよい。

参考画像と生成候補を並べて採点する場合は、レビュー用HTMLを作る。

```bash
python3 scripts/style_eval.py --review-workbench coffee_walk_v1
```

出力:

```text
reports/coffee_walk_v1_review_workbench.html
```

このHTMLは、候補画像、同スタイルの参考画像、スタイル指紋、自動スコア、対象スタイル順位、失敗理由、6軸スコア欄を1画面で確認できる。出力CSVは `--apply-review-csv` と同じ列を持つ。

```json
{
  "subjectAdherence": 15,
  "lineShapeLanguage": 14,
  "textureMediumVisual": 13,
  "compositionIntent": 8,
  "stylePurity": 9,
  "productionUsefulness": 2
}
```

または、コマンドで記録する。

```bash
python3 scripts/style_eval.py \
  --set-review coffee_walk_v1 naive_wobbly round_01_a.png \
  --scores 15 14 13 8 9 2 \
  --notes "線の揺れは良いが、紙の余白が少し多い"
```

`--scores` の順番:

```text
subjectAdherence lineShapeLanguage textureMediumVisual compositionIntent stylePurity productionUsefulness
```

最大点:

```text
15 15 15 8 10 2
```

11. 90点未満なら、`data/style_fingerprints.json` の `improvementRules` に沿ってプロンプトを修正する。

12. 次ラウンドのプロンプトを生成する。

```bash
python3 scripts/style_eval.py --next-round coffee_walk_v1 coffee_walk_v2
```

Codex上のサブスク生成まで続ける場合は、改善プロンプト、生成計画、Codex用プロンプト、ダッシュボード、レビューガイドをまとめて準備する。

```bash
python3 scripts/style_eval.py --prepare-next-round coffee_walk_v1 coffee_walk_v2 --variants 3
```

前ラウンドの評価JSONに手入力した `manualReview`、自動評価の弱い指標、対象スタイル順位、`improvementRules` から `prompt_runs/coffee_walk_v2/{style_id}.md` を作る。改善制約は次ラウンドの `generation_plan.json` と Codex用プロンプト本文にも入る。

13. `round_02`, `round_03` と繰り返し、90点以上で合格にする。

14. 全スタイルが合格したかをゲートで確認する。

```bash
python3 scripts/style_eval.py --gate coffee_walk_v1
```

全5スタイルに合格画像がある場合のみ終了コード0。未生成、未レビュー、90点未満、対象スタイルが1位でない場合は終了コード1。

完了監査:

```bash
python3 scripts/style_eval.py --audit coffee_walk_v1
python3 scripts/style_eval.py --gate-report coffee_walk_v1
```

37枚解析、5スタイル、生成計画、生成画像の存在、レビュー済み合格、ゲート成功を要件別に表示する。
`--gate-report` はMarkdown/HTMLも出力し、スタイル別の次アクションと失敗理由を確認できる。

## 自己テスト

実画像生成前に、評価パイプライン自体を検証するための `style_selftest` ランを用意している。各スタイルの参照画像1枚を `generated/style_selftest/{style_id}/reference_selftest.webp` に置き、レビュー記録とゲートが通ることを確認する。

```bash
python3 scripts/style_eval.py --smoke-test coffee_walk_v1
python3 scripts/style_eval.py --report style_selftest
python3 scripts/style_eval.py --gate style_selftest
```

`--smoke-test` は参照画像37枚、基準値、生成計画、自己テスト、実ランの現状をまとめて確認する。`style_selftest` はプロンプト品質の合格ではなく、採点・レビュー保存・合格ゲートの動作確認用。

## 失敗時の典型パターン

| 失敗 | 修正方向 |
|---|---|
| 内容は合っているがスタイルが違う | スタイル指紋の line / texture / color を強める |
| スタイルは近いがコーヒーがない | `takeaway coffee cup held in one hand` を前方に移す |
| 写実化する | `flat illustration`, `not photorealistic`, `no camera lens effects` を追加 |
| 3D化する | `2D illustration`, `flat`, `no 3D render`, `no glossy lighting` を追加 |
| 余白が違う | `large negative space` または `poster-like dense composition` を明示 |
| 色が違う | `limited palette`, `one accent color`, `blue and orange accents` などを指定 |

## 合格条件

- 総合90点以上
- 全スタイル照合で対象スタイルが1位
- Subject adherence が12/15以上
- Style purity が8/10以上
- Texture / medium visual が12/15以上
- 元スタイルと違うジャンルへの逸脱がない

この最低軸条件は `--gate` の合格判定にも反映する。レビュー済み画像が90点以上でも、主題、技法、スタイル純度の最低条件を下回る場合は `failureReasons` に理由を残して不合格にする。

## 強制上限

以下に該当する場合、見た目が良くても上限点を超えない。

| 条件 | 上限 |
|---|---:|
| 媒体・技法が明確に違う | 89 |
| 写実・3Dが混入している | 85 |
| 色の系統が違う | 80 |
| 線や形の言語がスタイルと矛盾している | 75 |

## スタイル別重み

| Style | Palette | Line / edge | Shape | Texture / medium | Composition | Finish |
|---|---:|---:|---:|---:|---:|---:|
| naive_wobbly | 15 | 25 | 25 | 10 | 15 | 10 |
| grain_flat | 20 | 10 | 20 | 25 | 15 | 10 |
| print_relief | 20 | 15 | 15 | 30 | 10 | 10 |
| editorial_outline | 15 | 30 | 20 | 5 | 20 | 10 |
| flat_vector | 25 | 15 | 25 | 5 | 20 | 10 |
