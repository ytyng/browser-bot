#!/usr/bin/env zsh

# パスに登録された browser-bot のスクリプト経由で実行する



echo "
* https://www.mangazenkan.com を開いてください。

* 「マンガを検索」と書かれている、検索欄をクリックしてください。

* ポップアップされたダイアログの「漫画を検索」と書かれている検索欄に、「スラムダンク」と入力して、虫眼鏡のボタンを押してください。
" | BROWSER_USE_MAX_STEPS=10 browser-bot
