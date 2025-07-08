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
import asyncio
import os
import platform
import socket
import subprocess
import sys
from typing import Annotated

import httpx

# テレメトリを無効化
os.environ['ANONYMIZED_TELEMETRY'] = 'false'

import fastmcp
from dotenv import load_dotenv
from fastmcp.utilities.types import Image
from pydantic import Field

from browser_bot import (
    get_full_screenshot,
    get_page_source,
    get_visible_screenshot,
    logger,
    run_script,
    run_task,
    setup_logger_for_mcp_server,
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
    description="""ローカルで起動している Chrome (:9222) に接続して、
browser_use ライブラリを用いてブラウザ操作を行うツールです。

このツールは、基本的には操作をするだけです。
結果の確認や、ページの状態を取得することには適していません。
ページの状態を確認するには、 get_page_source_code や
get_visible_screenshot、get_full_screenshot ツールを使用してください。

パラメーター:
    task_text (str):
        実行したいタスクの説明。 browser_use のタスクプロンプトです。
        例: "https://example.com を開いて、ログインボタンをクリックしてください"

    url (str | None):
        最初に開く URL。指定された場合、タスク実行前にこの URL に移動します。

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
    url: Annotated[
        str | None,
        Field(
            description=(
                "最初に開く URL。指定された場合、タスク実行前にこの URL に移動します。\n"
                "タスクの説明に URL が含まれている場合でも、この URL が優先されます。"
            ),
            examples=["https://example.com", "https://github.com", None],
        ),
    ] = None,
) -> str:
    """ブラウザ操作タスクを実行する"""
    if not task_text or not task_text.strip():
        error_msg = "❌ エラー: タスクの説明が空です。実行したい操作を指定してください。"
        logger.error(error_msg)
        return error_msg

    logger.info(
        f"MCP ツール実行開始 (max_steps={max_steps}, url={url}): {task_text[:100]}..."
    )

    try:
        result_text = await run_task(
            task=task_text, max_steps=max_steps, url=url
        )
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
    description="""Browser_bot (Chrome) の現在アクティブなタブまたは
指定された URL の表示されている箇所をスクリーンショットします。

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


# JavaScript 実行ツール
@server.tool(
    name="run_javascript_in_browser",
    description="""Browser_bot (Chrome) の現在アクティブなタブまたは指定された URL で JavaScript を実行します。

このツールは Browser_bot (Chrome) に Playwright を使用して接続し、指定された JavaScript コードを実行します。

URL が指定された場合:
- 指定された URL に移動してから JavaScript を実行
- ページの読み込みが完了してから実行

使用用途:
- 開発したページでの JavaScript 動作確認
- DOM 操作やイベント発火などの自動化
- ページ状態の動的な変更
- 複雑な操作の自動化（browser_use では困難な場合）

注意:
- 実行結果は返されません（void）
- エラーが発生した場合はログに記録されます
""",
)
async def run_javascript_in_browser(
    script: Annotated[
        str,
        Field(
            description=(
                "実行する JavaScript コード。\n"
                "ブラウザのコンソールで実行されるのと同じように動作します。\n"
                "\n"
                "例:\n"
                "- DOM 操作: document.getElementById('submit').click()\n"
                "- フォーム入力: document.querySelector('input[name=\"email\"]')."
                "value = 'test@example.com'\n"
                "- スクロール: window.scrollTo(0, document.body.scrollHeight)\n"
                "- イベント発火: document.querySelector('.button')."
                "dispatchEvent(new Event('click'))\n"
                "- 複数行の処理も可能（セミコロンで区切る）"
            ),
            min_length=1,
            max_length=10000,
            examples=[
                "document.getElementById('login-button').click()",
                "document.querySelector('input[type=\"email\"]').value = "
                "'user@example.com'; "
                "document.querySelector('input[type=\"password\"]').value = "
                "'password123'; document.querySelector('form').submit()",
                "Array.from(document.querySelectorAll('.item')).forEach(el => "
                "el.style.backgroundColor = 'yellow')",
                "window.scrollTo(0, 0); setTimeout(() => window.print(), 1000)",
            ],
        ),
    ],
    url: Annotated[
        str | None,
        Field(
            description=(
                "JavaScript を実行する URL。\n"
                "指定された場合、その URL に移動してから JavaScript を実行します。\n"
                "指定されない場合は、現在アクティブなページで実行します。"
            ),
            examples=["https://example.com", "https://github.com", None],
        ),
    ] = None,
) -> str:
    """指定された JavaScript をブラウザで実行する"""
    logger.info(f"JavaScript 実行ツール開始 (URL: {url})")

    try:
        # run_script を実行（戻り値なし）
        await run_script(script=script, url=url)

        success_msg = "✅ JavaScript の実行が完了しました"
        logger.info(success_msg)
        return success_msg

    except Exception as e:
        error_msg = f"❌ エラー: JavaScript 実行中に予期しないエラーが発生しました: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


# Chrome 起動ツール
@server.tool(
    name="launch_chrome_with_debug",
    description="""Chrome をデバッグポート 9222 で起動します。

このツールは、browser_bot が接続するための Chrome ブラウザを起動します。
既に起動している場合は、その旨を通知します。

機能:
- ポート 9222 の使用状況をチェック
- 既存の Chrome プロセスを検知
- 新規 Chrome の起動
- プラットフォーム対応 (macOS, Linux, Windows)

使用用途:
- browser_bot を使用する前の Chrome 起動
- 開発・テスト環境の準備
""",
)
async def launch_chrome_with_debug() -> str:
    """Chrome をデバッグポート 9222 で起動する"""
    logger.info("Chrome 起動ツール実行開始")

    # ポート 9222 が使用中かチェック
    def is_port_in_use(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('', port))
                return False
            except socket.error:
                return True

    if is_port_in_use(9222):
        # ポートが使用中の場合、Chrome が起動しているか確認
        try:

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "http://localhost:9222/json/version", timeout=2
                )
                if response.status_code == 200:
                    version_info = response.json()
                    browser_info = version_info.get('Browser', 'Unknown')
                    logger.info(f"Chrome は既に起動しています: {browser_info}")
                    return (
                        f"✅ Chrome は既に起動しています (ポート 9222)\n\n"
                        f"ブラウザ情報: {browser_info}\n\n"
                        "browser_bot ツールを使用できます。"
                    )
        except Exception:
            pass

        logger.warning(
            "ポート 9222 は使用中ですが、Chrome ではない可能性があります"
        )
        return "⚠️ ポート 9222 は既に使用されていますが、Chrome ではない可能性があります。\n\n既存のプロセスを確認してください。"

    # Chrome の実行パスを取得
    system = platform.system()
    chrome_paths = []

    if system == "Darwin":  # macOS
        chrome_paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            (
                "/Applications/Google Chrome Canary.app/Contents/MacOS/"
                "Google Chrome Canary"
            ),
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    elif system == "Linux":
        chrome_paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
        ]
    elif system == "Windows":
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Google\Chrome Beta\Application\chrome.exe",
            r"C:\Program Files\Google\Chrome Dev\Application\chrome.exe",
        ]

    # 実行可能な Chrome パスを探す
    chrome_executable = None
    for path in chrome_paths:
        if os.path.exists(path):
            chrome_executable = path
            break

    if not chrome_executable:
        error_msg = (
            f"❌ エラー: Chrome が見つかりません。Chrome をインストールしてください。\n\n検索したパス:\n"
            + "\n".join(chrome_paths)
        )
        logger.error(error_msg)
        return error_msg

    # Chrome 起動オプション
    user_data_dir = os.path.expanduser("~/.google-chrome-debug")
    chrome_args = [
        chrome_executable,
        "--remote-debugging-port=9222",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--disable-default-apps",
    ]

    try:
        # Chrome を起動
        logger.info(f"Chrome を起動しています: {chrome_executable}")
        subprocess.Popen(
            chrome_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

        await asyncio.sleep(2)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "http://localhost:9222/json/version", timeout=5
                )
                if response.status_code == 200:
                    version_info = response.json()
                    browser_info = version_info.get('Browser', 'Unknown')
                    success_msg = (
                        f"✅ Chrome を正常に起動しました (ポート 9222)\n\n"
                        f"ブラウザ情報: {browser_info}\n\n"
                        "browser_bot ツールを使用できます。"
                    )
                    logger.info(success_msg)
                    return success_msg
        except Exception as e:
            logger.warning(
                f"Chrome の起動確認でエラー: {e.__class__.__name__}: {e}"
            )

        # 起動したけど確認できない場合
        return (
            "✅ Chrome を起動しました (ポート 9222)\n\n"
            "起動確認はできませんでしたが、少し待ってから browser_bot ツールを試してください。"
        )

    except Exception as e:
        error_msg = f"❌ エラー: Chrome の起動に失敗しました: {e.__class__.__name__}: {e}"
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
        logger.error(
            f"MCP サーバーエラー: {e.__class__.__name__}: {e}", exc_info=True
        )
        raise


if __name__ == "__main__":
    main()
