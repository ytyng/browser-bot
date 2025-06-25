#!/usr/bin/env python3

import argparse
import asyncio
import logging
import os
import sys

# テレメトリを無効化
os.environ['ANONYMIZED_TELEMETRY'] = 'false'

import dotenv
import base64
import io

import httpx
from PIL import Image
from playwright.async_api import async_playwright
from browser_use import Agent, BrowserSession

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
logger.setLevel(logging.DEBUG)


def setup_logger_for_mcp_server():
    """
    MCPサーバー用にロガーを設定する
    標準出力にログを出さないようにする
    """

    logger.handlers = []  # 既存のハンドラーをクリア
    logger.addHandler(file_handler)

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


def get_llm():

    _llm_model_name = os.getenv('BROWSER_USE_LLM_MODEL', None)
    if _llm_model_name:
        if _llm_model_name.startswith('gemini'):
            # Google Gemini
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(
                model=_llm_model_name, temperature=0.0
            )

    # default: OpenAI
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=_llm_model_name or "gpt-4.1-mini",
        temperature=0.0,
    )


async def run_task(*, task: str, max_steps: int | None = None):
    """
    :9222 の Chrome でログインする。
    """
    logger.info(f"タスク開始: {task}")

    if max_steps is None:
        # 環境変数から max_steps を取得
        max_steps = int(os.getenv('BROWSER_USE_MAX_STEPS', 7))

    logger.debug(f"max_steps: {max_steps}")

    # Chrome が :9222 で起動しているか確認
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                'http://localhost:9222/json/version', timeout=5.0
            )
            if response.status_code != 200:
                error_msg = (
                    "❌ エラー: Chrome が :9222 で起動していません。"
                    "launch-chrome.sh を実行してから再度お試しください。"
                )
                logger.error(error_msg)
                return error_msg
    except httpx.ConnectError:
        error_msg = (
            "❌ エラー: Chrome が :9222 で起動していません。"
            "launch-chrome.sh を実行してから再度お試しください。"
        )
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
        llm=get_llm(),
        browser_session=browser_session,
    )

    try:
        result = await agent.run(max_steps=max_steps)
        logger.info(
            f"タスク完了 (max_steps={max_steps}): {str(result)[:200]}..."
        )  # 最初の200文字のみログに記録
        return result
    except Exception as e:
        error_msg = f"❌ エラー: エージェント実行中にエラーが発生しました: {e}"
        logger.error(error_msg, exc_info=True)
        return error_msg


async def _get_active_page(playwright_instance, *, url: str | None = None):
    """
    Chrome のアクティブなページを取得する共通処理

    Args:
        playwright_instance: Playwright のインスタンス
        url: 指定されたら遷移する

    Returns:
        tuple: (page, browser) または (None, None) とエラーメッセージ
    """
    if url and url.lower() in {'null', 'none', 'undefined', ''}:
        url = None

    # Chrome の CDP エンドポイントに接続
    browser = await playwright_instance.chromium.connect_over_cdp(
        'http://localhost:9222'
    )

    try:
        # 既存のコンテキストを取得
        contexts = browser.contexts
        if not contexts:
            error_msg = (
                "❌ エラー: Chrome にアクティブなコンテキストがありません"
            )
            logger.error(error_msg)
            await browser.close()
            return None, None, error_msg

        # 全コンテキストからページを収集
        all_pages = []
        for context in contexts:
            for page in context.pages:
                # ページが閉じられていないかチェック
                if not page.is_closed():
                    all_pages.append(page)

        if not all_pages:
            error_msg = "❌ エラー: Chrome にアクティブなページがありません"
            logger.error(error_msg)
            await browser.close()
            return None, None, error_msg

        # 最も最近アクティブになったページを特定
        active_page = await _find_most_recent_active_page(all_pages)

        if not active_page:
            # フォールバック: 最初の有効なページを使用
            active_page = all_pages[0]
            logger.info(
                "最新のアクティブページが特定できないため、最初のページを使用します"
            )

        logger.info(f"アクティブページを特定: {active_page.url}")

        # URL が指定されていれば遷移
        if url:
            logger.info(f"URL に遷移: {url}")
            await active_page.goto(url)
            await active_page.wait_for_load_state('networkidle')

        return active_page, browser, None

    except Exception as e:
        await browser.close()
        error_msg = (
            f"❌ エラー: アクティブページの取得中にエラーが発生しました: {e}"
        )
        logger.error(error_msg, exc_info=True)
        return None, None, error_msg


async def _find_most_recent_active_page(pages):
    """
    複数のページから最も最近アクティブになったページを特定する

    Args:
        pages: ページのリスト

    Returns:
        page: 最もアクティブなページ、または None
    """
    try:
        # ページの情報を収集
        page_info = []
        for page in pages:
            try:
                if page.is_closed():
                    continue

                # ページの基本情報を取得
                url = page.url
                title = (
                    await page.title() if not page.is_closed() else "Unknown"
                )

                # ページに JavaScript を実行して最終アクセス時刻を取得
                last_activity = await page.evaluate(
                    """
                    () => {
                        // document.lastModified または現在時刻を使用
                        return {
                            lastModified: document.lastModified,
                            timestamp: Date.now(),
                            hasFocus: document.hasFocus(),
                            visibilityState: document.visibilityState
                        };
                    }
                """
                )

                page_info.append(
                    {
                        'page': page,
                        'url': url,
                        'title': title,
                        'has_focus': last_activity.get('hasFocus', False),
                        'visibility_state': last_activity.get(
                            'visibilityState', 'hidden'
                        ),
                        'timestamp': last_activity.get('timestamp', 0),
                    }
                )

            except Exception as e:
                logger.debug(f"ページ情報取得エラー: {e}")
                continue

        if not page_info:
            return None

        # 優先順位でソート
        # 1. フォーカスがあるページ
        # 2. visible 状態のページ
        # 3. タイムスタンプが新しいページ
        page_info.sort(
            key=lambda x: (
                x['has_focus'],
                x['visibility_state'] == 'visible',
                x['timestamp'],
            ),
            reverse=True,
        )

        selected_page = page_info[0]
        logger.info(
            f"最もアクティブなページを選択: {selected_page['title']} ({selected_page['url']})"
        )
        logger.debug(
            f"選択理由 - フォーカス: {selected_page['has_focus']}, 表示状態: {selected_page['visibility_state']}"
        )

        return selected_page['page']

    except Exception as e:
        logger.error(f"アクティブページの特定中にエラー: {e}", exc_info=True)
        return None


def _resize_image_if_needed(
    image_bytes: bytes, max_size_bytes: int = 700000
) -> bytes:
    """
    画像サイズが制限を超える場合は縮小する
    Base64 エンコード後のサイズを考慮（約1.33倍）

    Args:
        image_bytes: 元の画像データ
        max_size_bytes: 最大サイズ（Base64 前）

    Returns:
        bytes: リサイズされた画像データ
    """
    # Base64 エンコード後のサイズを推定
    estimated_base64_size = len(image_bytes) * 1.33

    if estimated_base64_size <= max_size_bytes:
        return image_bytes

    # PIL で画像を開く
    img = Image.open(io.BytesIO(image_bytes))

    # 縮小率を計算
    scale_factor = (max_size_bytes / estimated_base64_size) ** 0.5
    new_width = int(img.width * scale_factor)
    new_height = int(img.height * scale_factor)

    logger.info(
        f"画像をリサイズ: {img.width}x{img.height} → {new_width}x{new_height}"
    )

    # リサイズ
    img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # バイトに変換
    output = io.BytesIO()
    img_resized.save(output, format='PNG', optimize=True)
    return output.getvalue()


async def get_page_source(*, url: str | None = None):
    """
    現在アクティブなタブのソースコードを取得する

    Args:
        url: 指定されたらその URL に移動してから取得

    Returns:
        dict: {
            'source': str,  # ページのソースコード
            'url': str,     # 現在のURL
            'title': str    # ページタイトル
        }
    """
    logger.info("ソースコード取得開始")

    async with async_playwright() as p:
        page, browser, error = await _get_active_page(p, url=url)
        if error:
            return {'error': error}

        try:
            # 現在の状態を取得
            current_url = page.url

            # ページが完全に読み込まれるまで待機
            await page.wait_for_load_state('domcontentloaded')

            # タイトルとソースコードを取得
            try:
                title = await page.title()
            except Exception:
                title = "Unknown"
                logger.warning("タイトル取得に失敗しました")

            source = await page.content()

            logger.info(f"ソースコード取得完了: {current_url}")

            return {'source': source, 'url': current_url, 'title': title}
        finally:
            await browser.close()


async def get_visible_screenshot(*, url: str | None = None):
    """
    現在アクティブなタブの表示されている箇所をスクリーンショットする

    Args:
        url: 指定されたらその URL に移動してから取得

    Returns:
        dict: {
            'screenshot': bytes,  # スクリーンショットの画像データ
            'url': str,          # 現在のURL
            'title': str         # ページタイトル
        }
    """
    logger.info("表示箇所のスクリーンショット取得開始")

    async with async_playwright() as p:
        page, browser, error = await _get_active_page(p, url=url)
        if error:
            return {'error': error}

        try:
            # 現在の状態を取得
            current_url = page.url

            # ページが完全に読み込まれるまで待機
            await page.wait_for_load_state('domcontentloaded')

            # タイトルを取得
            try:
                title = await page.title()
            except Exception:
                title = "Unknown"
                logger.warning("タイトル取得に失敗しました")

            # 表示箇所のスクリーンショット取得
            screenshot_bytes = await page.screenshot()

            # サイズ調整
            screenshot_bytes = _resize_image_if_needed(screenshot_bytes)

            logger.info(f"表示箇所のスクリーンショット取得完了: {current_url}")

            return {
                'screenshot': screenshot_bytes,
                'url': current_url,
                'title': title,
            }
        finally:
            await browser.close()


async def get_full_screenshot():
    """
    現在アクティブなタブの全領域をスクリーンショットする

    Returns:
        dict: {
            'screenshot': bytes,  # スクリーンショットの画像データ
            'url': str,          # 現在のURL
            'title': str         # ページタイトル
        }
    """
    logger.info("全領域のスクリーンショット取得開始")

    async with async_playwright() as p:
        page, browser, error = await _get_active_page(p, url=url)
        if error:
            return {'error': error}

        try:
            # 現在の状態を取得
            current_url = page.url

            # ページが完全に読み込まれるまで待機
            await page.wait_for_load_state('domcontentloaded')

            # タイトルを取得
            try:
                title = await page.title()
            except Exception:
                title = "Unknown"
                logger.warning("タイトル取得に失敗しました")

            # 全領域のスクリーンショット取得
            screenshot_bytes = await page.screenshot(full_page=True)

            # サイズ調整（全領域は特に大きくなりがちなので、より小さい制限を設定）
            screenshot_bytes = _resize_image_if_needed(
                screenshot_bytes, max_size_bytes=800000
            )

            logger.info(f"全領域のスクリーンショット取得完了: {current_url}")

            return {
                'screenshot': screenshot_bytes,
                'url': current_url,
                'title': title,
            }
        finally:
            await browser.close()


if __name__ == '__main__':
    dotenv.load_dotenv()

    parser = argparse.ArgumentParser(
        description="Run a browser automation task."
    )
    parser.add_argument(
        '--max-steps',
        type=int,
        help='Maximum number of steps for the agent to run.',
    )
    args = parser.parse_args()

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

    asyncio.run(run_task(task=task, max_steps=args.max_steps))
