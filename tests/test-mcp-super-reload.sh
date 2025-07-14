#!/usr/bin/env zsh
# スーパーリロードツールのテスト

cd $(dirname $0)/../

{
    echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test-client", "version": "1.0.0"}}}'
    sleep 0.5
    echo '{"jsonrpc": "2.0", "method": "notifications/initialized"}'
    sleep 0.5
    echo '{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "super_reload", "arguments": {}}}'
    sleep 1
} | ./launch-mcp-server.sh

# 終了時に anyio.ClosedResourceError が出るが気にしない
