# illustration-tool GUI

汎用イラスト生成プロンプト＋評価ループの GUI。
既存の `scripts/style_eval.py` を **subprocess でラップ** する
FastAPI バックエンド + Vite/React フロントエンドの構成。

```
app/
├── backend/                FastAPI: CLI ラッパー
│   ├── main.py             /api/* エンドポイント
│   ├── runner.py           style_eval.py を subprocess 実行
│   ├── schemas.py          Pydantic モデル
│   └── requirements.txt
└── frontend/               Vite + React + TS + Tailwind
    └── src/
        ├── App.tsx         4タブ（生成 / 取り込み / 採点・ゲート / スタイル設定）
        ├── hooks/useAppRouter.ts   URL ハッシュルーティング
        ├── pages/
        │   ├── PromptBuilder.tsx
        │   ├── RunDashboard.tsx
        │   ├── ReviewWorkbench.tsx
        │   └── StyleSource.tsx
        └── api.ts          API クライアント
```

命名規則: [`document/NamingConvention.md`](../document/NamingConvention.md)

## 起動

### Codex app server（FastAPI + built frontend, port 8765）

```bash
cd /Users/kazuma/Documents/イラストツール
cd app/frontend && npm run build && cd ../..
app/.venv/bin/python app/server.py
```

ブラウザで http://127.0.0.1:8765 を開く。API とフロントエンドを
同じサーバから配信する。

URL 例: `http://127.0.0.1:8765/#/generate?run=猫が窓辺で本を読んでいる_20260526_120000`

### バックエンド（FastAPI, port 8765）

```bash
cd /Users/kazuma/Documents/イラストツール
app/.venv/bin/uvicorn app.backend.main:app --host 127.0.0.1 --port 8765 --reload
```

### フロントエンド（Vite, port 5173）

```bash
cd /Users/kazuma/Documents/イラストツール/app/frontend
npm run dev
```

開発時は Vite が Tailwind を同梱コンパイル。本番 CSS は `npm run build` で dist に出力。

## ワークフロー

1. **イラスト生成** — 題材入力 → Strength 調整 → 5スタイル run 作成 → プロンプトコピー / エクスポート
2. **取り込み** — 保存フォルダを監査・取り込み → 成功後は採点タブへ（評価を自動再計算）
3. **採点・ゲート** — 6軸手動採点 → 90点ゲート → 次ラウンド準備
4. **スタイル設定** — プロンプト断片・特徴・改善ルールの編集

## API（主要）

| Method | Path | 用途 |
|---|---|---|
| GET | `/api/health` | 疎通確認 |
| GET | `/api/styles` | スタイル一覧 |
| POST | `/api/prompts/compose` | 1スタイルプロンプト合成（strength 対応） |
| POST | `/api/prompts/compose-batch` | 5スタイル一括プレビュー |
| GET/POST | `/api/runs` | run 一覧 / 新規作成 |
| DELETE | `/api/runs/{id}` | run 削除 |
| GET | `/api/runs/{id}/meta` | run メタ（題材・スタイル・strength） |
| POST | `/api/runs/{id}/intake-audit` | 取り込み前監査 |
| POST | `/api/runs/{id}/sync` | 監査＋取り込み |
| GET | `/api/runs/{id}/reviews/workbench` | 採点ワークベンチ |
| POST | `/api/runs/{id}/reviews/batch` | 一括採点保存 |
| POST | `/api/runs/{id}/evaluation/refresh` | 評価レポート再計算 |
| GET | `/api/runs/{id}/gate/summary` | ゲートサマリー |
| POST | `/api/runs/{id}/next-round` | 次ラウンド準備 |
| POST | `/api/runs/{id}/export` | プロンプトパック書き出し |

### 静的マウント

| Path | 中身 |
|---|---|
| `/references/*` | プロジェクト直下の参考画像 |
| `/generated/*` | `generated/` 配下の生成画像 |
| `/prompt_runs/*` | run ごとの生成物 |
| `/reports/*` | レポート HTML/MD |

## 現状

- [x] 4タブ UI（生成 / 取り込み / 採点・ゲート / スタイル設定）
- [x] run 作成・切替・削除（題材ベースの run ID）
- [x] 取り込み監査サマリー + 採点タブへの導線（評価自動再計算）
- [x] 6軸採点ワークベンチ + 一括保存（満点入力・未採点のみ保存）
- [x] 90点ゲートパネル + 次ラウンド準備（ID 衝突回避・上書きオプション）
- [x] 評価レポートキャッシュ（2回目以降の採点・ゲート高速化）
- [x] legacy run（`coffee_walk_v1` 等）互換
- [x] 題材固定文言の汎用化（`improvement_constraints` / 採点ガイド / バリアント）
- [x] Strength UI（1–100、プロンプト強度）
- [x] 5スタイル一括プレビュー
- [x] URL ハッシュルーティング（`#/generate?run=...`）
- [x] Tailwind CSS 導入（Vite プラグイン、段階的移行）

## 補足

- macOS のファイル名は NFD で保存されるため、`referenceGlob` 照合では NFC 正規化してから fnmatch する。
- 90点ゲートは初期構築の自己検証用。汎用運用では参考スコア。
- 採点は `POST /api/runs/{id}/reviews` から直接 `--set-review` を呼ぶ（CSV 往復なし）。
- 新 run のデフォルト5スタイル: `naive_wobbly_line`, `grain_flat`, `print_relief_lino`, `editorial_outline_minimal`, `flat_vector`（15枚 = 5×3）。
- `coffee_walk_v*` はループ検証用フィクスチャ。評価ロジックは run の題材メタを参照する。
