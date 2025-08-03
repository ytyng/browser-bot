#!/usr/bin/env python3

import argparse
import asyncio
import os
import sys

from logging_config import broser_console_logger, logger

# テレメトリを無効化
os.environ['ANONYMIZED_TELEMETRY'] = 'false'

import io

import dotenv
import httpx
from browser_use import Agent, BrowserSession
from PIL import Image
from playwright._impl._errors import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright


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
    Chrome が :9222 で起動しているかを確認する共通処理

    Returns:
        str | None: エラーメッセージ、または None（正常時）
    """
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
                raise BrowserRuntimeError(error_msg)
    except httpx.ConnectError:
        error_msg = (
            "❌ エラー: Chrome が :9222 で起動していません。"
            "launch-chrome.sh を実行してから再度お試しください。"
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

    logger.info("✅ Chrome が :9222 で起動していることを確認しました。")


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

    # default: OpenAI
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=_llm_model_name or "gpt-4.1-mini",
        temperature=0.0,
    )


async def run_task(
    *, task: str, max_steps: int | None = None, url: str | None = None
):
    """
    :9222 の Chrome でログインする。

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

    logger.debug(f"max_steps: {max_steps}")

    # Chrome が :9222 で起動しているか確認
    await _check_chrome_running()

    # 既存の Chrome に接続
    browser_session = BrowserSession(cdp_url='http://localhost:9222')

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

    # Agent を作成
    agent = Agent(
        task=task,
        llm=get_llm(),
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

            logger.info(f"ソースコード取得完了: {current_url}")

            return {'source': source, 'url': current_url, 'title': title}
        finally:
            await browser.close()


async def get_visible_screenshot(
    *, url: str | None = None, page_y_offset_as_viewport_height: float = 0.0
):
    """
    現在アクティブなタブの表示されている箇所をスクリーンショットする

    Args:
        url: 指定されたらその URL に移動してから取得
        page_y_offset_as_viewport_height: ビューポートの高さを基準にした
            スクロール量の倍率。1.0 で 1 ページ分下にスクロール

    Returns:
        dict: {
            'screenshot': bytes,  # スクリーンショットの画像データ
            'url': str,          # 現在のURL
            'title': str         # ページタイトル
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
            screenshot_bytes = _resize_image_if_needed(screenshot_bytes)

            logger.info(f"表示箇所のスクリーンショット取得完了: {current_url}")

            return {
                'screenshot': screenshot_bytes,
                'url': current_url,
                'title': title,
            }
        finally:
            await browser.close()


async def get_full_screenshot(*, url: str | None = None):
    """
    現在アクティブなタブの全領域をスクリーンショットする

    Args:
        url: 指定されたらその URL に移動してから取得

    Returns:
        dict: {
            'screenshot': bytes,  # スクリーンショットの画像データ
            'url': str,          # 現在のURL
            'title': str         # ページタイトル
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

    # Chrome が :9222 で起動しているか確認
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

    # Chrome が :9222 で起動しているか確認
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
