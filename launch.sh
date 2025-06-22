#!/usr/bin/env zsh

cd $(dirname $0)
. .venv/bin/activate

python3 mcp_server.py
