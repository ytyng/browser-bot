#!/usr/bin/env zsh
# 利用可能なツール一覧を取得

cd $(dirname $0)/../

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
    
    # 5. tools/listリクエストを送信  
    echo '{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}'
    
    # 6. レスポンス待機
    sleep 2
} | ./launch.sh | {
    initialize_received=false
    while IFS= read -r line; do
        # 初期化レスポンスを受信したらフラグを立てる
        if echo "$line" | grep -q '"id":1'; then
            initialize_received=true
            echo "初期化完了: $line" >&2
        fi
        
        # tools/list のレスポンスが見つかったら表示
        if echo "$line" | grep -q '"id":2'; then
            echo "$line" | jq '.' 2>/dev/null || echo "$line"
            break
        fi
    done
}
