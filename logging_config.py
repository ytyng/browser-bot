#!/usr/bin/env python3

import logging
import os

# ファイルハンドラーの設定
log_file = '/tmp/browser_bot.log'
file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
file_handler.setFormatter(
    logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
)

# ルートロガーの設定
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# browser_use をインポートする前にログ設定を行う
os.environ['BROWSER_USE_LOGGING_LEVEL'] = 'result'

logger_set_up = False


def setup_logger_for_mcp_server():
    """
    MCPサーバー用にロガーを設定する
    標準出力にログを出さないようにする
    """
    global logger_set_up
    if logger_set_up:
        return

    logger_set_up = True

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


setup_logger_for_mcp_server()
