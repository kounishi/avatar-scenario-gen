# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 概要

記事URLと動画の上限時間（分）から、日本語の解説動画用ナレーション（1人語り、または `--dialogue` で2人の掛け合いCSV）を生成するPython CLI。
原稿生成は OpenAI API ではなく、**ChatGPTアカウントでログインした公式 Codex CLI** をサブプロセスで呼び出して行う。API キー方式への切り替え・フォールバックは意図的に実装していない（README参照）。

## Codex CLI の利用方針（OpenAI API は使わず、ChatGPT サブスクの範囲内で使う）

LLM の呼び出しは、すべて ChatGPT サブスクリプション（Codex 利用枠）の範囲内で、Codex CLI 経由で行う。従量課金の OpenAI API は使わない。コードを変更するときは次を守ること。

- `openai` SDK の導入、OpenAI API への直接 HTTP リクエスト、API キーの読み込み（`.env` や `OPENAI_API_KEY` など）を追加しない。生成処理は必ず `CodexClient.generate` を通す。
- `CodexClient` の安全策を外さない。
  - 子プロセスの環境変数から `OPENAI_API_KEY` / `CODEX_API_KEY` / `OPENAI_BASE_URL` を除く。
  - `-c forced_login_method="chatgpt"` と `-c model_provider="openai"` を必ず付け、API キー認証や別のプロバイダーに切り替わらないようにする。
  - 実行前の `check_login` で ChatGPT ログインを確認し、API キーでのログインや未ログインなら中止する。
- 認証は利用者が手動で行う（`codex login`、`codex login status` で `Logged in using ChatGPT` と表示されることを確認）。アプリからログインやログアウトを自動で実行しない。
- 利用枠の上限に達したら、エラー（終了コード1）で止める。API 方式への自動切り替えや別サービスでの再試行はしない。
- 書き直しを1回するたびに利用枠を消費する。`generate_narration` の試行回数（現在最大3回）を増やすときは、利用枠への影響を考えること。
- テストでは実際の Codex を呼び出さない（モックか偽の codex スクリプトを使う）。開発中に実際の生成を試す実行も利用枠を消費するため、必要なときだけにする。
- 非対話実行は `codex exec` を使う。公式仕様: [非対話実行](https://learn.chatgpt.com/docs/non-interactive-mode)、[ChatGPT認証](https://learn.chatgpt.com/docs/auth?surface=cli)。

## コマンド（Windows / PowerShell、`.venv` 使用）

```powershell
# セットアップ
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
npm.cmd install --prefix .tools --cache .tools/npm-cache --no-audit --no-fund @openai/codex
.\.tools\node_modules\.bin\codex.cmd login        # ChatGPTでログイン（ユーザーが手動で行う）

# テスト（全件）— Codexの利用枠は消費しない
.venv\Scripts\python.exe -m unittest discover -s tests -v

# 単一テスト
.venv\Scripts\python.exe -m unittest tests.test_scenario_gen.DialogueTests.test_invalid_dialogue_is_rejected -v

# 実行
.venv\Scripts\scenario-gen.exe "https://example.com/article" 3 -o output\narration.txt
.venv\Scripts\scenario-gen.exe "https://example.com/article" 3 --dialogue -o output\dialogue.txt
```

lint / フォーマッタの設定はない。Python 3.9 互換を保つこと（`requires-python = ">=3.9"`）。

## アーキテクチャ

全ロジックは単一モジュール `scenario_gen.py`（`py-modules` で配布、エントリポイント `scenario-gen = scenario_gen:main`）。処理の流れ:

1. `main` — 引数検証（`article_url`, `positive_number`）、出力先の既存チェック（`--force` なしでは `"x"` モードで開き上書きしない）、`find_codex` → `CodexClient.check_login` → `fetch_article` → `generate_narration` → UTF-8・LF で保存。終了コードは成功0、実行時エラー1、argparse エラー2。
2. `fetch_article` — `requests` でストリーム取得（HTMLのみ、5MB上限）し `trafilatura` で本文抽出（100文字未満/10万文字超はエラー）。`requests`/`trafilatura` は関数内で import しており、`ImportError` は `main` で依存インストール案内に変換される。
3. `find_codex` — PATH または `--codex` から Codex を解決。Windows の npm ラッパー（`.cmd/.ps1/.js`）はシェル経由で実行せず、隣接する `node_modules/@openai/**/codex.exe` のネイティブバイナリに解決する。最後にプロジェクト内 `.tools` を探す。
4. `CodexClient` — 環境変数から `OPENAI_API_KEY` / `CODEX_API_KEY` / `OPENAI_BASE_URL` を除去して実行。`login status` が ChatGPT ログインでなければ拒否。`generate` は一時ディレクトリを cwd にし、`codex exec --sandbox read-only --ephemeral -c approval_policy="never" -c forced_login_method="chatgpt" -c model_provider="openai" --output-last-message <file> -` で、指示＋記事を標準入力に渡し、最終応答ファイルを読む。
5. `generate_narration` — 文字数予算 `int(minutes * cpm * 0.9)`（3分・300cpmで810文字）。最大3回生成し、形式不正や予算超過時は理由（と前回原稿）をプロンプトに追記して書き直させる。**予算を満たさなければ切り詰めずにエラー**にする（テストで保証されている仕様）。
6. 正規化 — `normalize_sentences` は句点・疑問符・感嘆符（後続の閉じ括弧を含む）で1文1行に分割し、小数は分割しない。`normalize_dialogue` は `話者名,セリフ` の2列CSVを検証し、1文ごとに話者名を付け直す。話者は定数 `LEARNER = "jahic-chan-001"` / `TEACHER = "etc-bouya-001"` に固定で、両者の登場が必須。対話モードの文字数（`spoken_character_count`）はセリフ列のみを数える。

## 守るべき設計上の制約

- 記事本文は信頼しない入力として扱う（プロンプトで本文内の命令に従わないよう指示している）。Codex は読み取り専用サンドボックス・一時ディレクトリで実行し、このリポジトリのファイルを読ませない。
- エラー時に Codex の出力をそのまま表示しない（記事本文やアカウント情報を含みうるため）。`ValueError`/`OSError` のメッセージのみ表示する。
- TLS 検証は無効化しない。社内プロキシ環境では `.venv/windows-ca.pem` を `REQUESTS_CA_BUNDLE` / `CODEX_CA_CERTIFICATE` / `NODE_EXTRA_CA_CERTS` / `PIP_CERT` に設定する（README参照）。
- ユーザー向けメッセージ・プロンプトは日本語。
- テストは `CodexClient` / `subprocess.run` / `fetch_article` をモックし、実際の Codex やネットワークを使わない。`CodexClient` のフラグ・環境変数の検証は、偽の codex として Python スクリプトを実行するテストで行っている。

## その他

- `.tools/`（ローカル Codex CLI と npm キャッシュ）、`output/`、`.venv/` は git 管理外。
- ルートの `yk-逆三角 - コピー.csv`、`zunnda-逆三角.txt` は掛け合い原稿のサンプル（話者名を別キャラクターに置き換えたもの）で、コードからは参照されない。
