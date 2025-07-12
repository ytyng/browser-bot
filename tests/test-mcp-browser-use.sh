#!/usr/bin/env zsh
# browser_use ツールのテスト（簡単なタスク）

cd $(dirname $0)/../

{
    echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test-client", "version": "1.0.0"}}}'
    sleep 0.5
    echo '{"jsonrpc": "2.0", "method": "notifications/initialized"}'
    sleep 0.5
    echo '{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "browser_use_local_chrome", "arguments": {"task_text": "現在のページのタイトルを確認してください", "max_steps": 3}}}'
} | ./launch-mcp-server.sh
