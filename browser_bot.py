#!/usr/bin/env python3

""" """
import asyncio
import os
import sys
import logging
from pathlib import Path
import httpx
from dotenv import load_dotenv
from browser_use import Agent, BrowserSession
from langchain_openai import ChatOpenAI


# browser_use をインポートする前にログ設定を行う
os.environ['BROWSER_USE_LOGGING_LEVEL'] = 'result'

# ファイルハンドラーの設定
log_file = '/tmp/browser_bot.log'
file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
file_handler.setFormatter(
    logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
)

# ルートロガーの設定
logger = logging.getLogger()
logger.handlers = []  # 既存のハンドラーをクリア
logger.addHandler(file_handler)
logger.setLevel(logging.DEBUG)

# サードパーティーのロガーも設定
for logger_name, log_level in [
    ('httpx', logging.WARNING),
    ('selenium', logging.WARNING),
    ('playwright', logging.WARNING),
    ('urllib3', logging.WARNING),
    ('asyncio', logging.WARNING),
    ('fastmcp', logging.INFO),
    ('FastMCP.fastmcp.server.server', logging.INFO),
    ('browser_use', logging.DEBUG),
]:
    _logger = logging.getLogger(logger_name)
    _logger.handlers = []
    _logger.addHandler(file_handler)
    _logger.setLevel(log_level)
    _logger.propagate = False

# モジュール用のロガー
logger = logging.getLogger(__name__)


async def run_task(*, task: str):
    """
    :9222 の Chrome でログインする。
    """
    logger.info(f"タスク開始: {task}")

    # Chrome が :9222 で起動しているか確認
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                'http://localhost:9222/json/version', timeout=5.0
            )
            if response.status_code != 200:
                error_msg = "❌ エラー: Chrome が :9222 で起動していません。launch-chrome.sh を実行してから再度お試しください。"
                logger.error(error_msg)
                return error_msg
    except httpx.ConnectError:
        error_msg = "❌ エラー: Chrome が :9222 で起動していません。launch-chrome.sh を実行してから再度お試しください。"
        logger.error(error_msg)
        return error_msg
    except httpx.TimeoutException:
        error_msg = "❌ エラー: Chrome への接続がタイムアウトしました。Chrome が正常に起動しているか確認してください。"
        logger.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"❌ エラー: Chrome の起動確認中に予期しないエラーが発生しました: {e}"
        logger.error(error_msg)
        return error_msg

    logger.info("✅ Chrome が :9222 で起動していることを確認しました。")

    # 既存の Chrome に接続
    browser_session = BrowserSession(cdp_url='http://localhost:9222')

    # Agent を作成
    agent = Agent(
        task=task,
        llm=ChatOpenAI(model="gpt-4.1-mini"),
        browser_session=browser_session,
    )

    try:
        result = await agent.run(max_steps=5)
        logger.info(
            f"タスク完了: {str(result)[:200]}..."
        )  # 最初の200文字のみログに記録
        return result
    except Exception as e:
        error_msg = f"❌ エラー: エージェント実行中にエラーが発生しました: {e}"
        logger.error(error_msg, exc_info=True)
        return error_msg


if __name__ == '__main__':
    import sys

    if not sys.stdin.isatty():
        # 標準入力からタスクを読み取る
        task = sys.stdin.read().strip()
        if not task:
            print("❌ エラー: 標準入力からタスクが取得できませんでした。")
            sys.exit(1)
    else:
        print("❌ エラー: タスクを標準入力から入力してください。")
        print("例: echo 'タスク内容' | python browser_bot.py")
        sys.exit(1)

    asyncio.run(run_task(task=task))
