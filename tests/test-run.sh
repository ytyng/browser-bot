#!/usr/bin/env zsh

cd $(dirname $0)/../

echo "
* https://www.mangazenkan.com を開いてください。

* 「マンガを検索」と書かれている、検索欄をクリックしてください。

* ポップアップされたダイアログの「漫画を検索」と書かれている検索欄に、「スラムダンク」と入力して、Enter キーを押してください。
" | .venv/bin/python browser_bot.py
