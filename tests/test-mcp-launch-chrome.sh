#!/usr/bin/env zsh
# Chrome 起動ツールをテストするスクリプト

cd $(dirname $0)/../

echo "=== Chrome 起動ツールテスト ==="
echo "テスト: launch_chrome_with_debug ツールの実行"
echo

# Chrome が既に起動している可能性があるので、まず確認して終了
if lsof -ti :9222 > /dev/null 2>&1; then
    echo "既存の Chrome プロセスを終了します..."
    lsof -ti :9222 | xargs kill -9 2>/dev/null || true
    sleep 2
fi

# MCPサーバーとの通信を段階的に行う
{
    # 1. 初期化リクエストを送信
    echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test-client", "version": "1.0.0"}}}'

    # 2. 初期化完了を待つ
    sleep 1

    # 3. initialized 通知を送信
    echo '{"jsonrpc": "2.0", "method": "notifications/initialized"}'

    # 4. 少し待つ
    sleep 1

    # 5. Chrome 起動ツールを呼び出す
    echo '{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "launch_chrome_with_debug", "arguments": {}}}'

    # 6. レスポンス待機
    sleep 3
} | ./launch-mcp-server.sh | {
    initialize_received=false
    tool_response_received=false
    while IFS= read -r line; do
        # 初期化レスポンスを受信したらフラグを立てる
        if echo "$line" | grep -q '"id":1'; then
            initialize_received=true
            echo "初期化完了" >&2
        fi

        # tools/call のレスポンスが見つかったら表示
        if echo "$line" | grep -q '"id":2'; then
            tool_response_received=true
            echo "ツール実行結果:"
            echo "$line" | jq '.' 2>/dev/null || echo "$line"
        fi
    done
}

echo
echo "=== 起動確認 ==="

# Chrome が起動したか確認
sleep 3
if curl -s http://localhost:9222/json/version > /dev/null 2>&1; then
    echo "✅ Chrome が正常に起動しました"
    echo
    echo "バージョン情報:"
    curl -s http://localhost:9222/json/version | jq '.'
else
    echo "❌ Chrome の起動を確認できませんでした"
    exit 1
fi

echo
echo "=== 再実行テスト (既に起動している状態) ==="
echo

# 既に起動している状態で再度実行
{
    # 1. 初期化リクエストを送信
    echo '{"jsonrpc": "2.0", "id": 3, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test-client", "version": "1.0.0"}}}'

    # 2. 初期化完了を待つ
    sleep 1

    # 3. initialized 通知を送信
    echo '{"jsonrpc": "2.0", "method": "notifications/initialized"}'

    # 4. 少し待つ
    sleep 1

    # 5. Chrome 起動ツールを再度呼び出す
    echo '{"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "launch_chrome_with_debug", "arguments": {}}}'

    # 6. レスポンス待機
    sleep 2
} | ./launch-mcp-server.sh | {
    while IFS= read -r line; do
        # tools/call のレスポンスが見つかったら表示
        if echo "$line" | grep -q '"id":4'; then
            echo "再実行結果 (既に起動している状態):"
            echo "$line" | jq '.' 2>/dev/null || echo "$line"
        fi
    done
}

echo
echo "テスト完了!"
