#!/usr/bin/env zsh

cd $(dirname $0)/../

# echo "
# console.log('Hello, world!');
# return `script completed. ${window.location.href}`;
# " | .venv/bin/python browser_bot.py --script --url https://www.example.com

echo "
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));
console.log('Hello, world!');
await sleep(100);
return \`Hello, world! Current URL: \${window.location.href}\`;
" | .venv/bin/python browser_bot.py --script --url https://www.example.com
