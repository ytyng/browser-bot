#!/bin/bash

# ページスクロール機能のテストスクリプト

# 0. スクロールなし（デフォルト）
echo "=== テスト1: スクロールなし ==="
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_visible_screenshot", "arguments": {"url": "https://example.com"}}}' | ../launch-mcp-server.sh

# 1. 1ページ分下にスクロール
echo -e "\n\n=== テスト2: 1ページ分下にスクロール ==="
echo '{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_visible_screenshot", "arguments": {"url": "https://example.com", "page_y_offset_as_viewport_height": 1.0}}}' | ../launch-mcp-server.sh

# 2. 半ページ分下にスクロール
echo -e "\n\n=== テスト3: 半ページ分下にスクロール ==="
echo '{"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_visible_screenshot", "arguments": {"url": "https://example.com", "page_y_offset_as_viewport_height": 0.5}}}' | ../launch-mcp-server.sh

# 3. 2ページ分下にスクロール
echo -e "\n\n=== テスト4: 2ページ分下にスクロール ==="
echo '{"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "get_visible_screenshot", "arguments": {"url": "https://example.com", "page_y_offset_as_viewport_height": 2.0}}}' | ../launch-mcp-server.sh
