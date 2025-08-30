#!/usr/bin/env zsh
# Chrome を :9222 でゲストモード起動するスクリプト。

# 既に:9222 で起動しているものあがれば kill
lsof -ti :9222 | xargs kill -9

echo "Chrome をゲストモードで起動中..."
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --guest \
  --no-first-run \
  --disable-default-apps
