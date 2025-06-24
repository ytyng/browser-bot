# Browser Bot - Claude Code 開発ガイド

このドキュメントは、Browser Bot プロジェクトを Claude Code で開発・メンテナンスする際のガイドです。

## プロジェクト概要

Browser Bot は Chrome ブラウザの自動操作を行う MCP (Model Context Protocol) サーバーです。browser_use ライブラリを使用して、自然言語による指示でブラウザ操作を実行できます。

### 主な機能

- **ブラウザ自動操作**: 自然言語による指示でブラウザ操作を実行
- **スクリーンショット取得**: 表示領域または全領域のスクリーンショット
- **ソースコード取得**: 現在表示されているページの HTML ソース
- **複数 LLM 対応**: OpenAI GPT および Google Gemini をサポート

## アーキテクチャ

### コアコンポーネント

- **browser_bot.py**: メインの操作実行エンジン
- **mcp_server.py**: MCP プロトコル実装とツール定義
- **launch-mcp-server.sh**: MCP サーバー起動スクリプト
- **launch-chrome.sh**: Chrome 起動スクリプト

### 依存関係

- **browser_use**: ブラウザ自動操作ライブラリ
- **fastmcp**: MCP サーバー実装フレームワーク
- **langchain_openai**: OpenAI LLM 統合
- **langchain_google_genai**: Google Gemini LLM 統合
- **playwright**: ブラウザ制御
- **httpx**: HTTP クライアント
- **pillow**: 画像処理
- **pydantic**: データバリデーション

## 開発時の重要なポイント

### 1. ログ設定

- すべてのログは `/tmp/browser_bot.log` に記録
- MCP サーバーでは stdout にログを出力しない（stdio 通信を妨げるため）
- ログレベルは環境変数 `BROWSER_USE_LOGGING_LEVEL=result` で制御

### 2. エラーハンドリング

- Chrome 接続エラーの適切な処理
- タスク実行エラーの詳細なログ記録
- ユーザーフレンドリーなエラーメッセージ

### 3. MCP プロトコル対応

- 初期化シーケンス: `initialize` → `notifications/initialized` → `tools/list`
- Pydantic Field を使った詳細なパラメーター説明
- JSON Schema による入力バリデーション
- 4つの MCP ツール実装:
  - `browser_use_local_chrome_9222`: ブラウザ自動操作
  - `get_page_source`: HTML ソースコード取得
  - `get_visible_screenshot`: 表示箇所のスクリーンショット
  - `get_full_screenshot`: 全領域のスクリーンショット

## コーディング規約

### 1. コードスタイル

- **flake8** 準拠（最大行長: 79文字）
- **black** フォーマッター使用
- 型ヒント必須（typing, Annotated, Pydantic Field）

### 2. ファイル構成

```python
# インポート順序
import os
import sys
from typing import Annotated

from dotenv import load_dotenv
from pydantic import Field
import fastmcp

from browser_bot import run_task, logger
```

### 3. 関数設計

- キーワード引数のみ使用（`*` パラメーター）
- async/await の適切な使用
- 詳細なドキュメンテーション

## テスト手順

### 1. 開発環境セットアップ

```bash
# 依存関係のインストール
uv sync

# Chrome の起動
./launch-chrome.sh

# 環境変数の確認
cat .env  # OPENAI_API_KEY または GOOGLE_API_KEY が設定されていること
```

### 2. テスト実行

```bash
# 初期化テスト
./tests/test-mcp-initialize.sh

# ツール一覧テスト
./tests/test-mcp-tools-list.sh

# 直接実行テスト
./tests/test-run.sh

# パス経由実行テスト
./tests/test-run-with-path.sh
```

### 3. MCP サーバーテスト

```bash
# サーバー起動
./launch-mcp-server.sh

# 別ターミナルでクライアントテスト
./tests/test-mcp-tools-list.sh
```

## デバッグ方法

### 1. ログ確認

```bash
# リアルタイムログ監視
tail -f /tmp/browser_bot.log
```

### 2. Chrome デバッグ

```bash
# Chrome の状態確認
curl http://localhost:9222/json/version

# アクティブなタブ一覧
curl http://localhost:9222/json
```

### 3. MCP プロトコルデバッグ

```bash
# JSON-RPC メッセージの確認
echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {...}}' | ./launch.sh
```

## よくある問題と解決方法

### 1. Chrome 接続エラー

**問題**: `Chrome が :9222 で起動していません`

**解決**:
```bash
# 既存 Chrome を終了
pkill -f chrome
# デバッグポート付きで再起動
./launch-chrome.sh
```

### 2. MCP サーバーエラー

**問題**: `Invalid request parameters`

**解決**:
- `initialize` → `notifications/initialized` の順序を確認
- JSON-RPC メッセージの形式を確認

### 3. LLM 接続エラー

**問題**: OpenAI または Google API 接続エラー

**解決**:
- `.env` ファイルで API キーを確認
- モデル名が正しいか確認（例: `gemini-2.5-flash`）
- 使用量制限に達していないか確認

### 4. タスク実行失敗

**問題**: `max_steps` 制限でタスクが途中終了

**解決**:
- `max_steps` パラメーターを増加
- タスク内容をより具体的に記述

## パフォーマンス最適化

### 1. ステップ数調整

- 簡単な操作: 3-5ステップ
- 中程度の操作: 5-10ステップ
- 複雑な操作: 10-15ステップ

### 2. ログレベル調整

```python
# 開発時: DEBUG
# 本番: INFO または WARNING
```

### 3. タイムアウト設定

```python
# Chrome 接続タイムアウト: 5秒
# エージェント実行: max_steps に依存
```

## 拡張ポイント

### 1. 新機能追加

- `mcp_server.py` に新しいツール定義
- `browser_bot.py` に実装ロジック追加
- テストスクリプトの作成
- 必要に応じて新しい依存関係を `pyproject.toml` に追加

### 2. エラーハンドリング強化

- より詳細なエラー分類
- リトライ機能の実装
- エラー回復処理

### 3. パフォーマンス改善

- 並列実行サポート
- キャッシュ機能
- ブラウザプール管理

## リリース手順

### 1. コード品質チェック

```bash
# 依存関係の更新
uv sync

# リンター実行（pre-commit があれば）
# python -m flake8 *.py
# python -m black *.py

# テスト実行
./tests/test-mcp-initialize.sh
./tests/test-mcp-tools-list.sh
./tests/test-run.sh
```

### 2. ドキュメント更新

- README.md の使用例更新
- CLAUDE.md の開発ガイド更新
- コメントとドキュメンテーション

### 3. 依存関係管理

```bash
# 新しい依存関係の追加
uv add <package_name>

# 開発依存関係の追加
uv add --dev <package_name>

# ロックファイルの更新
uv lock

# 同期
uv sync
```

## セキュリティ考慮事項

### 1. API キー管理

- `.env` ファイルを `.gitignore` に追加
- 環境変数での API キー管理
- ログにシークレット情報を出力しない

### 2. ブラウザセキュリティ

- デバッグポートへの外部アクセス制限
- 信頼できないサイトへのアクセス制御
- サンドボックス環境での実行推奨

### 3. 入力検証

- Pydantic Field による厳密な入力バリデーション
- SQLインジェクション等の脆弱性対策
- 悪意のあるスクリプト実行の防止

## トラブルシューティング

### 開発環境

- Python バージョン確認: 3.12+
- Chrome バージョン確認: 最新版推奨
- ポート競合確認: 9222 が空いていること

### 本番環境

- ログファイルの容量監視
- メモリ使用量の監視
- Chrome プロセスの安定性確認

このガイドを参考に、安全で効率的な開発を行ってください。
