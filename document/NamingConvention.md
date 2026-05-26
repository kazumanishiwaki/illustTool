# 命名規則

イラスト プロンプト工房（`app/frontend` + `app/backend`）のコード命名ルール。
1 目的 = 1 ドキュメント。他 md への依存は最小限にする。

## ディレクトリ名

機能・役割が一目で分かる **PascalCase** または意味のある英語名。

| 例 | 用途 |
|---|---|
| `pages/` | 画面単位の React ページ |
| `components/` | 再利用 UI 部品 |
| `hooks/` | カスタム React フック |
| `utils/` | 純粋関数・変換ロジック |
| `constants/` | 定数・列挙 |
| `backend/` | FastAPI バックエンド |

## ファイル名

処理・役割が分かる **camelCase**（React コンポーネントは PascalCase）。

| 種別 | 規則 | 例 |
|---|---|---|
| ページ | `{機能}{Page名}.tsx` または `{機能}.tsx` | `PromptBuilder.tsx`, `RunDashboard.tsx` |
| コンポーネント | `{パーツ名}{役割}.tsx` | `RunSelector.tsx` |
| フック | `use{機能}.ts` | `useLocalStorage.ts`, `useAppRouter.ts` |
| API / 型 | `api.ts` | フロント API クライアント |
| バックエンド | `snake_case` モジュール | `runner.py`, `main.py`, `schemas.py` |
| 定数 | `{domain}.ts` | `runStyles.ts` |
| ドキュメント | `{目的}.md` | `NamingConvention.md` |

## コンポーネント名（React）

**パーツ名を先頭**に置く。

| 例 | 意味 |
|---|---|
| `RunSelector` | Run 選択 UI |
| `GatePanel` | ゲート判定パネル |
| `ReviewWorkbench` | 採点ワークベンチ |

## 関数・フック

- フック: `use` プレフィックス（`useAppRouter`）
- イベントハンドラ: `on` + 動詞（`onCompose`, `onCreateRun`）
- 非同期 API 呼び出し: 動詞から（`reload`, `saveBatch`, `compose_prompt`）
- 純粋ヘルパー: 動詞または `build` / `parse` / `summarize`（`buildReviewItemFromDraft`, `parseHash`）

## 型名（TypeScript）

- リクエスト / レスポンス: `{名}Request`, `{名}Result`, `{名}Payload`
- ドメインエンティティ: `RunMeta`, `StyleSummary`, `WorkbenchRow`

## run ID

- 題材から自動生成: `{題材スラッグ}_{YYYYMMDD_HHMMSS}`
- 手動指定可。次ラウンドは `{base}_v2` 等、衝突時は API が空き ID を提案

## CSS / Tailwind

- **新規 UI**: Tailwind ユーティリティを優先（`index.css` で `@import "tailwindcss"`）
- **既存コンポーネント**: `App.css` の BEM 風クラスを段階的に移行
- 開発: `npm run dev`（Vite + Tailwind 同時）
- 本番: `npm run build`（TypeScript + Vite 本番ビルド）

## 禁止・注意

- 題材固定のハードコード（コーヒー散歩等）を評価ロジックに入れない → `run_meta.json` / `load_run_theme` を使う
- 1 ファイルに無関係な複数画面を混ぜない
- 略語だけの名前（`data`, `tmp`, `handler2`）は避ける
