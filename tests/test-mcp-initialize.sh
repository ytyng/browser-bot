#!/usr/bin/env zsh
# MCP サーバーの初期化をテスト

cd $(dirname $0)/../

# 初期化リクエストのみ送信
echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "0.1.0", "capabilities": {}, "clientInfo": {"name": "test-client", "version": "1.0.0"}}}' | ./launch-mcp-server.sh
