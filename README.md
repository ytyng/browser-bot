# Browser Bot

Chrome の自動操作を行う MCP (Model Context Protocol) サーバーです。browser_use を使用して、ローカルで起動している Chrome (:9222) に接続し、Web ブラウザの操作を自動化します。

## 主な機能

- **ブラウザ自動操作**: 自然言語による指示でブラウザ操作を実行
- **スクリーンショット取得**: 表示領域または全領域のスクリーンショット
- **ソースコード取得**: 現在表示されているページの HTML ソース
- **MCP プロトコル対応**: Claude などの AI アシスタントからの操作が可能

## 必要な環境

- Python 3.12+
- Chrome ブラウザ
- OpenAI API キー または Google API キー (Gemini 使用時)
- uv (Python パッケージマネージャー)

## インストールと設定

### 1. 依存関係のインストール

```shell
uv sync
```

### 2. 環境変数の設定

`.env` ファイルを作成し、以下を設定する

#### OpenAI を使う場合

```env
OPENAI_API_KEY=your_openai_api_key_here
# デフォルトは gpt-5-mini
# 他のモデルを使う場合は BROWSER_USE_LLM_MODEL を設定
# BROWSER_USE_LLM_MODEL=gpt-4o
```

#### Google Gemini を使う場合

```env
GOOGLE_API_KEY=your_google_api_key_here
BROWSER_USE_LLM_MODEL=gemini-2.5-flash
```

### 3. Chrome の起動

デバッグポート付きで Chrome を起動：

```shell
./launch-chrome.sh
```

## 使用方法

### MCP サーバーとして使用

```shell
./launch-mcp-server.sh
```

### 直接実行

パスに以下のスクリプトを登録する

browser-bot
```shell
#!/usr/bin/env zsh

cd ${HOME}/<your-workspace>/browser-bot
.venv/bin/python3 ./browser_bot.py
```

```shell
echo "https://www.google.com を開いて、'Python tutorial' を検索してください" | browser-bot
```

## MCP ツールの仕様

### 1. browser_use_local_chrome_9222

Chrome ブラウザでの自動操作を実行するツールです。

#### パラメーター

- **task_text** (str, 必須): 実行したいブラウザ操作タスクの詳細な説明
- **max_steps** (int, オプション): 最大実行ステップ数（デフォルト: 7、範囲: 1-30）

### 2. get_page_source

現在アクティブなタブのソースコードを取得します。ページの HTML 構造を解析したい時に使用します。

### 3. get_visible_screenshot

現在アクティブなタブの表示されている箇所をスクリーンショットします。現在見えている部分の状態を確認したい時に使用します。

### 4. get_full_screenshot

現在アクティブなタブの全領域をスクリーンショットします。ページ全体のレイアウトを確認したい時に使用します。

#### タスクの書き方のポイント

1. **URL は完全な形式で記述**
   - ✅ `https://example.com`
   - ❌ `example.com`

2. **クリックする要素は具体的に説明**
   - ✅ `'送信'と書かれた青いボタン`
   - ❌ `ボタン`

3. **入力する内容は明確に指定**
   - ✅ `メールアドレス欄に 'test@example.com' を入力`
   - ❌ `メールアドレスを入力`

4. **複数の操作は箇条書きで順序立てて記述**

#### 使用例

**簡単な検索操作 (3-5ステップ):**
```
https://www.google.com を開いて、検索ボックスに 'Python tutorial' と入力し、検索ボタンをクリックしてください
```

**フォーム入力操作 (5-10ステップ):**
```
現在のページで、お問い合わせフォームの名前欄に '山田太郎'、メールアドレス欄に 'yamada@example.com'、メッセージ欄に 'テストメッセージです' と入力して、送信ボタンをクリックしてください
```

**複雑な操作 (10-15ステップ):**
```
https://www.amazon.co.jp を開いて、検索ボックスに 'Python プログラミング' と入力し、検索を実行してください。その後、最初の検索結果をクリックしてください
```

## ファイル構成

```
browser-bot/
├── browser_bot.py              # メインの操作実行エンジン
├── mcp_server.py              # MCP サーバー実装
├── launch-mcp-server.sh       # MCP サーバー起動スクリプト
├── launch-chrome.sh           # Chrome 起動スクリプト（デバッグポート付き）
├── pyproject.toml             # プロジェクト設定と依存関係
├── uv.lock                    # 依存関係ロックファイル
├── tests/                     # テストスクリプト
│   ├── test-mcp-initialize.sh
│   ├── test-mcp-tools-list.sh
│   ├── test-run.sh
│   └── test-run-with-path.sh
├── README.md
└── CLAUDE.md
```

## 依存関係

- **browser-use**: ブラウザ自動操作ライブラリ
- **fastmcp**: MCP サーバー実装フレームワーク
- **langchain_openai**: OpenAI LLM 統合
- **langchain_google_genai**: Google Gemini LLM 統合
- **playwright**: ブラウザ制御
- **httpx**: HTTP クライアント
- **pillow**: 画像処理
- **python-dotenv**: 環境変数管理

## ログ

すべてのログは以下のファイルに記録されます：

- **ログファイル**: `/tmp/browser-bot.log`

注意: MCP サーバーでは stdout にログを出力しません（stdio 通信を妨げるため）

## テスト

### 初期化テスト
```bash
./tests/test-mcp-initialize.sh
```

### ツール一覧テスト
```bash
./tests/test-mcp-tools-list.sh
```

### 直接実行テスト
```bash
./tests/test-run.sh
```

### パス経由実行テスト
```bash
./tests/test-run-with-path.sh
```

## トラブルシューティング

### Chrome が起動しない

1. Chrome が既に起動している場合は終了してください
2. `./launch-chrome.sh` を実行してください
3. ポート 9222 が使用されていないか確認してください

### MCP サーバーでエラーが出る

1. `.env` ファイルに `OPENAI_API_KEY` が設定されているか確認
2. Chrome がデバッグポート付きで起動しているか確認
3. ログファイル (`/tmp/browser-bot.log`) を確認

### 操作が途中で止まる

- `max_steps` パラメーターを増やしてみてください
- タスクの内容をより具体的に記述してください

### スーパーリロードが期待通りに動作しない

Browser Bot では複数の方法でスーパーリロード（キャッシュ無視のリロード）を実装しています：

1. **super_reload**: 3段階のフォールバック方式
   - Chrome DevTools Protocol (CDP) を使用（最も確実）
   - キーボードショートカット（Ctrl+Shift+R / Cmd+Shift+R）
   - 通常のリロード（フォールバック）

2. **force_reload_with_javascript**: JavaScript による強制リロード
   - `location.reload(true)` を使用
   - キャッシュバスティング用のタイムスタンプ付きリロード

いずれかの方法で確実にキャッシュをクリアできます。
