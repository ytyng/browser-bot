#!/usr/bin/env python3
"""
ローカル :9222 で起動している Chrome に接続し、
BrowserUse を使用する MCP サーバーの実装

使用方法:
    python mcp_server.py

前提条件:
    - Chrome が --remote-debugging-port=9222 で起動していること
    - 必要な環境変数が設定されていること (OPENAI_API_KEY など)
"""

import os
import sys
import logging
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
import fastmcp
from browser_bot import run_task, logger

# .envファイルから環境変数を読み込む
load_dotenv()


# MCPサーバーの設定
server = fastmcp.FastMCP(
    name="browser_bot",
    instructions="""ブラウザ操作のための MCP サーバーです。

このサーバーは browser_use を使用して、ローカルで起動している Chrome (:9222) に接続します。

使用例:
- Web サイトの自動操作
- フォームの自動入力
- 情報の自動収集
- UI テストの自動化

注意事項:
- Chrome が --remote-debugging-port=9222 で起動している必要があります
- launch-chrome.sh スクリプトを使用して Chrome を起動してください""",
)


# ツールを登録
@server.tool(
    name="browser_use_local_chrome_9222",
    description="""ローカルで起動している Chrome (:9222) に接続して、ブラウザ操作を行うツールです。

パラメーター:
    task_text (str): 実行したいタスクの説明。
                    例: "https://example.com を開いて、ログインボタンをクリックしてください"

戻り値:
    str: タスクの実行結果。成功時は結果の説明、失敗時はエラーメッセージ。

例:
    - "Google で 'Python' を検索してください"
    - "フォームに名前とメールアドレスを入力して送信してください"
    - "ページのスクリーンショットを撮ってください"
""",
)
async def browser_use_local_chrome_9222_tool(task_text: str) -> str:
    """ブラウザ操作タスクを実行する"""
    if not task_text or not task_text.strip():
        error_msg = "❌ エラー: タスクの説明が空です。実行したい操作を指定してください。"
        logger.error(error_msg)
        return error_msg

    logger.info(f"MCP ツール実行開始: {task_text[:100]}...")

    try:
        result_text = await run_task(task=task_text)
        logger.info(f"MCP ツール実行完了: 成功")
        return str(result_text)
    except Exception as e:
        error_msg = f"❌ エラー: タスク実行中に予期しないエラーが発生しました: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


def main() -> None:
    """
    メイン関数: MCPサーバーを起動します
    """
    logger.info("MCP サーバー起動中...")

    # 必要な環境変数のチェック
    required_env_vars = ['OPENAI_API_KEY']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]

    if missing_vars:
        error_msg = f"❌ エラー: 必要な環境変数が設定されていません: {', '.join(missing_vars)}"
        logger.error(error_msg)
        print(error_msg, file=sys.stderr)
        sys.exit(1)

    try:
        # サーバーを起動 (stdio モード)
        logger.info("MCP サーバー起動完了")
        server.run()  # stdio is default
    except KeyboardInterrupt:
        logger.info("MCP サーバーを終了します (KeyboardInterrupt)")
    except Exception as e:
        logger.error(f"MCP サーバーエラー: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
