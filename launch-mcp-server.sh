#!/usr/bin/env zsh

# MCPサーバーを起動するスクリプト

cd $(dirname $0)

.venv/bin/python3 mcp_server.py
