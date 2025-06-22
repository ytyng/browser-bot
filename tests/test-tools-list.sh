#!/usr/bin/env zsh
# 利用可能なツール一覧を取得

cd $(dirname $0)/../
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}' | ./launch.sh
