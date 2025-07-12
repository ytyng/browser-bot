#!/usr/bin/env zsh

cd $(dirname $0)/../

echo "
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

document.querySelector('.header .search-form input.header-search-input').click();
await sleep(1000);

document.querySelector('#search-modal-input').value = 'ハイキュー';
await sleep(1000);

document.querySelector('#search-modal-input').dispatchEvent(new Event('input', { bubbles: true }));
await sleep(1000);

document.querySelector('button[data-annotate=\"search-submit-button\"]').click();
await sleep(2000);

return '完了しました。 URL: ' + window.location.href;
" | .venv/bin/python browser_bot.py --script --url https://www.mangazenkan.com
