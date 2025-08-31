#!/usr/bin/env zsh
# ページソースコード取得ツールのテスト

cd $(dirname $0)/../

{
    echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "0.1.0", "capabilities": {}, "clientInfo": {"name": "test-client", "version": "1.0.0"}}}'
    sleep 0.5
    echo '{"jsonrpc": "2.0", "method": "notifications/initialized"}'
    sleep 0.5
    echo '{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "http_request", "arguments": {"url":"https://httpbin.org/ip", "method": "get"}}}'
    sleep 5
} | ./launch-mcp-server.sh | jq

# 終了時に anyio.ClosedResourceError が出るが気にしない
