# 2026-05-26 修正・追加ログ（イラスト プロンプト工房 GUI）

本日の `app/` フロントエンド・バックエンドおよび `scripts/style_eval.py` に対する
実装変更の記録。1 ドキュメント = 本日分の変更サマリー。

---

## 概要

華やかさより**実用性**を重視し、イラスト生成〜取り込み〜採点〜90点ゲートまでを
アプリ内で完結できる 4 タブ構成に刷新した。`coffee_walk_v1` 固定から脱却し、
題材ベースの run 管理・汎用評価ロジックへ移行。

---

## フロントエンド（`app/frontend/`）

### 4 タブ構成

| タブ | ファイル | 内容 |
|------|----------|------|
| イラスト生成 | `pages/PromptBuilder.tsx` | スタイル選択、題材入力、run 作成、エクスポート |
| 取り込み | `pages/RunDashboard.tsx` | 監査・取り込み、スロットサムネ、パス記憶 |
| 採点・ゲート | `pages/ReviewWorkbench.tsx` | 6 軸採点、一括保存、GatePanel |
| スタイル設定 | `pages/StyleSource.tsx` | プロンプト断片等の編集（従来どおり） |

### 新規ファイル

| パス | 役割 |
|------|------|
| `components/RunSelector.tsx` | run 切替・一覧更新・**2 段階確認付き run 削除** |
| `hooks/useLocalStorage.ts` | runId / sourceDir / フォーム等の永続化 |
| `hooks/useAppRouter.ts` | **URL ハッシュルーティング**（`#/generate?run=...`） |
| `constants/runStyles.ts` | デフォルト 5 スタイル ID・タブ定数 |
| `utils/intakeAuditSummary.ts` | 取り込み監査結果の人間可読サマリー |
| `pages/ReviewWorkbench.tsx` | 採点ワークベンチ + `GatePanel` コンポーネント |

### 主要 UI 改善

**取り込み（RunDashboard）**

- 監査サマリー表示（`AuditSummary`）
- 取り込み成功メッセージ + 「採点タブへ進む」ボタン
- 詳細 JSON は `<details>` に折りたたみ

**App.tsx 連携**

- 取り込み成功 / 「採点へ」クリックで採点タブへ自動遷移
- 遷移時 `autoRefresh` で評価を自動再計算

**採点（ReviewWorkbench）**

- **満点入力**（行単位 + 「未採点に満点」一括）
- **未採点のみ保存**（採点済み行は上書きしない）
- **すべて一括保存**（全行上書き）
- 進捗表示: `採点済み X/Y（未採点 Z）`
- 状態バッジ: 未採点 / 入力済・未保存 / 合格 / 未合格

**ゲート（GatePanel）**

- 次ラウンド run ID 入力欄
- 「同名 run があれば上書き」チェックボックス
- 名前衝突時は API が別 ID を選びメッセージ表示

**生成（PromptBuilder）**

- **Strength スライダー**（1–100、標準 70）
- **5 スタイル一括プレビュー**（比較カード + コピー）
- run メタから題材・strength を復元
- Project Hub リンクは run 選択時のみ表示（`coffee_walk_v1` 固定リンク削除）

**RunSelector**

- `DELETE /api/runs/{id}` による run 削除 UI

### API クライアント（`api.ts`）

追加・拡張した型・メソッド:

- runs CRUD、`runMeta`、`intakeAudit`、`syncRun`
- `reviewWorkbench`、`refreshEvaluation`、`submitReviewsBatch`
- `gateSummary`、`prepareNextRound`（`overwrite` 対応）
- `compose`（`strength`）、**`composeBatch`**
- 型: `IntakeAudit`, `SyncResult`, `WorkbenchPayload`, `GateSummary` 等

### Tailwind CSS

- `@tailwindcss/vite` 導入（`vite.config.ts`）
- `src/index.css` で `@import "tailwindcss"`
- App シェルに Tailwind ユーティリティ追加
- 既存 `App.css` はページ固有スタイルとして併用（段階移行）

### スタイル追加（App.css）

- `.audit-summary`, `.import-complete`
- `.next-round-form`, `.review-toolbar`, `.review-row-actions`
- `.batch-preview-grid`, `.strength-control`
- 採点カード状態: `.unscored`, `.ready`, `.scored`

---

## バックエンド（`app/backend/`）

### 新規・拡張 API

| Method | Path | 用途 |
|--------|------|------|
| GET/POST | `/api/runs` | run 一覧 / 新規作成 |
| DELETE | `/api/runs/{id}` | run 削除 |
| GET | `/api/runs/{id}/meta` | run メタ |
| POST | `/api/runs/{id}/intake-audit` | 取り込み前監査 |
| POST | `/api/runs/{id}/sync` | 監査 + 取り込み |
| GET | `/api/runs/{id}/reviews/workbench` | 採点ワークベンチ |
| POST | `/api/runs/{id}/reviews/batch` | 一括採点 |
| POST | `/api/runs/{id}/evaluation/refresh` | 評価再計算 |
| GET | `/api/runs/{id}/gate/summary` | ゲートサマリー |
| POST | `/api/runs/{id}/next-round` | 次ラウンド準備 |
| POST | `/api/prompts/compose-batch` | 5 スタイル一括プレビュー |
| POST | `/api/runs/{id}/export` | プロンプトパック書き出し |

静的マウント: `/generated`, `/prompt_runs`, `/references`, `/reports`

### runner.py 主要追加

- `create_run` — 題材スラッグ run ID、5 スタイル MD 生成、メタ JSON
- `ensure_run_meta` — legacy run 向け `run_meta.json` 自動生成
- `find_available_run_id` — 次ラウンド名衝突回避
- `review_workbench_data`, `gate_summary`, `prepare_next_round`, `delete_run`
- `compose_prompt` + **`apply_style_strength`**
- **`compose_prompts_batch`**
- `DEFAULT_RUN_STYLE_IDS`（新 run の 5 スタイル）

新 run デフォルト 5 スタイル:

- `naive_wobbly_line`
- `grain_flat`
- `print_relief_lino`
- `editorial_outline_minimal`
- `flat_vector`

（15 枚 = 5 × 3 バリアント）

### schemas.py

- `CreateRunRequest.strength`
- `ComposeRequest.strength`, `ComposeBatchRequest`, `ComposeBatchResult`
- `PrepareNextRoundRequest.overwrite`
- `BatchReviewRequest` 等

### その他

- `requirements.txt` に **Pillow** 追加（サムネ生成用）

---

## 評価スクリプト（`scripts/style_eval.py`）

### legacy 互換

- `LEGACY_STYLE_ALIASES`（`naive_wobbly` → `naive_wobbly_line` 等）
- `load_run_meta` / `load_run_theme` / `styles_for_run`
- `resolve_style_record` — legacy スタイル ID 解決
- `write_run_report(..., force=False)` + **`report_is_stale` キャッシュ**（2 回目以降高速化）
- `write_next_round` / `source_run_iteration_rows` の legacy 対応
- `codex_prompt_text` を run 題材に連動

### 題材固定文言の汎用化（本日後半）

コーヒー散歩固定文言を削除し、run メタベースのヘルパーに置換:

| 関数 | 役割 |
|------|------|
| `theme_subject_lock_line` | 改善制約の主題ロック文 |
| `theme_subject_clarity_focus` | バリアント A の subject clarity |
| `theme_subject_adherence_messages` | 採点ガイド・主題軸 |
| `theme_composition_messages` | 構図軸ガイド |
| `theme_production_usefulness_messages` | 実用性軸ガイド |
| `theme_manual_subject_hint` | 手動採点フィードバック |

更新した呼び出し元:

- `improvement_constraints_for_style(style, style_report, theme=...)`
- `manual_axis_constraints(..., theme=...)`
- `variant_focus(style, index, theme=...)`
- `score_axis_guidance(data, style, theme=...)`
- `write_generation_plan` — theme を variant_focus に渡す
- `write_next_round` / `source_run_iteration_rows`
- `render_review_guide_md` — `load_run_theme` 使用

---

## ドキュメント

| ファイル | 内容 |
|----------|------|
| `app/README.md` | 起動手順・API 一覧・チェックリスト（全項目完了） |
| `document/NamingConvention.md` | ディレクトリ・ファイル・コンポーネント命名規則 |
| `document/20260526_AppUIChangelog.md` | 本ファイル |

---

## 起動・確認

```bash
cd /Users/kazuma/Documents/イラストツール
cd app/frontend && npm run build && cd ../..
app/.venv/bin/python app/server.py
```

- URL: http://127.0.0.1:8765
- ルーティング例: `http://127.0.0.1:8765/#/import?run={run_id}`

---

## 運用上の注意

- 初回の採点・ゲート読込は評価レポート生成のため数十秒かかることがある。2 回目以降はキャッシュで高速。
- 取り込み後は採点タブで「評価を再計算」が自動実行される（手動でも可能）。
- `coffee_walk_v1` 等は **検証用 legacy run**。評価ロジックは run の `run_meta.json` / `generation_plan.json` の題材を参照する。
- 90 点ゲートは自己検証用。汎用運用では参考スコアとして扱う。

---

## 未着手・今後（参考）

- `App.css` 全体の Tailwind 完全移行
- History API ベースのルーティング（現状はハッシュ）
- 5 スタイル全合格の real run データ（運用・採点で埋める部分）
