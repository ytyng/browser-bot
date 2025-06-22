#!/usr/bin/env python3

""" """
import asyncio
import os
from pathlib import Path
import httpx
from dotenv import load_dotenv
from browser_use import Agent, BrowserSession
from langchain_openai import ChatOpenAI


async def run_task(*, task: str):
    """
    :9222 の Chrome でログインする。
    """

    # Chrome が :9222 で起動しているか確認
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                'http://localhost:9222/json/version', timeout=5.0
            )
            if response.status_code != 200:
                print(
                    "❌ エラー: Chrome が :9222 で起動していません。launch-chrome.sh を実行してから再度お試しください。"
                )
                return
    except httpx.ConnectError:
        print(
            "❌ エラー: Chrome が :9222 で起動していません。launch-chrome.sh を実行してから再度お試しください。"
        )
        return
    except httpx.TimeoutException:
        print(
            "❌ エラー: Chrome への接続がタイムアウトしました。Chrome が正常に起動しているか確認してください。"
        )
        return
    except Exception as e:
        print(
            f"❌ エラー: Chrome の起動確認中に予期しないエラーが発生しました: {e}"
        )
        return

    print("✅ Chrome が :9222 で起動していることを確認しました。")

    # 既存の Chrome に接続
    browser_session = BrowserSession(cdp_url='http://localhost:9222')

    # Agent を作成
    agent = Agent(
        task=task,
        llm=ChatOpenAI(model="gpt-4.1-mini"),
        browser_session=browser_session,
    )
    result = await agent.run(max_steps=5)
    print(result)


test_task = '''
* https://www.mangazenkan.com を開いてください。

* 「マンガを検索」と書かれている、検索欄をクリックしてください。

* ポップアップされたダイアログの「漫画を検索」と書かれている検索欄に、「スラムダンク」と入力して、Enter キーを押してください。
'''


if __name__ == '__main__':
    asyncio.run(run_task(task=test_task))
