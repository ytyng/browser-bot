#!/usr/bin/env zsh

# MCPサーバーを起動するスクリプト

cd $(dirname $0)
. .venv/bin/activate

python3 mcp_server.py
