#!/usr/bin/env zsh

# home-files/bin/browser-bot のパスに登録されたスクリプト経由で実行する

echo "
* https://www.mangazenkan.com を開いてください。

* 「マンガを検索」と書かれている、検索欄をクリックしてください。

* ポップアップされたダイアログの「漫画を検索」と書かれている検索欄に、「スラムダンク」と入力して、Enter キーを押してください。
" | browser-bot
