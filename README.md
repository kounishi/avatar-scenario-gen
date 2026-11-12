# 記事URL → 動画ナレーション（ChatGPTサブスク / Codex CLI）

URLと動画の上限時間（分）を指定し、日本語の解説動画用ナレーションを生成するPython CLIです。
原稿生成には、ChatGPTアカウントでログインした公式Codex CLIを使用します。
OpenAI APIキーは不要です。API認証での実行は拒否し、API方式への自動切り替えは行いません。
契約プランのCodex利用枠を消費します。上限到達時はエラーになります。

## セットアップ（PowerShell / Python 3.9以上・Node.jsとnpm）

プロジェクトのフォルダーで実行します。

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
npm.cmd install --prefix .tools --cache .tools/npm-cache --no-audit --no-fund @openai/codex
.\.tools\node_modules\.bin\codex.cmd login
```

ブラウザーで、Codexを利用できるChatGPTアカウントにログインしてください。
この環境ではPython依存ライブラリとローカルCodex CLIはインストール済みです。初回ログインは必要です。
既にPATHにCodex CLIがある場合、npmインストールは省略できます。

```powershell
.\.tools\node_modules\.bin\codex.cmd login status
```

`Logged in using ChatGPT` と表示されれば準備完了です。
既にAPIキーでログインしている場合は、利用中の設定を確認したうえで `codex logout` → `codex login` で切り替えます。
アプリはログイン処理やログアウトを自動実行しません。

## 使い方

```powershell
.venv\Scripts\scenario-gen.exe "https://jahic-etc.com/2026/10/29/jahic_26_10_29/" 3 -o narration.txt
```

2分30秒なら `2.5` を指定します。

```powershell
.venv\Scripts\python.exe scenario_gen.py "https://example.com/article" 2.5 -o output\article.txt --cpm 280
.venv\Scripts\scenario-gen.exe --help
```

- `-o`: 保存先。省略時は `output/narration_日時.txt`。
- `--cpm`: 毎分の読み上げ文字数。既定300。
- `--dialogue`: 教わる役と教える役による2人の掛け合いにする。
- `--model`: Codexで利用できるモデル名。省略時はCodex CLIの設定を使用。
- `--codex`: Codexの実行ファイルのパス。省略時はPATH、その後プロジェクト内 `.tools` を検索。
- `--timeout`: 生成1回の待ち時間（秒）。既定300。
- `--force`: 既存ファイルの上書きを許可。

Windowsのnpmラッパーはシェルを経由せず、付属するネイティブ `codex.exe` に解決して実行します。
原稿ファイルには一文ごとに改行したナレーションだけが入り、UTF-8で保存されます。
保存先・文字数・推定時間はコンソールに表示します。

## 2人の掛け合い（3分以内）

```powershell
.venv\Scripts\scenario-gen.exe "https://jahic-etc.com/2026/10/29/jahic_26_10_29/" 3 --dialogue -o dialogue.txt
```

教わる役は `jahic-chan-001`、教える役は `etc-bouya-001` に固定しています。
教わる役の質問・確認に、教える役が解説する原稿を生成します。
出力はヘッダーなしの `話者名,セリフ` で、一文ごとに話者名を付けて改行します。

```text
jahic-chan-001,今回の通行止めはいつ行われるのですか？
etc-bouya-001,記事に記載された日程と対象区間を確認しましょう。
```

半角カンマを含むセリフはCSVの規則で二重引用符で囲みます。
話者名・区切り・CSVの引用符を除いた、2人のセリフの合計文字数で時間を計算します。
3分指定なら合計810文字までです。別の長さにする場合は分数を変更します。
不正な話者名・空のセリフ・片方しか登場しない出力などは書き直しの対象になります。
`--dialogue` を付けない場合は従来の1人ナレーションになります。
実際の尺は話者交代時の間でも変わるため、音声化後に確認してください。

## 時間と本文の扱い

- 毎分300文字、間の余裕10%で計算します。3分指定なら最大810文字です。
- 長すぎる原稿は最大2回書き直します。その分もCodexの利用枠を消費します。
- 指定文字数内にならなければエラーにし、途中で文章を切りません。
- 実際の尺は読み上げソフト、数字・略語の読み方、間で変わります。音声化後に確認し、必要なら `--cpm` を下げて再生成してください。
- 記事本文をPythonで抽出し、標準入力でCodexへ渡します。APIキーや旧 `.env` は読み込みません。
- Codexは一時ディレクトリで読み取り専用・承認要求なしのモードで実行します。最終応答を取り出し、Pythonが原稿を保存します。
- HTML記事向けです。ログイン、JavaScript実行必須、画像内だけの情報、PDFは非対応です。
- ページは5MB、抽出後は10万文字までです。長文を無断で切り落として要約しません。
- 未ログイン・本文取得失敗・Codex失敗時は終了コード1、不正な引数は2です。
- 生成結果の日付・数字・固有名詞は使用前に確認してください。

## 証明書エラーが出る環境

企業プロキシ等の環境では、管理者提供の信頼するCA証明書を設定してください。TLS検証は無効化しません。
この作業環境ではWindows証明書ストアから作成した `.venv/windows-ca.pem` を検証に使用しています。
同じ環境で必要な場合は以下を設定して実行できます。

```powershell
$env:PIP_CERT = (Resolve-Path .venv/windows-ca.pem).Path
$env:NODE_EXTRA_CA_CERTS = $env:PIP_CERT
$env:REQUESTS_CA_BUNDLE = $env:PIP_CERT
$env:CODEX_CA_CERTIFICATE = $env:PIP_CERT
```

## 検証

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

テストは実際のCodex利用枠を消費しません。
公式仕様: [非対話実行](https://learn.chatgpt.com/docs/non-interactive-mode)、[ChatGPT認証](https://learn.chatgpt.com/docs/auth?surface=cli)。
