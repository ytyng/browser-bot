#!/usr/bin/env python3
"""
browser_bot.py の関数を直接テストするスクリプト
"""
import asyncio

import dotenv

from browser_bot import get_current_url, super_reload

# .env ファイルを読み込み
dotenv.load_dotenv()


async def main():
    print("=== 直接関数テスト ===")

    print("\n1. get_current_url() をテスト:")
    try:
        result = await get_current_url()
        print(f"結果: {result}")
    except Exception as e:
        print(f"エラー: {e.__class__.__name__}: {e}")

    print("\n2. super_reload() をテスト:")
    try:
        result = await super_reload()
        print(f"結果: {result}")
    except Exception as e:
        print(f"エラー: {e.__class__.__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
