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
import base64
import json
import os
import platform
import socket
import subprocess
import sys
from typing import Annotated

import httpx

from logging_config import log_file, logger

# テレメトリを無効化
os.environ['ANONYMIZED_TELEMETRY'] = 'false'

import fastmcp
from dotenv import load_dotenv
from fastmcp.utilities.types import Image
from pydantic import Field

from browser_bot import (
    get_current_url,
    get_full_screenshot,
    get_page_source,
    get_visible_screenshot,
    request,
    run_script,
    run_task,
    super_reload,
)

# .envファイルから環境変数を読み込む
load_dotenv()

# Chrome 接続先の設定 (デフォルト: http://localhost:9222)
CHROME_DEBUG_URL = os.getenv("CHROME_DEBUG_URL", "http://localhost:9222")
CHROME_DEBUG_HOST = (
    CHROME_DEBUG_URL.replace("http://", "")
    .replace("https://", "")
    .split(":")[0]
)
CHROME_DEBUG_PORT = int(
    CHROME_DEBUG_URL.replace("http://", "")
    .replace("https://", "")
    .split(":")[1]
    if ":" in CHROME_DEBUG_URL
    else "9222"
)

# リモートブラウザ使用フラグ
USE_REMOTE_BROWSER = os.getenv("USE_REMOTE_BROWSER", "false").lower() == "true"

# Selenium Grid URL (リモートブラウザ使用時)
SELENIUM_REMOTE_URL = os.getenv(
    "SELENIUM_REMOTE_URL", "http://selenium-grid.cyberneura.com:31444"
)

# MCPサーバーの設定
server = fastmcp.FastMCP(
    name="browser_bot",
    instructions=r"""ブラウザ操作のための MCP サーバーです。

このサーバーは browser_use を使用して、ローカルで起動している Chrome (:9222) に接続します。

Chrome に対しての操作指示をする場合、このツールを使ってください。
また、 「brower bot を使って…」という指示も、このMCP サーバーのツールを使ってください。

ここのツールで使うブラウザは、ユーザーが手動で操作することができるので、
認証や複雑なマウス操作をユーザーにやってもらい、
文字入力やボタンクリックなど単調な作業をツールに任せることができます。

# 使用例
- Web サイトの自動操作
- フォームの自動入力
- 情報の自動収集
- UI テストの自動化

# 注意事項
- Chrome が --remote-debugging-port=9222 で起動している必要があります
- launch-chrome.sh スクリプトを使用して Chrome を起動してください

# 補足
ログは {log_file} に保存されます。必要に応じて確認してください。

ログを、 [browser-console] で grep すると、ブラウザのコンソールログに限定して取得できます。

## 例
```
tail -f {log_file} | grep '\[browser-console\]'
```

# 長いタスクを実行する場合 (Python スクリプトを動かす)
MCPツールではなく、CLI の browser_bot のインターフェイスがあります。

```shell
echo "<long-python-script>" | browser-bot --python-script  --url "https://example.com/" --max-steps 10
```
といった形で実行できます。

## python スクリプト例
```python
await asyncio.sleep(1)
await page.click('.header .search-form span.header-search-input')
await page.fill(
    '#search-modal-input',
    'ハイキュー',
)

await asyncio.sleep(1)
await page.click('button[data-annotate=\"search-submit-button\"]')
```

詳細は `browser-bot --help` コマンドを参照してください。

""",
)


# ツールを登録
@server.tool(
    name="browser_use_local_chrome",
    description="""Chrome に接続してブラウザ操作を行うツールです。
ローカル Chrome または リモート Selenium Grid に対応しています。

このツールは、基本的には操作をするだけです。
結果の確認や、ページの状態を取得することには適していません。
ページの状態を確認するには、 get_page_source_code や
get_visible_screenshot、get_full_screenshot ツールを使用してください。

# パラメーター
task_text (str):
    実行したいタスクの説明。 browser_use のタスクプロンプトです。
    例: "https://example.com を開いて、ログインボタンをクリックしてください"

url (str | None):
    最初に開く URL。指定された場合、タスク実行前にこの URL に移動します。

# 戻り値
str: タスクの実行結果。成功時は結果の説明、失敗時はエラーメッセージ。

# 使用用途
- 開発したウェブサイトを実際に操作しての動作確認
- ブラウザを使う定型処理の実行

# 注意事項
比較的不安定なので、非推奨です。
可能な限り、 run_javascript_in_browser ツールを使用してください。
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

現在の URL とページタイトルも取得します。

ソースコードはユーザーのホームディレクトリの Downloads フォルダに HTML 形式で保存します。
保存したファイルパスを含むレスポンスを JSON 形式で返します。
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

        logger.info(f"ソースコード取得ツール実行完了: {result['url']}")

        # JSON レスポンスを構築
        response = {
            'file_path': result['file_path'],
            'url': result['url'],
            'title': result['title'],
        }

        return json.dumps(response, ensure_ascii=False, indent=2)

    except Exception as e:
        error_msg = f"❌ エラー: ソースコード取得中に予期しないエラーが発生しました: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


# 表示箇所のスクリーンショット取得ツール
@server.tool(
    name="get_visible_screenshot",
    description="""Browser_bot (Chrome) の現在アクティブなタブまたは
指定された URL の表示されている箇所のスクリーンショットを取得し、
ユーザーのホームディレクトリの Downloads フォルダに PNG 形式で保存します。
保存したファイルパスを含むレスポンスJSON 形式でを返します。
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
    page_y_offset_as_viewport_height: Annotated[
        float,
        Field(
            description=(
                "ビューポートの高さを基準にしたスクロール量の倍率。\n"
                "0.0: スクロールしない（デフォルト）\n"
                "1.0: 1ページ分下にスクロール\n"
                "2.0: 2ページ分下にスクロール\n"
                "例: 0.5 を指定すると半ページ分下にスクロールしてスクリーンショットを取得"
            ),
            ge=0.0,
            le=10.0,
            examples=[0.0, 1.0, 0.5, 2.0],
        ),
    ] = 0.0,
    # include_image_binary: Annotated[
    #     bool,
    #     Field(
    #         description=(
    #             "true を指定したら、画像バイナリを返答に含める。\n"
    #             "false (デフォルト) の場合、ファイルパスのみを返す。"
    #             "true の場合、レスポンスのコンテキストサイズを大きく使ってしまい、"
    #             "正常にレスポンスが受け取れない場合があるので、"
    #             "通常は false(デフォルト) のまま使ってください。"
    #             "作成後のスクリーンショットにアクセスする場合、"
    #             "レスポンスのファイルパスを操作してください。"
    #         ),
    #         examples=[False, True],
    #     ),
    # ] = False,
) -> str:
    """現在表示されている箇所または指定された URL のスクリーンショットを取得する。JSON を返します。"""
    logger.info(
        f"表示箇所のスクリーンショット取得ツール実行開始 "
        f"(URL: {url}, スクロール倍率: {page_y_offset_as_viewport_height})"
    )

    try:
        result = await get_visible_screenshot(
            url=url,
            page_y_offset_as_viewport_height=page_y_offset_as_viewport_height,
            include_image_binary=False,
        )

        if 'error' in result:
            logger.error(f"スクリーンショット取得エラー: {result['error']}")
            return result['error']

        logger.info(
            f"表示箇所のスクリーンショット取得ツール実行完了: {result['url']}"
        )

        # JSON レスポンスを構築
        response = {
            'file_path': result['file_path'],
            'url': result['url'],
            'title': result['title'],
        }

        # include_image_binary が True の場合は画像バイナリを base64 エンコードして含める
        # if include_image_binary:
        #     response['image_binary_base64'] = base64.b64encode(
        #         result['screenshot']
        #     ).decode('utf-8')

        return json.dumps(response, ensure_ascii=False, indent=2)

    except Exception as e:
        error_msg = f"❌ エラー: スクリーンショット取得中に予期しないエラーが発生しました: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


# 全領域のスクリーンショット取得ツール
@server.tool(
    name="get_full_screenshot",
    description="""Browser_bot (Chrome) の現在アクティブなタブまたは指定された URL
の全領域をスクリーンショットを、ユーザーのホームディレクトリの Downloads フォルダに PNG 形式で保存します。
保存したファイルパスを含むレスポンスJSON 形式でを返します。
""",
)
async def get_full_screenshot_tool(
    url: Annotated[
        str | None,
        Field(
            description=(
                "取得する URL。指定された場合、その URL に移動してからスクリーンショットを取得します。\n"
                "現在の URL と同じ場合、スーパーリロードが実行されます。\n"
                "指定されない場合は、現在のページのスクリーンショットを取得します。\n"
                "保存したファイルパスを含むレスポンスJSON 形式でを返します。"
            ),
            examples=["https://example.com", "https://github.com"],
        ),
    ] = None,
) -> str:
    """ページ全体または指定された URL のスクリーンショットを取得する"""
    logger.info(f"全領域のスクリーンショット取得ツール実行開始 (URL: {url})")

    try:
        result = await get_full_screenshot(url=url, include_image_binary=False)

        if 'error' in result:
            logger.error(f"スクリーンショット取得エラー: {result['error']}")
            return result['error']

        logger.info(
            f"全領域のスクリーンショット取得ツール実行完了: {result['url']}"
        )

        # JSON レスポンスを構築
        response = {
            'file_path': result['file_path'],
            'url': result['url'],
            'title': result['title'],
        }

        # include_image_binary が True の場合は画像バイナリを base64 エンコードして含める
        # if include_image_binary:
        #     response['image_binary_base64'] = base64.b64encode(
        #         result['screenshot']
        #     ).decode('utf-8')

        return json.dumps(response, ensure_ascii=False, indent=2)

    except Exception as e:
        error_msg = f"❌ エラー: スクリーンショット取得中に予期しないエラーが発生しました: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


# JavaScript 実行ツール
@server.tool(
    name="run_javascript_in_browser",
    description="""Browser_bot (Chrome) の現在アクティブなタブまたは指定された URL で JavaScript を実行します。

このツールは Browser_bot (Chrome) に Playwright を使用して接続し、指定された JavaScript コードを実行します。

# 実行方法
- 渡された JavaScript コードは自動的に async 即時関数 (async () => { ... })() でラップされて実行されます
- そのため、await を使用した非同期処理も記述できます
- return 文を使用すると、実行結果を取得することができます

# パラメーター `url` が指定された場合
- 指定された URL に移動してから JavaScript を実行
- ページの読み込みが完了してから実行

# 使用用途
- 開発したページでの JavaScript 動作確認
- DOM 操作やイベント発火などの自動化
- ページ状態の動的な変更
- 複雑な操作の自動化（browser_use では困難な場合）

# 注意
- エラーが発生した場合は、ローカルコンピューターの /tmp/browser-bot.log に記録されます。

# 戻り値
正常終了した場合は、 {
    "message": "✅ JavaScript の実行が完了しました",
    "result": 実行結果
}
が返されます。
""",
)
async def run_javascript_in_browser(
    script: Annotated[
        str,
        Field(
            description=(
                "実行する JavaScript コード。\n"
                "ブラウザのコンソールで実行されるのと同じように動作します。\n"
                "return 文を書くと、結果を取得できます。\n"
                "内容は、`(async () => { ... })()` でラップされます。\n"
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
                "window.scrollTo(0, 0); "
                "setTimeout(() => window.print(), 1000)",
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
        result = await run_script(script=script, url=url)

        success_msg = "✅ JavaScript の実行が完了しました"
        logger.info(f'{success_msg}: {result=}')
        return json.dumps(
            {"message": success_msg, "result": result},
            ensure_ascii=False,
            indent=2,
        )

    except Exception as e:
        error_msg = f"❌ エラー: JavaScript 実行中にエラーが発生しました: {e.__class__} {e}"
        logger.error(error_msg, exc_info=True)
        return error_msg


# 現在の URL 取得ツール
@server.tool(
    name="get_current_url",
    description="""Browser_bot (Chrome) の現在アクティブなタブの URL を取得します。

このツールは Browser_bot (Chrome) に Playwright を使用して接続し、以下の情報を取得します:
- 現在の URL
- ページタイトル
""",
)
async def get_current_url_tool() -> str:
    """現在アクティブなタブの URL を取得する"""
    logger.info("現在の URL 取得ツール実行開始")

    try:
        result = await get_current_url()

        if 'error' in result:
            logger.error(f"URL 取得エラー: {result['error']}")
            return result['error']

        # 結果を整形して返す
        response = f"""# 現在のページ情報

## URL

{result['url']}

## タイトル

{result['title']}
"""

        logger.info(f"現在の URL 取得ツール実行完了: {result['url']}")
        return response

    except Exception as e:
        error_msg = f"❌ エラー: URL 取得中にエラーが発生しました: {e.__class__.__name__}: {e}"
        logger.error(error_msg, exc_info=True)
        return error_msg


# スーパーリロードツール
@server.tool(
    name="super_reload",
    description="""Browser_bot (Chrome) の現在アクティブなタブでスーパーリロード (キャッシュを無視してリロード) を実行します。
""",
)
async def super_reload_tool(
    url: Annotated[
        str | None,
        Field(
            description=(
                "スーパーリロードする URL。指定された場合、その URL に移動してからスーパーリロードします。\n"
                "指定されない場合は、現在のページでスーパーリロードを実行します。"
            ),
            examples=["https://example.com", "https://github.com"],
        ),
    ] = None,
    mode: Annotated[
        str,
        Field(
            description=(
                "スーパーリロードのモード。通常、指定する必要は無し。\n"
                "cdp: Chrome DevTools Protocol を使用してスーパーリロード(default)、\n"
                "javascript: JavaScript を使用してスーパーリロード。\n"
                "keyboard: キーボードショートカット (Ctrl+F5) を使用してスーパーリロード。\n"
            ),
            examples=["cdp", "javascript", "keyboard"],
        ),
    ] = "cdp",
) -> str:
    """現在アクティブなタブまたは指定された URL でスーパーリロードを実行する"""
    logger.info(f"スーパーリロードツール実行開始 (URL: {url})")

    try:
        result = await super_reload(url=url, mode=mode)

        if 'error' in result:
            logger.error(f"スーパーリロードエラー: {result['error']}")
            return result['error']

        # 結果を整形して返す
        response = f"""# スーパーリロード完了

## URL

{result['url']}

## タイトル

{result['title']}

✅ キャッシュを無視してページを再読み込みしました。
"""

        logger.info(f"スーパーリロードツール実行完了: {result['url']}")
        return response

    except Exception as e:
        error_msg = f"❌ エラー: スーパーリロード中にエラーが発生しました: {e.__class__.__name__}: {e}"
        logger.error(error_msg, exc_info=True)
        return error_msg


# Chrome 起動ツール
@server.tool(
    name="launch_chrome_with_debug",
    description="""Chrome をデバッグポート 9222 で起動します（ゲストモード/通常モード選択可能）。
既に起動している場合は、その旨を通知します。
""",
)
async def launch_chrome_with_debug(
    as_guest: Annotated[
        bool,
        Field(
            description=(
                "Chrome をゲストモードで起動するかどうか。\n"
                "True: ゲストモードで起動（プライバシー保護、クリーンな環境）\n"
                "False: 通常モードで起動（既存のプロファイルやデータを使用）"
            ),
            examples=[True, False],
        ),
    ] = True,
) -> str:
    """Chrome をデバッグポートで起動する（リモートブラウザ使用時はスキップ）"""
    mode_text = "ゲストモード" if as_guest else "通常モード"

    if USE_REMOTE_BROWSER:
        logger.info(
            f"リモートブラウザ使用中 ({SELENIUM_REMOTE_URL}) - Chrome 起動をスキップ"
        )
        return (
            f"✅ リモートブラウザを使用中です ({SELENIUM_REMOTE_URL})\n\n"
            "browser_bot ツールを使用できます。"
        )

    logger.info(
        f"Chrome {mode_text}起動ツール実行開始 (URL: {CHROME_DEBUG_URL})"
    )

    # ローカルブラウザの場合のみポート確認
    # ポートが使用中かチェック
    def is_port_in_use(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('', port))
                return False
            except socket.error:
                return True

    if is_port_in_use(CHROME_DEBUG_PORT):
        # ポートが使用中の場合、Chrome が起動しているか確認
        message_to_append = ""
        try:

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{CHROME_DEBUG_URL}/json/version", timeout=2
                )
                if response.status_code == 200:
                    version_info = response.json()
                    browser_info = version_info.get('Browser', 'Unknown')
                    logger.info(f"Chrome は既に起動しています: {browser_info}")
                    return (
                        f"✅ Chrome は既に起動しています ({CHROME_DEBUG_URL})\n\n"
                        f"ブラウザ情報: {browser_info}\n\n"
                        "browser_bot ツールを使用できます。"
                    )
        except Exception as e:
            message_to_append = f" (エラー: {e.__class__.__name__}: {e})"

        logger.warning(
            f"ポート {CHROME_DEBUG_PORT} は使用中ですが、Chrome ではない"
            f"可能性があります{message_to_append}"
        )
        return (
            f"⚠️ ポート {CHROME_DEBUG_PORT} は既に使用されていますが、Chrome ではない可能性があります。"
            f"\n\n既存のプロセスを確認してください。{message_to_append}"
        )

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
    chrome_args = [
        chrome_executable,
        f"--remote-debugging-port={CHROME_DEBUG_PORT}",
        "--no-first-run",
        "--disable-default-apps",
    ]

    if as_guest:
        # ゲストモードの場合
        chrome_args.append("--guest")
    else:
        # 通常モードの場合
        user_data_dir = os.path.expanduser("~/.google-chrome-debug")
        chrome_args.append(f"--user-data-dir={user_data_dir}")

    try:
        # Chrome を起動
        logger.info(
            f"Chrome を{mode_text}で起動しています: {chrome_executable}"
        )
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
                        f"✅ Chrome を{mode_text}で正常に起動しました (ポート 9222)\n\n"
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
            f"✅ Chrome を{mode_text}で起動しました (ポート 9222)\n\n"
            "起動確認はできませんでしたが、少し待ってから browser_bot ツールを試してください。"
        )

    except Exception as e:
        error_msg = f"❌ エラー: Chrome の起動に失敗しました: {e.__class__.__name__}: {e}"
        logger.error(error_msg, exc_info=True)
        return error_msg


@server.tool(
    name="http_request",
    description="""Browser_bot (Chrome) の現在アクティブなタブまたは指定された URL で
    HTTP リクエストを行い、結果をJSONで返します。
認証が必要な http リソースを取得できます。

# 戻り値
```json
{
    "status": HTTPステータスコード,
    "headers": レスポンスヘッダー,
    "body": レスポンス本文。バイナリデータなら base64 エンコードして返す,
}
```

""",
)
async def http_request_tool(
    url: Annotated[
        str,
        Field(
            description="リクエスト先の URL",
            examples=[
                "https://example.com",
                "https://jsonplaceholder.typicode.com/users/1/todos",
            ],
        ),
    ],
    method: Annotated[
        str,
        Field(
            description=(
                "HTTP メソッド ('get', 'post', 'put', 'delete', "
                "'patch', 'head', 'options')"
            ),
            examples=["get", "post", "put", "delete"],
        ),
    ] = "get",
    preload_url: Annotated[
        str | None,
        Field(
            description="指定されたらその URL に移動してからリクエストを送信",
            default=None,
            examples=["https://example.com/login", None],
        ),
    ] = None,
    data: Annotated[
        str | None,
        Field(
            description="POST ボディなどのデータ (JSON文字列またはテキスト)",
            default=None,
            examples=[
                '{"name": "test", "email": "test@example.com"}',
                "key=value&param=data",
            ],
        ),
    ] = None,
    headers: Annotated[
        dict[str, str] | None,
        Field(
            description="HTTP ヘッダー",
            default=None,
            examples=[
                {"Content-Type": "application/json"},
                {"Authorization": "Bearer token123"},
            ],
        ),
    ] = None,
) -> str:
    """Browser_bot のブラウザセッションを使って HTTP リクエストを送信する"""
    logger.info(f"HTTP リクエストツール実行開始: {method.upper()} {url}")
    try:
        # kwargs を構築
        kwargs = {}
        if data is not None:
            kwargs["data"] = data
        if headers is not None:
            kwargs["headers"] = headers

        response_data = await request(
            method=method, url=url, preload_url=preload_url, **kwargs
        )

        # レスポンス本文をテキストとして処理
        response_body = response_data['body']
        content_type = response_data['headers'].get("content-type", "")

        # レスポンスが文字列っぽければデコードを試みる
        # そうでなければ、バイナリデータなので base64 エンコードして返す
        if "text" in content_type or "json" in content_type:
            response_text = response_body.decode('utf-8', errors='replace')
        else:
            response_text = base64.b64encode(response_body).decode('utf-8')

        result = {
            "status": response_data['status'],
            "headers": response_data['headers'],
            "body": response_text,
        }

        logger.info(
            f"HTTP リクエストツール実行完了: {method.upper()} {url} -> "
            f"{response_data['status']}"
        )

        # JSON として結果を返す
        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        error_msg = (
            f"❌ エラー: HTTP リクエスト中にエラーが発生しました: "
            f"{e.__class__.__name__}: {e}"
        )
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
