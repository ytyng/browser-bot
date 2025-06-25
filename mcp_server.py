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
from typing import Annotated

# テレメトリを無効化
os.environ['ANONYMIZED_TELEMETRY'] = 'false'

import fastmcp
from fastmcp.utilities.types import Image
from dotenv import load_dotenv
from pydantic import Field

from browser_bot import (
    logger,
    run_task,
    setup_logger_for_mcp_server,
    get_page_source,
    get_visible_screenshot,
    get_full_screenshot,
)

setup_logger_for_mcp_server()

# .envファイルから環境変数を読み込む
load_dotenv()


# MCPサーバーの設定
server = fastmcp.FastMCP(
    name="browser_bot",
    instructions="""ブラウザ操作のための MCP サーバーです。

このサーバーは browser_use を使用して、ローカルで起動している Chrome (:9222) に接続します。

Chrome に対しての操作指示をする場合、このツールを使ってください。
また、 「brower bot を使って…」という指示も、このMCP サーバーのツールを使ってください。

ここのツールで使うブラウザは、ユーザーが手動で操作することができるので、
認証や複雑なマウス操作をユーザーにやってもらい、
文字入力やボタンクリックなど単調な作業をツールに任せることができます。

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
    name="browser_use_local_chrome",
    description="""ローカルで起動している Chrome (:9222) に接続して、browser_use ライブラリを用いてブラウザ操作を行うツールです。

このツールは、基本的には操作をするだけです。結果の確認や、ページの状態を取得することには適していません。
ページの状態を確認するには、 get_page_source_code や get_visible_screenshot、get_full_screenshot ツールを使用してください。

パラメーター:
    task_text (str):
        実行したいタスクの説明。 browser_use のタスクプロンプトです。
        例: "https://example.com を開いて、ログインボタンをクリックしてください"

戻り値:
    str: タスクの実行結果。成功時は結果の説明、失敗時はエラーメッセージ。

使用用途:
- 開発したウェブサイトを実際に操作しての動作確認
- ブラウザを使う定型処理の実行
""",
)
async def browser_use_local_chrome(
    task_text: Annotated[
        str,
        Field(
            description=(
                "実行したいブラウザ操作タスクの詳細な説明。日本語または英語で記述可能。"
                "具体的で明確な指示を含めてください。"
                "\n\n"
                "browser_use のタスクプロンプトとしてそのまま使われます。"
                "\n\n"
                "タスクの書き方のポイント:\n"
                "1. URL は完全な形式で記述 (例: https://example.com)\n"
                "2. クリックする要素は具体的に説明 (例: '送信'と書かれた青いボタン)\n"
                "3. 入力する内容は明確に指定 (例: メールアドレス欄に 'test@example.com' を入力)\n"
                "4. 複数の操作は箇条書きで順序立てて記述\n"
                "\n"
                "良い例:\n"
                "- 'https://www.google.com を開いて、検索ボックスに Python tutorial と"
                "入力し、検索ボタンをクリックしてください'\n"
                "- '現在のページで、ログインフォームのユーザー名欄に admin、"
                "パスワード欄に password123 を入力して、ログインボタンをクリックしてください'\n"
                "\n"
                "悪い例:\n"
                "- 'ログインして' (具体的な情報が不足)\n"
                "- 'ボタンをクリック' (どのボタンか不明確)"
            ),
            min_length=10,
            max_length=4000,
            examples=[
                (
                    "https://github.com を開いて、Search or jump to... と"
                    "書かれた検索ボックスに fastmcp と入力してください"
                ),
                (
                    "現在のページで、お問い合わせフォームの名前欄に '山田太郎'、"
                    "メールアドレス欄に 'yamada@example.com'、"
                    "メッセージ欄に 'テストメッセージです' と入力して、"
                    "送信ボタンをクリックしてください"
                ),
                (
                    "https://www.amazon.co.jp を開いて、"
                    "検索ボックスに 'Python プログラミング' と入力し、"
                    "検索を実行してください。"
                    "その後、最初の検索結果をクリックしてください"
                ),
            ],
        ),
    ],
    max_steps: Annotated[
        int,
        Field(
            description=(
                "ブラウザ操作の最大実行ステップ数。"
                "複雑なタスクほど多くのステップが必要になります。"
                "\n\n"
                "目安:\n"
                "- 簡単な操作（1つのページで完結）: 3-5ステップ\n"
                "- 中程度の操作（複数のページにわたる）: 5-10ステップ\n"
                "- 複雑な操作（検索、フォーム入力、複数画面）: 10-15ステップ\n"
                "\n"
                "注意: 多すぎると時間がかかり、少なすぎるとタスクが完了しない可能性があります。"
            ),
            ge=1,
            le=30,
            examples=[3, 7, 15],
        ),
    ] = 7,
) -> str:
    """ブラウザ操作タスクを実行する"""
    if not task_text or not task_text.strip():
        error_msg = "❌ エラー: タスクの説明が空です。実行したい操作を指定してください。"
        logger.error(error_msg)
        return error_msg

    logger.info(
        f"MCP ツール実行開始 (max_steps={max_steps}): {task_text[:100]}..."
    )

    try:
        result_text = await run_task(task=task_text, max_steps=max_steps)
        logger.info(f"MCP ツール実行完了: 成功")
        return str(result_text)
    except Exception as e:
        error_msg = f"❌ エラー: タスク実行中に予期しないエラーが発生しました: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


# ソースコード取得ツール
@server.tool(
    name="get_page_source_code",
    description="""Browser_bot (Chrome) の現在アクティブなタブ (または指定された URL のソースコード)を取得します。

このツールは Browser_bot (Chrome) の に Playwright を使用して接続し、以下の情報を取得します:
- ページのソースコード (HTML)
- 現在の URL
- ページタイトル

URL が指定された場合:
- 指定された URL に移動してからソースコードを取得
- 現在の URL と同じ場合はスーパーリロードを実行


使用用途:
- 開発したページの成果確認、不具合に対する調査
- 特にエラーメッセージを変換無く取得したい時
""",
)
async def get_page_source_code(
    url: Annotated[
        str | None,
        Field(
            description=(
                "取得する URL。指定された場合、その URL に移動してからソースコードを取得します。\n"
                "現在の URL と同じ場合、スーパーリロードが実行されます。\n"
                "指定されない場合は、現在のページのソースコードを取得します。"
            ),
            examples=["https://example.com", "https://github.com"],
        ),
    ] = None,
) -> str:
    """現在アクティブなタブまたは指定された URL のソースコードを取得する"""
    logger.info(f"ソースコード取得ツール実行開始 (URL: {url})")

    try:
        result = await get_page_source(url=url)

        if 'error' in result:
            logger.error(f"ソースコード取得エラー: {result['error']}")
            return result['error']

        # 結果を整形して返す
        response = f"""# 取得結果

## URL

{result['url']}

## タイトル

{result['title']}

## ソースコード

```html
{result['source']}
```
"""

        logger.info(f"ソースコード取得ツール実行完了: {result['url']}")
        return response

    except Exception as e:
        error_msg = f"❌ エラー: ソースコード取得中に予期しないエラーが発生しました: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


# 表示箇所のスクリーンショット取得ツール
@server.tool(
    name="get_visible_screenshot",
    description="""Browser_bot (Chrome) の現在アクティブなタブまたは指定された URL の表示されている箇所をスクリーンショットします。

このツールは Browser_bot (Chrome) に Playwright を使用して接続し、以下の情報を取得します:
- 現在表示されている領域のスクリーンショット (PNG 形式の画像データ)

URL が指定された場合:
- 指定された URL に移動してからスクリーンショットを取得
- 現在の URL と同じ場合はスーパーリロードを実行

注意: 画像サイズが大きい場合は自動的に縮小されます。

使用用途:
- 開発したページの成果確認、不具合に対する調査
- デザインタスク
""",
)
async def get_visible_screenshot_tool(
    url: Annotated[
        str | None,
        Field(
            description=(
                "取得する URL。指定された場合、その URL に移動してからスクリーンショットを取得します。\n"
                "現在の URL と同じ場合、スーパーリロードが実行されます。\n"
                "指定されない場合は、現在のページのスクリーンショットを取得します。"
            ),
            examples=["https://example.com", "https://github.com"],
        ),
    ] = None,
) -> Image:
    """現在表示されている箇所または指定された URL のスクリーンショットを取得する"""
    logger.info(f"表示箇所のスクリーンショット取得ツール実行開始 (URL: {url})")

    try:
        result = await get_visible_screenshot(url=url)

        if 'error' in result:
            logger.error(f"スクリーンショット取得エラー: {result['error']}")
            # エラーの場合はプレースホルダー画像を返す
            error_msg = f"Screenshot Error: {result['error']}"
            # 小さなエラー画像データを生成するか、エラーメッセージを含むプレースホルダーを返す
            # ここではとりあえず空のバイトデータでエラーレスポンスを作成
            return Image(data=error_msg.encode('utf-8'), format="txt")

        logger.info(
            f"表示箇所のスクリーンショット取得ツール実行完了: {result['url']}"
        )

        # FastMCP の Image オブジェクトで返す
        return Image(data=result['screenshot'], format="png")

    except Exception as e:
        error_msg = f"❌ エラー: スクリーンショット取得中に予期しないエラーが発生しました: {str(e)}"
        logger.error(error_msg, exc_info=True)
        # エラーの場合もプレースホルダーを返す
        return Image(data=error_msg.encode('utf-8'), format="txt")


# 全領域のスクリーンショット取得ツール
@server.tool(
    name="get_full_screenshot",
    description="""Browser_bot (Chrome) の現在アクティブなタブまたは指定された URL の全領域をスクリーンショットします。

このツールは Browser_bot (Chrome) にPlaywright を使用して接続し、以下の情報を取得します:
- ページ全体のスクリーンショット (PNG 形式の画像データ)

URL が指定された場合:
- 指定された URL に移動してからスクリーンショットを取得
- 現在の URL と同じ場合はスーパーリロードを実行

注意:
- 長いページの場合、スクロールして全体を撮影します
- 画像サイズが大きい場合は自動的に縮小されます

使用用途:
- 開発したページの成果確認、不具合に対する調査
- デザインタスク
""",
)
async def get_full_screenshot_tool(
    url: Annotated[
        str | None,
        Field(
            description=(
                "取得する URL。指定された場合、その URL に移動してからスクリーンショットを取得します。\n"
                "現在の URL と同じ場合、スーパーリロードが実行されます。\n"
                "指定されない場合は、現在のページのスクリーンショットを取得します。"
            ),
            examples=["https://example.com", "https://github.com"],
        ),
    ] = None,
) -> Image:
    """ページ全体または指定された URL のスクリーンショットを取得する"""
    logger.info(f"全領域のスクリーンショット取得ツール実行開始 (URL: {url})")

    try:
        result = await get_full_screenshot(url=url)

        if 'error' in result:
            logger.error(f"スクリーンショット取得エラー: {result['error']}")
            # エラーの場合はプレースホルダー画像を返す
            error_msg = f"Screenshot Error: {result['error']}"
            return Image(data=error_msg.encode('utf-8'), format="txt")

        logger.info(
            f"全領域のスクリーンショット取得ツール実行完了: {result['url']}"
        )

        # FastMCP の Image オブジェクトで返す
        return Image(data=result['screenshot'], format="png")

    except Exception as e:
        error_msg = f"❌ エラー: スクリーンショット取得中に予期しないエラーが発生しました: {str(e)}"
        logger.error(error_msg, exc_info=True)
        # エラーの場合もプレースホルダーを返す
        return Image(data=error_msg.encode('utf-8'), format="txt")


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
