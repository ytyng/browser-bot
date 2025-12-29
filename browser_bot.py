#!/usr/bin/env python3

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime

from logging_config import broser_console_logger, logger

# テレメトリを無効化
os.environ['ANONYMIZED_TELEMETRY'] = 'false'

import io

import dotenv
import httpx
from browser_use import Agent, BrowserSession
from PIL import Image
from playwright._impl._errors import TimeoutError as PlaywrightTimeoutError
from playwright._impl._fetch import APIResponse
from playwright.async_api import async_playwright

# 環境変数を読み込む
dotenv.load_dotenv()

# Chrome 接続先の設定 (デフォルト: http://localhost:9222)
CHROME_DEBUG_URL = os.getenv("CHROME_DEBUG_URL", "http://localhost:9222")

# リモートブラウザ使用フラグ
BROWSER_BOT_USE_REMOTE = os.getenv(
    "BROWSER_BOT_USE_REMOTE", "false"
).lower() in {"true", "1", "yes"}

# Selenium Grid URL (リモートブラウザ使用時)
SELENIUM_REMOTE_URL = os.getenv(
    "SELENIUM_REMOTE_URL", "http://selenium-grid.cyberneura.com:31444"
)


class BrowserBotError(Exception):
    pass


class BrowserBotTaskAbortedError(BrowserBotError):
    """タスクが中断された場合に raise する例外"""

    pass


class BrowserBotTaskFailedError(BrowserBotError):
    """タスクが失敗した場合に raise する例外"""

    pass


class BrowserRuntimeError(BrowserBotError):
    """Chrome が起動していない場合に raise する例外"""

    pass


async def _page_wait_for_load_state(
    page, state='domcontentloaded', timeout=7000
):
    """
    ページのロード状態を段階的にフォールバックしながら待機する共通関数

    Args:
        page: Playwright の Page オブジェクト
        state: 待機するロード状態（'networkidle', 'domcontentloaded', 'load'）
        timeout: タイムアウト時間（ミリ秒）

    Returns:
        str: 実際に使用されたロード状態
    """
    try:
        await page.wait_for_load_state(state, timeout=timeout)
        logger.debug(f"ロード状態 '{state}' で完了")
        return state
    except PlaywrightTimeoutError as e:
        logger.warning(f"ロード状態 '{state}' の待機がタイムアウト: {e}")

        # networkidle に失敗した場合は domcontentloaded を試行
        if state == 'networkidle':
            try:
                await page.wait_for_load_state(
                    'domcontentloaded', timeout=5000
                )
                logger.debug("DOM読み込み完了状態で続行")
                return 'domcontentloaded'
            except PlaywrightTimeoutError as e2:
                logger.warning(f"DOM読み込み待機もタイムアウト: {e2}")
                logger.debug("ロード状態の待機をスキップして続行")
                return 'skipped'

        # その他の状態に失敗した場合はスキップ
        logger.debug(f"ロード状態 '{state}' の待機をスキップして続行")
        return 'skipped'


async def _check_chrome_running():
    """
    Chrome が起動しているかを確認する共通処理

    Returns:
        str | None: エラーメッセージ、または None（正常時）
    """
    if BROWSER_BOT_USE_REMOTE:
        # リモートブラウザ使用時はチェックしない
        logger.debug(
            f'Using remote browser. SELENIUM_REMOTE_URL={SELENIUM_REMOTE_URL}'
        )
        return

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f'{CHROME_DEBUG_URL}/json/version', timeout=5.0
            )
            if response.status_code != 200:
                error_msg = (
                    f"❌ エラー: Chrome が {CHROME_DEBUG_URL} で起動していません。"
                    "Chrome をデバッグポートで起動してから再度お試しください。"
                )
                logger.error(error_msg)
                raise BrowserRuntimeError(error_msg)
    except httpx.ConnectError:
        error_msg = (
            f"❌ エラー: Chrome が {CHROME_DEBUG_URL} で起動していません。"
            "Chrome をデバッグポートで起動してから再度お試しください。"
        )
        logger.error(error_msg)
        raise BrowserRuntimeError(error_msg)
    except httpx.TimeoutException:
        error_msg = "❌ エラー: Chrome への接続がタイムアウトしました。Chrome が正常に起動しているか確認してください。"
        logger.error(error_msg)
        raise BrowserRuntimeError(error_msg)
    except Exception as e:
        error_msg = (
            f"❌ エラー: Chrome の起動確認中に予期しないエラーが発生しました: "
            f"{e.__class__.__name__}: {e}"
        )
        logger.error(error_msg)
        raise BrowserRuntimeError(error_msg)

    logger.info(
        f"✅ Chrome が {CHROME_DEBUG_URL} で起動していることを確認しました。"
    )


async def _get_browser_connection(playwright_instance):
    """
    リモートブラウザかローカルブラウザかに応じてブラウザ接続を取得する

    Args:
        playwright_instance: Playwright インスタンス

    Returns:
        Browser: 接続されたブラウザインスタンス
    """
    if BROWSER_BOT_USE_REMOTE:
        from selenium_remote import get_cdp_url_from_selenium_grid

        logger.info(f"リモートブラウザに接続: {SELENIUM_REMOTE_URL}")

        # Selenium Grid から CDP URL を取得
        cdp_url = await get_cdp_url_from_selenium_grid(SELENIUM_REMOTE_URL)
        # リモートブラウザに接続（CDP URL 使用）
        browser = await playwright_instance.chromium.connect_over_cdp(cdp_url)
        return browser
    else:
        # Chrome が起動しているか確認
        await _check_chrome_running()

        # ローカル Chrome の CDP エンドポイントに接続
        browser = await playwright_instance.chromium.connect_over_cdp(
            CHROME_DEBUG_URL
        )
        return browser


# LLM モデルを取得する関数
def get_llm():

    _llm_model_name = os.getenv('BROWSER_USE_LLM_MODEL', None)
    if _llm_model_name:
        if _llm_model_name.startswith('gemini'):
            # Google Gemini
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(
                model=_llm_model_name, temperature=0.0
            )
        elif _llm_model_name.startswith('claude'):
            # Anthropic Claude
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(model=_llm_model_name, temperature=0.0)

    # default: OpenAI
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=_llm_model_name or "gpt-5-mini",
    )


async def run_task(
    *, task: str, max_steps: int | None = None, url: str | None = None
):
    """
    設定した Chrome デバッグポートでログインする。

    Args:
        task: 実行するタスクの説明
        max_steps: 最大ステップ数
        url: 最初に開く URL（指定された場合）
    """
    logger.info(f"タスク開始: {task}")

    if url:
        logger.info(f"指定 URL: {url}")

    if max_steps is None:
        # 環境変数から max_steps を取得
        max_steps = int(os.getenv('BROWSER_USE_MAX_STEPS', 7))

    logger.debug(f"{max_steps=}")

    logger.debug(f"{BROWSER_BOT_USE_REMOTE=}")
    # リモートブラウザかローカルブラウザかによって処理を分岐
    if BROWSER_BOT_USE_REMOTE:
        from selenium_remote import get_cdp_url_from_selenium_grid

        logger.info(f"リモートブラウザを使用: {SELENIUM_REMOTE_URL}")
        # Selenium Grid から CDP URL を取得
        cdp_url = await get_cdp_url_from_selenium_grid(SELENIUM_REMOTE_URL)
        # リモートブラウザに接続（CDP URL 使用）
        browser_session = BrowserSession(cdp_url=cdp_url)
    else:
        # Chrome が起動しているか確認
        await _check_chrome_running()

        # 既存のローカル Chrome に接続
        browser_session = BrowserSession(cdp_url=CHROME_DEBUG_URL)

    # browser_session を開始してコンソールメッセージのリスナーを設定
    await browser_session.start()

    # 現在のページを取得してコンソールイベントをリスン
    try:
        page = await browser_session.get_current_page()
        _setup_page_logging(page)
        await page.wait_for_load_state('networkidle')
    except Exception as e:
        error_msg = f"❌ エラー: エージェント実行中にエラーが発生しました: {e.__class__.__name__}: {e}"
        logger.error(error_msg, exc_info=True)
        raise BrowserBotTaskFailedError(error_msg)

    # URL が指定されている場合、ブラウザを直接操作して遷移
    if url:
        logger.info(f"指定された URL に遷移: {url}")
        try:
            # 現在のページを取得（すでに browser_session.start() 済み）
            page = await browser_session.get_current_page()
            # URL に遷移
            await page.goto(url)
            load_state = await _page_wait_for_load_state(page)
            if load_state == 'skipped':
                logger.info(f"✅ {url} への遷移を続行")
            else:
                logger.info(f"✅ {url} への遷移完了（{load_state}）")
        except Exception as e:
            logger.warning(
                f"URL への遷移中にエラー: {e.__class__.__name__}: {e}"
            )
            # エラーが発生しても続行（Agent が処理する）

    llm_model = get_llm()
    logger.info(f"使用する LLM モデル: {llm_model.__class__.__name__}")
    # Agent を作成
    agent = Agent(
        task=task,
        llm=llm_model,
        browser_session=browser_session,
    )

    timeout_seconds = max_steps * 6

    try:
        # 1分（60秒）のタイムアウトを設定
        result = await asyncio.wait_for(
            agent.run(max_steps=max_steps), timeout=timeout_seconds
        )
        logger.info(
            f"タスク完了 (max_steps={max_steps}): {str(result)[:200]}..."
        )  # 最初の200文字のみログに記録
        return result
    except asyncio.TimeoutError:
        error_msg = f"❌ エラー: エージェント実行が{timeout_seconds}秒でタイムアウトしました"
        logger.error(error_msg)
        raise BrowserBotTaskFailedError(error_msg)
    except Exception as e:
        error_msg = f"❌ エラー: エージェント実行中にエラーが発生しました: {e.__class__.__name__}: {e}"
        logger.error(error_msg, exc_info=True)
        raise BrowserBotTaskFailedError(error_msg)


async def _get_active_page(
    playwright_instance,
    *,
    url: str | None = None,
    create_new_page: bool = True,
):
    """
    Chrome のアクティブなページを取得する共通処理

    Args:
        playwright_instance: Playwright のインスタンス
        url: 指定されたら遷移する

    Returns:
        tuple: (page, browser) または (None, None)
    """
    if url and url.lower() in {'null', 'none', 'undefined', ''}:
        url = None

    # ブラウザに接続
    browser = await _get_browser_connection(playwright_instance)

    try:
        # 既存のコンテキストを取得
        contexts = browser.contexts
        if not contexts:
            error_msg = (
                "❌ エラー: Chrome にアクティブなコンテキストがありません"
            )
            logger.error(error_msg)
            await browser.close()
            raise BrowserRuntimeError(error_msg)

        # 全コンテキストからページを収集
        all_pages = []
        for context in contexts:
            for page in context.pages:
                # ページが閉じられていないかチェック
                if not page.is_closed():
                    # DevTools や特殊なプロトコルのページをスキップ
                    page_url = page.url
                    if page_url.startswith(
                        (
                            'devtools://',
                            'chrome://',
                            'chrome-extension://',
                            'moz-extension://',
                        )
                    ):
                        logger.debug(
                            f"特殊プロトコルページをスキップ: {page_url}"
                        )
                        continue
                    all_pages.append(page)

        if all_pages:
            # 最も最近アクティブになったページを特定
            active_page = await _find_most_recent_active_page(all_pages)

            if not active_page:
                # フォールバック: 最初の有効なページを使用
                active_page = all_pages[0]
                logger.info(
                    "最新のアクティブページが特定できないため、最初のページを使用します"
                )

        else:
            # ページが取得できなかった
            if create_new_page:
                # 無かった場合に作る設定になっている
                # 新しいページを作成
                active_page = await browser.new_page()
                all_pages = [active_page]
            else:
                error_msg = (
                    "❌ エラー: Chrome にアクティブなページがありません"
                )
                logger.error(error_msg)
                await browser.close()
                raise BrowserRuntimeError(error_msg)

        logger.info(f"アクティブページを特定: {active_page.url}")

        # URL が指定されていれば遷移
        if url:
            logger.info(f"URL に遷移: {url}")
            await active_page.goto(url)
            # ページのロード状態を待機
            await _page_wait_for_load_state(active_page)

        # ページログ転送を設定
        _setup_page_logging(active_page)

        return active_page, browser

    except Exception as e:
        await browser.close()
        error_msg = f"❌ エラー: アクティブページの取得中にエラーが発生しました: {e.__class__.__name__}: {e}"
        logger.error(error_msg, exc_info=True)
        raise BrowserRuntimeError(error_msg)


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

                # DevTools や特殊なプロトコルのページをスキップ
                if url.startswith(
                    (
                        'devtools://',
                        'chrome://',
                        'chrome-extension://',
                        'moz-extension://',
                    )
                ):
                    logger.debug(f"特殊プロトコルページをスキップ: {url}")
                    continue

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
                logger.debug(
                    f"ページ情報取得エラー: {e.__class__.__name__}: {e}"
                )
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
            f"選択理由 - フォーカス: {selected_page['has_focus']}, "
            f"表示状態: {selected_page['visibility_state']}"
        )

        return selected_page['page']

    except Exception as e:
        logger.error(
            f"アクティブページの特定中にエラー: {e.__class__.__name__}: {e}",
            exc_info=True,
        )
        return None


def _setup_page_logging(page):
    """
    ページにコンソールログとエラーログの転送を設定する

    Args:
        page: Playwright page オブジェクト
    """
    try:
        # コンソールメッセージのリスナーを設定
        page.on(
            'console',
            lambda msg: broser_console_logger.info(
                f"console.{msg.type}: {msg.text}"
            ),
        )

        # エラーイベントもキャプチャ
        page.on(
            'pageerror',
            lambda error: broser_console_logger.error(f"[PAGE ERROR] {error}"),
        )

        logger.debug(f"ページログ転送を設定: {page.url}")
    except Exception as e:
        logger.warning(
            f"ページログ転送設定に失敗: {e.__class__.__name__}: {e}"
        )


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
    現在アクティブなタブのソースコードを取得し、Downloads フォルダに保存する

    Args:
        url: 指定されたらその URL に移動してから取得

    Returns:
        dict: {
            'file_path': str,  # 保存したファイルのフルパス
            'url': str,        # 現在のURL
            'title': str       # ページタイトル
        }
    """
    logger.info("ソースコード取得開始")

    async with async_playwright() as p:
        page, browser = await _get_active_page(p, url=url)

        try:
            # 現在の状態を取得
            current_url = page.url

            # ページが完全に読み込まれるまで待機
            await _page_wait_for_load_state(page)

            # タイトルとソースコードを取得
            try:
                title = await page.title()
            except Exception:
                title = "Unknown"
                logger.warning("タイトル取得に失敗しました")

            source = await page.content()

            # ファイルに保存
            downloads_dir = os.path.expanduser("~/Downloads")
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            filename = f"browser-bot-source-{timestamp}.html"
            file_path = os.path.join(downloads_dir, filename)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(source)

            logger.info(
                f"ソースコード取得完了: {current_url}, ファイル保存: {file_path}"
            )

            return {'file_path': file_path, 'url': current_url, 'title': title}
        finally:
            await browser.close()


async def get_visible_screenshot(
    *,
    url: str | None = None,
    page_y_offset_as_viewport_height: float = 0.0,
    include_image_binary: bool = False,
):
    """
    現在アクティブなタブの表示されている箇所をスクリーンショットする

    Args:
        url: 指定されたらその URL に移動してから取得
        page_y_offset_as_viewport_height: ビューポートの高さを基準にした
            スクロール量の倍率。1.0 で 1 ページ分下にスクロール
        include_image_binary: True の場合、画像バイナリを返す。
            デフォルト False

    Returns:
        dict: {
            'file_path': str,     # 保存したファイルのフルパス
            'url': str,           # 現在のURL
            'title': str          # ページタイトル
            'screenshot': bytes,  # 画像バイナリ (include_image_binary=True の場合のみ)
        }
    """
    logger.info(
        f"表示箇所のスクリーンショット取得開始 "
        f"(スクロール倍率: {page_y_offset_as_viewport_height})"
    )

    async with async_playwright() as p:
        page, browser = await _get_active_page(p, url=url)

        try:
            # 現在の状態を取得
            current_url = page.url

            # ページが完全に読み込まれるまで待機
            await _page_wait_for_load_state(page)

            # タイトルを取得
            try:
                title = await page.title()
            except Exception:
                title = "Unknown"
                logger.warning("タイトル取得に失敗しました")

            # スクロール処理
            if page_y_offset_as_viewport_height > 0:
                # ビューポートの高さを取得
                viewport_height = await page.evaluate(
                    "() => window.innerHeight"
                )
                # スクロール量を計算
                scroll_y = int(
                    viewport_height * page_y_offset_as_viewport_height
                )
                # スクロール実行
                await page.evaluate(f"() => window.scrollBy(0, {scroll_y})")
                # スクロール後の描画を待つ
                await page.wait_for_timeout(500)
                logger.info(
                    f"ページをスクロールしました: {scroll_y}px "
                    f"(ビューポート高さ {viewport_height}px の "
                    f"{page_y_offset_as_viewport_height} 倍)"
                )

            # 表示箇所のスクリーンショット取得
            screenshot_bytes = await page.screenshot()

            # サイズ調整
            # やっぱりリサイズしない
            # screenshot_bytes = _resize_image_if_needed(screenshot_bytes)

            # ファイルに保存
            downloads_dir = os.path.expanduser("~/Downloads")
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            filename = f"browser-bot-screenshot-{timestamp}.png"
            file_path = os.path.join(downloads_dir, filename)

            with open(file_path, "wb") as f:
                f.write(screenshot_bytes)

            logger.info(
                f"表示箇所のスクリーンショット取得完了: {current_url}, "
                f"ファイル保存: {file_path}"
            )

            result = {
                'file_path': file_path,
                'url': current_url,
                'title': title,
            }

            if include_image_binary:
                result['screenshot'] = screenshot_bytes

            return result
        finally:
            await browser.close()


async def get_full_screenshot(
    *, url: str | None = None, include_image_binary: bool = False
):
    """
    現在アクティブなタブの全領域をスクリーンショットする

    Args:
        url: 指定されたらその URL に移動してから取得
        include_image_binary: True の場合、画像バイナリを返す。
            デフォルト False

    Returns:
        dict: {
            'file_path': str,     # 保存したファイルのフルパス
            'url': str,           # 現在のURL
            'title': str          # ページタイトル
            'screenshot': bytes,  # 画像バイナリ (include_image_binary=True の場合のみ)
        }
    """
    logger.info("全領域のスクリーンショット取得開始")

    async with async_playwright() as p:
        page, browser = await _get_active_page(p, url=url)

        try:
            # 現在の状態を取得
            current_url = page.url

            # ページが完全に読み込まれるまで待機
            await _page_wait_for_load_state(page)

            # タイトルを取得
            try:
                title = await page.title()
            except Exception:
                title = "Unknown"
                logger.warning("タイトル取得に失敗しました")

            # 全領域のスクリーンショット取得
            screenshot_bytes = await page.screenshot(full_page=True)

            # サイズ調整（全領域は特に大きくなりがちなので、より小さい制限を設定）
            # やっぱりリサイズしない
            # screenshot_bytes = _resize_image_if_needed(
            #     screenshot_bytes, max_size_bytes=800000
            # )

            # ファイルに保存
            downloads_dir = os.path.expanduser("~/Downloads")
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            filename = f"browser-bot-screenshot-{timestamp}.png"
            file_path = os.path.join(downloads_dir, filename)

            with open(file_path, "wb") as f:
                f.write(screenshot_bytes)

            logger.info(
                f"全領域のスクリーンショット取得完了: {current_url}, "
                f"ファイル保存: {file_path}"
            )

            result = {
                'file_path': file_path,
                'url': current_url,
                'title': title,
            }

            if include_image_binary:
                result['screenshot'] = screenshot_bytes

            return result
        finally:
            await browser.close()


async def get_current_url():
    """
    現在アクティブなタブの URL を取得する

    Returns:
        dict: {
            'url': str,     # 現在のURL
            'title': str    # ページタイトル
        }
    """
    logger.info("現在の URL 取得開始")

    async with async_playwright() as p:
        page, browser = await _get_active_page(
            p, url=None, create_new_page=False
        )

        try:
            # 現在の状態を取得
            current_url = page.url

            # タイトルを取得
            try:
                title = await page.title()
            except Exception:
                title = "Unknown"
                logger.warning("タイトル取得に失敗しました")

            logger.info(f"現在の URL 取得完了: {current_url}")

            return {'url': current_url, 'title': title}

        except Exception as e:
            error_msg = f"❌ エラー: URL 取得中に予期しないエラーが発生しました: {e.__class__.__name__}: {e}"
            logger.error(error_msg, exc_info=True)
            raise BrowserBotTaskFailedError(error_msg)
        finally:
            await browser.close()


async def super_reload(*, url: str | None = None, mode: str = 'cdp'):
    """
    現在アクティブなタブでスーパーリロードを実行する

    Args:
        url: 指定されたらその URL に移動してからスーパーリロード
        mode: リロード方法 ('cdp', 'javascript', 'keyboard')
            デフォルト = cdp

    Returns:
        dict: {
            'url': str,     # リロード後のURL
            'title': str    # ページタイトル
        }
    """
    logger.info("スーパーリロード開始")

    # Chrome が起動しているか確認
    await _check_chrome_running()

    async with async_playwright() as p:
        page, browser = await _get_active_page(p, url=url)

        try:
            # 現在の URL を保存
            current_url = page.url if not url else url

            # URL が指定されていて、現在のURLと異なる場合は移動
            if url and page.url != url:
                logger.info(f"指定 URL に移動: {url}")
                await page.goto(url)
                await _page_wait_for_load_state(page)

            # Playwright の reload メソッドでキャッシュを無視してリロード
            logger.info(f"スーパーリロード実行中: {current_url}, {mode=}")

            if mode == 'javascript':
                # JavaScript を使ってスーパーリロード
                await _super_reload_with_javascript(page)
            elif mode == 'keyboard':
                # キーボードショートカットを使ってスーパーリロード
                await _super_reload_with_keyboard(page)
            else:
                # CDP (Chrome DevTools Protocol) を使ってスーパーリロード
                await _super_reload_with_cdp(page)

            # リロード完了を待つ
            await _page_wait_for_load_state(page)

            # タイトルを取得
            try:
                title = await page.title()
            except Exception:
                title = "Unknown"
                logger.warning("タイトル取得に失敗しました")

            final_url = page.url
            logger.info(f"スーパーリロード完了: {final_url}")

            return {'url': final_url, 'title': title}

        except Exception as e:
            error_msg = (
                f"❌ エラー: スーパーリロード中に予期しないエラーが発生しました: "
                f"{e.__class__.__name__}: {e}"
            )
            logger.error(error_msg, exc_info=True)
            raise BrowserBotTaskFailedError(error_msg)

        finally:
            await browser.close()


async def _super_reload_with_cdp(page):
    """
    CDP (Chrome DevTools Protocol) を使用してスーパーリロードを実行する

    Args:
        page: Playwright のページオブジェクト

    Returns:
        None
    """
    try:
        cdp_session = await page.context.new_cdp_session(page)
        await cdp_session.send('Page.reload', {'ignoreCache': True})
        logger.info("CDP を使用してスーパーリロードを実行しました")
    except Exception as e:
        logger.error(f"CDP リロードエラー: {e.__class__.__name__}: {e}")
        raise BrowserBotTaskFailedError(f"CDP リロードエラー: {e}")


async def _super_reload_with_keyboard(page):
    """
    キーボードショートカットを使用してスーパーリロードを実行する

    Args:
        page: Playwright のページオブジェクト

    Returns:
        None
    """
    try:
        import platform

        if platform.system() == 'Darwin':  # macOS
            await page.keyboard.down('Meta')
            await page.keyboard.down('Shift')
            await page.keyboard.press('R')
            await page.keyboard.up('Shift')
            await page.keyboard.up('Meta')
        else:  # Windows/Linux
            await page.keyboard.down('Control')
            await page.keyboard.down('Shift')
            await page.keyboard.press('R')
            await page.keyboard.up('Shift')
            await page.keyboard.up('Control')

        logger.info("キーボードショートカットでスーパーリロードを実行しました")
    except Exception as e:
        logger.error(
            f"キーボードショートカットリロードエラー: {e.__class__.__name__}: {e}"
        )
        raise BrowserBotTaskFailedError(
            f"キーボードショートカットリロードエラー: {e}"
        )


async def _super_reload_with_javascript(page):
    """
    JavaScript を使用してスーパーリロードを実行する

    Args:
        page: Playwright のページオブジェクト

    Returns:
        None
    """
    try:
        await page.evaluate(
            """
            () => {
                // location.reload(true) は deprecated だが、多くのブラウザでまだ動作する
                if (typeof location.reload === 'function') {
                    try {
                        location.reload(true);
                    } catch (e) {
                        // 方法2: キャッシュバスティング用のタイムスタンプを追加
                        const url = new URL(window.location.href);
                        url.searchParams.set('_t', Date.now().toString());
                        window.location.href = url.toString();
                    }
                }
            }
        """
        )
        logger.info("JavaScript でスーパーリロードを実行しました")
    except Exception as e:
        logger.error(f"JavaScript リロードエラー: {e.__class__.__name__}: {e}")
        raise BrowserBotTaskFailedError(f"JavaScript リロードエラー: {e}")


async def run_script(*, script: str, url: str | None = None):
    """
    JavaScript を受け取って、Playwright を使ってブラウザ上でそのスクリプトを実行する

    Args:
        script: 実行する JavaScript コード
        url: 指定されたらその URL に移動してから実行

    Returns:
        JavaScript の実行結果
    """
    if not script:
        logger.error(
            "❌ run_script: エラー: 実行する JavaScript (script) が指定されていません。"
        )
        raise BrowserBotTaskAbortedError(
            "実行する JavaScript が指定されていません。"
        )

    logger.info("JavaScript スクリプト実行開始")
    logger.debug(f"スクリプト内容: {script}...")

    if url:
        logger.info(f"指定 URL: {url}")

    # Chrome が起動しているか確認
    chrome_check_error = await _check_chrome_running()
    if chrome_check_error:
        return None

    async with async_playwright() as p:
        page, browser = await _get_active_page(p, url=url)

        try:
            # ページが完全に読み込まれるまで待機
            await _page_wait_for_load_state(page)

            # JavaScript を実行
            # スクリプトを async function で囲って実行
            wrapped_script = f"(async () => {{\n{script}\n}})();"
            result = await page.evaluate(wrapped_script)
            logger.info(f"✅ JavaScript スクリプト実行完了: result={result}")

            # 実行結果をログに記録（結果が大きい場合は切り詰める）
            if result is not None:
                result_str = str(result)
                if len(result_str) > 500:
                    logger.debug(f"実行結果: {result_str[:500]}...")
                else:
                    logger.debug(f"実行結果: {result_str}")

            return result

        except Exception as e:
            error_msg = f"❌ スクリプト実行中に予期しないエラーが発生しました: {e.__class__.__name__}: {e}"
            logger.error(error_msg, exc_info=True)
            raise BrowserBotTaskFailedError(error_msg)

        finally:
            await browser.close()
            logger.info("ブラウザ接続を閉じました")


async def run_python_script(
    *, python_script_text: str = None, url: str | None = None
):
    """
    Playwright 用の Python スクリプトを実行する。
    eval 的なコード実行をしているのでリスクがある。信頼できるコードのみ実行すること。

    Args:
        python_script_text: 実行する Python コード
            page オブジェクトを 'page' という変数名で使用可能。
            return を書くとその値が実行結果として返される。
        url: 指定されたらその URL に移動してから実行

    Returns:
        return の実行結果
    """
    if not python_script_text:
        logger.error(
            "❌ run_python_script: エラー: 実行する Python スクリプト "
            "(python_script_text) が指定されていません。"
        )
        raise BrowserBotTaskAbortedError(
            "実行する Python スクリプトが指定されていません。"
        )

    logger.info("Python スクリプト実行開始")

    await _check_chrome_running()

    async with async_playwright() as p:
        page, browser = await _get_active_page(p, url=url)

        # ページが完全に読み込まれるまで待機
        await _page_wait_for_load_state(page)

        # page オブジェクトを利用可能にして Python スクリプトを実行
        local_vars = {'page': page, 'asyncio': asyncio}
        global_vars = {'page': page, 'asyncio': asyncio}
        try:
            # async 関数として実行するためにラップ
            wrapped_script = f"""
async def user_script():
{chr(10).join('    ' + line for line in python_script_text.strip().split(chr(10)))}
"""
            logger.debug('wrapped_script: %s', wrapped_script)
            # 関数を定義
            compiled_code = compile(wrapped_script, '<string>', 'exec')
            exec(compiled_code, global_vars, local_vars)
            # 定義した関数を実行
            result = await local_vars['user_script']()
            logger.info(
                f"カスタム Python スクリプトの実行が完了しました: {result=}"
            )
            return result

        except Exception as e:
            error_msg = f"❌ スクリプト実行中に予期しないエラーが発生しました: {e.__class__.__name__}: {e}"
            logger.error(error_msg, exc_info=True)
            raise BrowserBotTaskFailedError(error_msg)

        finally:
            await browser.close()
            logger.info("ブラウザ接続を閉じました")


epilog = '''
# Using javascript script example
[tests/test-script.sh]

```shell
echo "
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));
document.querySelector('.header .search-form input.header-search-input').click();
await sleep(1000);
document.querySelector('#search-modal-input').value = 'ハイキュー';
await sleep(1000);
const e = new Event('input', { bubbles: true });
document.querySelector('#search-modal-input').dispatchEvent(e);
await sleep(1000);
document.querySelector('button[data-annotate=\"search-submit-button\"]').click();
await sleep(2000);
return '完了しました。 URL: ' + window.location.href;
" | .venv/bin/python browser_bot.py --script --url https://www.mangazenkan.com
```

# Using python script example
[tests/test-python-script.sh]

```shell
echo "
await asyncio.sleep(1)
await page.click('.header .search-form span.header-search-input')
await page.fill('#search-modal-input', 'ハイキュー')
await asyncio.sleep(1)
await page.click('button[data-annotate=\"search-submit-button\"]')
await asyncio.sleep(2)
return f'完了しました。 URL: {page.url}'
" | .venv/bin/python browser_bot.py --python-script --url https://www.mangazenkan.com
```
'''

if __name__ == '__main__':
    dotenv.load_dotenv()

    parser = argparse.ArgumentParser(
        description="Run a browser automation task.",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '--max-steps',
        type=int,
        help='Maximum number of steps for the agent to run.',
    )
    parser.add_argument(
        '--script',
        action='store_true',
        help='Execute input as JavaScript instead of Playwright task.',
    )
    parser.add_argument(
        '--python-script',
        action='store_true',
        help='Execute input as Python script instead of Playwright task.',
    )
    parser.add_argument(
        '--url',
        type=str,
        help='URL to navigate to before executing the task or script.',
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
        print(
            "例: echo 'document.getElementById(\"submit\").click()' | "
            "python browser_bot.py --script"
        )
        sys.exit(1)

    # --script フラグがある場合は JavaScript として実行
    # JavaScript コードは自動的に async 即時関数でラップされて実行される
    try:
        if args.python_script:
            # Playwright 用の Python スクリプトを実行
            result = asyncio.run(
                run_python_script(python_script_text=task, url=args.url)
            )
            if result is not None:
                print(result)

        elif args.script:
            # Playwright 内で JavaScript を実行
            result = asyncio.run(run_script(script=task, url=args.url))
            if result is not None:
                print(result)
        else:
            # browser_use のタスク
            asyncio.run(
                run_task(task=task, max_steps=args.max_steps, url=args.url)
            )
    except BrowserBotError as e:
        logger.error(f"❌ エラー: {e}")
        sys.exit(1)


async def request(
    *, method, url: str, preload_url: str | None = None, **kwargs
) -> APIResponse:
    """
    現在開いている Browser-bot のブラウザセッションを使って HTTP リクエストを送信する。

    Args:
        method: HTTP メソッド ('get', 'post', etc.)
        url: リクエスト先の URL
        preload_url: 指定されたらその URL に移動してからリクエストを送信
        **kwargs: requests.request に渡す追加のキーワード引数
          data: POST ボディ
          headers: HTTP ヘッダー

    Returns:
        APIResponse
            .status ステータスコード
            .ok 成功したかどうか
            .headers レスポンスヘッダー
            await body() レスポンス本文
            await json() JSONのレスポンス本文をパースしてデータを取得
            await test() レスポンス本文をテキストで取得 (utf-8に限る)

    """
    # Chrome が起動しているか確認
    await _check_chrome_running()

    method = method.lower()
    if not method in {
        'get',
        'post',
        'put',
        'delete',
        'patch',
        'head',
        'options',
    }:
        error_msg = (
            f"❌ エラー: サポートされていない HTTP メソッドです: {method}"
        )
        logger.error(error_msg)
        raise BrowserBotTaskAbortedError(error_msg)

    async with async_playwright() as p:
        page, _browser = await _get_active_page(p, url=preload_url)

        request_metod = getattr(page.request, method)

        response: APIResponse = await request_metod(
            url,
            **kwargs,
        )

        # レスポンスの内容を取得（コンテキストが閉じられる前に）
        response_body = await response.body()
        response_headers = dict(response.headers)
        response_status = response.status

        # レスポンスデータを辞書として返す
        return {
            'status': response_status,
            'headers': response_headers,
            'body': response_body,
        }


async def run_lighthouse(
    *,
    url: str | None = None,
    categories: list[str] | None = None,
    device: str = 'desktop',
    timeout_seconds: int = 120,
):
    """
    Lighthouse を使ってパフォーマンス監査を実行する

    Args:
        url: 監査対象の URL。指定しない場合は現在アクティブなタブの URL を使用
        categories: 監査カテゴリのリスト。
            選択肢: 'performance', 'accessibility', 'best-practices', 'seo', 'pwa'
            指定しない場合は performance のみ
        device: エミュレートするデバイス ('desktop' または 'mobile')
        timeout_seconds: タイムアウト秒数 (デフォルト: 120秒)

    Returns:
        dict: {
            'url': str,           # 監査した URL
            'scores': dict,       # カテゴリ別スコア (0-100)
            'metrics': dict,      # 詳細メトリクス (LCP, FCP, TBT など)
            'report_path': str,   # HTML レポートのファイルパス
            'json_path': str,     # JSON レポートのファイルパス
        }
    """
    logger.info("Lighthouse 監査開始")

    # npx が使用可能か確認
    npx_path = shutil.which('npx')
    if not npx_path:
        error_msg = (
            "❌ エラー: npx コマンドが見つかりません。"
            "Node.js と npm がインストールされているか確認してください。"
        )
        logger.error(error_msg)
        raise BrowserRuntimeError(error_msg)

    # URL が指定されていない場合は現在のページの URL を取得
    if not url:
        await _check_chrome_running()
        async with async_playwright() as p:
            page, browser = await _get_active_page(
                p, url=None, create_new_page=False
            )
            url = page.url
            await browser.close()
        logger.info(f"現在のページの URL を使用: {url}")

    # カテゴリのデフォルト値
    if not categories:
        categories = ['performance']

    # 有効なカテゴリを検証
    valid_categories = {
        'performance',
        'accessibility',
        'best-practices',
        'seo',
        'pwa',
    }
    invalid_categories = set(categories) - valid_categories
    if invalid_categories:
        error_msg = (
            f"❌ エラー: 無効なカテゴリ: {invalid_categories}。"
            f"有効なカテゴリ: {valid_categories}"
        )
        logger.error(error_msg)
        raise BrowserBotTaskAbortedError(error_msg)

    # デバイスの検証
    valid_devices = {'desktop', 'mobile'}
    if device not in valid_devices:
        error_msg = (
            f"❌ エラー: 無効なデバイス: {device}。"
            f"有効なデバイス: {valid_devices}"
        )
        logger.error(error_msg)
        raise BrowserBotTaskAbortedError(error_msg)

    # 出力ファイルパスを準備
    downloads_dir = os.path.expanduser("~/Downloads")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base_filename = f"lighthouse-{timestamp}"
    json_path = os.path.join(downloads_dir, f"{base_filename}.json")
    html_path = os.path.join(downloads_dir, f"{base_filename}.html")

    # Chrome のデバッグポートを取得
    chrome_port = CHROME_DEBUG_URL.split(':')[-1]

    # Lighthouse コマンドを構築
    cmd = [
        npx_path,
        'lighthouse',
        url,
        f'--port={chrome_port}',
        '--output=json,html',
        f'--output-path={os.path.join(downloads_dir, base_filename)}',
        f'--only-categories={",".join(categories)}',
        '--quiet',
        '--chrome-flags=--ignore-certificate-errors',
    ]

    # デバイス設定
    if device == 'mobile':
        cmd.append('--emulated-form-factor=mobile')
    else:
        cmd.append('--emulated-form-factor=desktop')
        cmd.append('--preset=desktop')

    logger.info(f"Lighthouse コマンド実行: {' '.join(cmd)}")

    try:
        # Lighthouse を実行
        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )

        if result.returncode != 0:
            error_msg = (
                f"❌ Lighthouse 実行エラー (code={result.returncode}): "
                f"{result.stderr[:500] if result.stderr else 'unknown error'}"
            )
            logger.error(error_msg)
            raise BrowserBotTaskFailedError(error_msg)

        # JSON レポートを読み込んでスコアとメトリクスを抽出
        with open(json_path, 'r', encoding='utf-8') as f:
            report = json.load(f)

        # カテゴリ別スコアを抽出
        scores = {}
        for cat_id, cat_data in report.get('categories', {}).items():
            scores[cat_id] = round(cat_data.get('score', 0) * 100)

        # 主要メトリクスを抽出
        audits = report.get('audits', {})
        metrics = {}

        # Performance メトリクス
        metric_keys = {
            'first-contentful-paint': 'FCP',
            'largest-contentful-paint': 'LCP',
            'total-blocking-time': 'TBT',
            'cumulative-layout-shift': 'CLS',
            'speed-index': 'SI',
            'interactive': 'TTI',
        }
        for audit_key, metric_name in metric_keys.items():
            if audit_key in audits:
                audit = audits[audit_key]
                metrics[metric_name] = {
                    'value': audit.get('numericValue'),
                    'display': audit.get('displayValue'),
                    'score': round((audit.get('score') or 0) * 100),
                }

        logger.info(f"Lighthouse 監査完了: {url}, スコア: {scores}")

        return {
            'url': url,
            'scores': scores,
            'metrics': metrics,
            'report_path': html_path,
            'json_path': json_path,
        }

    except subprocess.TimeoutExpired:
        error_msg = (
            f"❌ Lighthouse 実行がタイムアウトしました ({timeout_seconds}秒)"
        )
        logger.error(error_msg)
        raise BrowserBotTaskFailedError(error_msg)
    except FileNotFoundError:
        error_msg = "❌ Lighthouse レポートファイルが見つかりません"
        logger.error(error_msg)
        raise BrowserBotTaskFailedError(error_msg)
    except json.JSONDecodeError as e:
        error_msg = f"❌ Lighthouse レポートの解析に失敗: {e}"
        logger.error(error_msg)
        raise BrowserBotTaskFailedError(error_msg)
