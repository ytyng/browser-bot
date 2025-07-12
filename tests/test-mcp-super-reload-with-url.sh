#!/usr/bin/env zsh
# スーパーリロードツール（URL指定）のテスト

cd $(dirname $0)/../

TEST_URL="https://httpbin.org/html"

# MCPサーバーとの通信を段階的に行う
{
    echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test-client", "version": "1.0.0"}}}'
    sleep 0.5
    echo '{"jsonrpc": "2.0", "method": "notifications/initialized"}'
    sleep 0.5
    echo '{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "super_reload", "arguments": {"url": "'$TEST_URL'"}}}'
    sleep 0.5
} | ./launch-mcp-server.sh
