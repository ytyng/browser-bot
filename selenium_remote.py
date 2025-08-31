"""Selenium Grid との接続を管理するモジュール。"""

import urllib.parse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from logging_config import logger


async def get_cdp_url_from_selenium_grid(selenium_grid_url: str) -> str:
    """Selenium Grid から WebDriver セッションを作成し、CDP URL を取得する。

    Selenium Grid は WebDriver プロトコルを使用するが、browser_use は CDP を期待する。
    この関数は Selenium Grid から WebDriver セッションを作成し、
    se:cdp capability から CDP エンドポイントを取得することで、この差異を埋める。

    Args:
        selenium_grid_url: Selenium Grid の URL
        (例: http://selenium-grid.example.com:4444)

    Returns:
        CDP WebSocket URL (例: ws://node-chrome:4444/session/xxx/se/cdp)

    Raises:
        Exception: CDP URL の取得に失敗した場合
    """
    logger.info(f"Selenium Grid から CDP URL を取得中: {selenium_grid_url}")

    driver = None

    # Chrome オプションを設定
    chrome_options = Options()
    chrome_options.add_argument("--remote-debugging-port=9222")
    chrome_options.add_argument("--remote-debugging-address=0.0.0.0")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(
        "--disable-blink-features=AutomationControlled"
    )
    chrome_options.add_experimental_option(
        "excludeSwitches", ["enable-automation"]
    )
    chrome_options.add_experimental_option("useAutomationExtension", False)

    # Selenium Grid に接続して WebDriver セッションを作成
    logger.info(f"WebDriver セッションを作成中: {selenium_grid_url}")
    driver = webdriver.Remote(
        command_executor=selenium_grid_url, options=chrome_options
    )

    # セッション ID を取得
    session_id = driver.session_id
    logger.info(f"WebDriver セッション作成成功: session_id={session_id}")

    # Capabilities から CDP URL を取得
    capabilities = driver.capabilities
    logger.debug(f"Capabilities: {capabilities}")

    # Selenium Grid 4 の場合、se:cdp capability が存在する
    # 存在しない場合、
    cdp_ws_url = capabilities["se:cdp"]
    logger.info(f"se:cdp capability から CDP URL を取得: {cdp_ws_url}")
    return cdp_ws_url

    # # se:cdpVersion が存在する場合の代替方法
    # if "se:cdpVersion" in capabilities:
    #     cdp_version = capabilities["se:cdpVersion"]
    #     logger.info(f"CDP version found: {cdp_version}")

    #     # Grid ノードの URL を構築
    #     parsed = urllib.parse.urlparse(selenium_grid_url)
    #     # Selenium Grid 4 のデフォルトポート構成を使用
    #     # Grid ハブは通常 4444、ノードも 4444 で CDP を提供
    #     node_url = f"ws://{parsed.hostname}:4444/session/{session_id}/se/cdp"
    #     logger.info(f"CDP URL を構築: {node_url}")
    #     return node_url
