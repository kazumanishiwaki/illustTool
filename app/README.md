# illustration-tool GUI

汎用イラスト生成プロンプト＋評価ループの GUI スケルトン。
既存の `scripts/style_eval.py` を **subprocess でラップ** する
FastAPI バックエンド + Vite/React フロントエンドの構成。

```
app/
├── backend/                FastAPI: CLI ラッパー
│   ├── main.py             /api/* エンドポイント
│   ├── runner.py           style_eval.py を subprocess 実行
│   ├── schemas.py          Pydantic モデル
│   └── requirements.txt
└── frontend/               Vite + React + TS
    └── src/
        ├── App.tsx         評価ループ + プロンプト作成 + スタイル設定
        └── api.ts          API クライアント
```

## 起動

### Codex app server（FastAPI + built frontend, port 8765）

```bash
cd /Users/kazuma/Documents/イラストツール
cd app/frontend && npm run build && cd ../..
app/.venv/bin/python app/server.py
```

ブラウザで http://127.0.0.1:8765 を開く。API とフロントエンドを
同じサーバから配信する。

### バックエンド（FastAPI, port 8765）

```bash
cd /Users/kazuma/Documents/イラストツール
app/.venv/bin/uvicorn app.backend.main:app --host 127.0.0.1 --port 8765 --reload
```

初回のみ venv 構築済（`app/.venv/`）。再構築するなら:

```bash
python3 -m venv app/.venv
app/.venv/bin/pip install -r app/backend/requirements.txt
```

### フロントエンド（Vite, port 5173）

```bash
cd /Users/kazuma/Documents/イラストツール/app/frontend
npm run dev
```

ブラウザで http://127.0.0.1:5173 を開く。バックエンドが 8765 で
起動していれば、`coffee_walk_v1` の評価ループ状態、プロンプト作成、
5スタイルの設定編集が表示される。

## API

| Method | Path | CLI | 用途 |
|---|---|---|---|
| GET | `/api/health` | — | 疎通確認 |
| GET | `/api/styles` | データ直読 | 5スタイル + 参考画像パス |
| GET | `/api/styles/{style_id}` | データ直読 | スタイル詳細 |
| PUT | `/api/styles/{style_id}` | データ更新 | スタイル断片・特徴・改善ルール更新 |
| POST | `/api/prompts/compose` | データ直読 | 汎用主題 + スタイル断片からプロンプト生成 |
| GET | `/api/runs/{run_id}/status` | `--loop-status` | 現在フェーズ + blockers |
| POST | `/api/runs/{run_id}/prompt-pack` | `--codex-image-pack` | Codex プロンプトパック生成 |
| POST | `/api/runs/{run_id}/plan?variants=3` | `--generation-plan` | 生成計画作成 |
| POST | `/api/runs/{run_id}/refresh` | `--refresh-run` | 全レポート再生成 |
| POST | `/api/runs/{run_id}/reviews` | `--set-review` | 採点保存（CSV往復なし） |
| GET | `/api/runs/{run_id}/gate` | `--gate-report` | ゲート判定 |

### 静的マウント

| Path | 中身 |
|---|---|
| `/references/*` | プロジェクト直下の参考画像 |
| `/generated/*` | `generated/` 配下の生成画像 |
| `/reports/*` | レポート HTML/MD |

## 現状

- [x] 5スタイルのサムネ・参考画像一覧
- [x] run status（phase + blockers + next commands）
- [x] generation-plan / prompt-pack / refresh-run / gate-report ボタン
- [x] 採点保存 API（`--set-review` ラッパー、UI 未実装）
- [x] Prompt Builder UI（フォーム + 必須要素 + 用途）
- [x] Style Source UI（スタイル断片・特徴・改善ルール編集）
- [ ] Dashboard UI（15枚スロット + インポート）
- [ ] Review Workbench UI（候補 × 参考 × 6軸採点）
- [ ] Gate Report UI

## 補足

- macOS のファイル名は NFD で保存されるため、`referenceGlob` 照合では
  `runner.style_reference_images` で NFC 正規化してから fnmatch する。
- 90点ゲートは初期構築の自己検証用。汎用運用では参考スコア。
- CSV 往復は撤廃。採点は `POST /api/runs/{id}/reviews` から直接
  `--set-review` を呼ぶ。
