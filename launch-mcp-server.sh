#!/usr/bin/env zsh

# MCPサーバーを起動するスクリプト

cd $(dirname $0)

[ -f .loadenv.sh ] && source .loadenv.sh

.venv/bin/python3 mcp_server.py
