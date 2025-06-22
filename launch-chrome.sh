#!/usr/bin/env zsh
# Chrome を :9222 でテスト用に起動するスクリプト。

# Alfred でも起動できるのでそっちが良い

# 既に:9222 で起動しているものあがれば kill
lsof -ti :9222 | xargs kill -9

/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=${HOME}/.google-chrome-debug \
  --no-first-run \
  --disable-default-apps
