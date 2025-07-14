#!/usr/bin/env zsh

cd $(dirname $0)/../

echo "
await asyncio.sleep(3)

await page.click('.header .search-form input.header-search-input')
await page.fill(
    '#search-modal-input',
    "ハイキュー",
)

await asyncio.sleep(1)
await page.click('button[data-annotate=\"search-submit-button\"]')

await asyncio.sleep(2)

return f'完了しました。 URL: {page.url}'
" | .venv/bin/python browser_bot.py --python-script --url https://www.mangazenkan.com
