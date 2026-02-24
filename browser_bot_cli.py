#!/usr/bin/env python3
"""
browser-bot CLI - Chrome ブラウザ自動操作の CLI インターフェイス

MCP サーバーと同じ機能をコマンドラインから利用可能にする。
"""
import argparse
import asyncio
import base64
import json
import sys

from browser_bot import (
    BrowserBotError,
    get_current_url,
    get_full_screenshot,
    get_page_source,
    get_visible_screenshot,
    launch_chrome,
    request,
    run_lighthouse,
    run_python_script,
    run_script,
    run_task,
    super_reload,
)


def _read_stdin_or_exit(label: str) -> str:
    """stdin からテキストを読み取り、空なら終了する"""
    if sys.stdin.isatty():
        print(
            f"Error: {label} を標準入力から渡してください",
            file=sys.stderr,
        )
        sys.exit(1)
    text = sys.stdin.read().strip()
    if not text:
        print(
            f"Error: {label} が空です",
            file=sys.stderr,
        )
        sys.exit(1)
    return text


def _print_json(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


# -- subcommand handlers --

def cmd_browser_use(args):
    task_text = _read_stdin_or_exit("タスクテキスト")
    result = asyncio.run(
        run_task(
            task=task_text,
            max_steps=args.max_steps,
            url=args.url,
        )
    )
    print(str(result))


def cmd_get_source(args):
    result = asyncio.run(get_page_source(url=args.url))
    _print_json(result)


def cmd_visible_screenshot(args):
    result = asyncio.run(
        get_visible_screenshot(
            url=args.url,
            page_y_offset_as_viewport_height=(
                args.scroll
            ),
            include_image_binary=False,
        )
    )
    _print_json(result)


def cmd_full_screenshot(args):
    result = asyncio.run(
        get_full_screenshot(
            url=args.url,
            include_image_binary=False,
        )
    )
    _print_json(result)


def cmd_run_js(args):
    script = _read_stdin_or_exit("JavaScript コード")
    result = asyncio.run(run_script(script=script, url=args.url))
    _print_json({"message": "OK", "result": result})


def cmd_python_script(args):
    script = _read_stdin_or_exit("Python スクリプト")
    result = asyncio.run(
        run_python_script(python_script_text=script, url=args.url)
    )
    if result is not None:
        print(result)


def cmd_current_url(args):
    result = asyncio.run(get_current_url())
    _print_json(result)


def cmd_super_reload(args):
    result = asyncio.run(
        super_reload(url=args.url, mode=args.mode)
    )
    _print_json(result)


def cmd_launch_chrome(args):
    result = asyncio.run(
        launch_chrome(as_guest=not args.no_guest)
    )
    _print_json(result)


def cmd_http_request(args):
    kwargs = {}
    if args.headers:
        kwargs["headers"] = json.loads(args.headers)

    # data: stdin があれば読み取る
    if not sys.stdin.isatty():
        data = sys.stdin.read()
        if data.strip():
            kwargs["data"] = data

    response_data = asyncio.run(
        request(
            method=args.method,
            url=args.request_url,
            preload_url=args.preload_url,
            **kwargs,
        )
    )

    body = response_data['body']
    content_type = response_data['headers'].get("content-type", "")
    if "text" in content_type or "json" in content_type:
        body_text = body.decode('utf-8', errors='replace')
    else:
        body_text = base64.b64encode(body).decode('utf-8')

    _print_json({
        "status": response_data['status'],
        "headers": response_data['headers'],
        "body": body_text,
    })


def cmd_lighthouse(args):
    categories = None
    if args.categories:
        categories = [c.strip() for c in args.categories.split(',')]

    result = asyncio.run(
        run_lighthouse(
            url=args.url,
            categories=categories,
            device=args.device,
            timeout_seconds=args.timeout,
        )
    )
    _print_json(result)


def build_parser():
    parser = argparse.ArgumentParser(
        prog='browser-bot-cli',
        description=(
            'Chrome ブラウザ自動操作 CLI。'
            'MCP サーバーと同じ機能をコマンドラインから利用できます。'
        ),
    )

    sub = parser.add_subparsers(dest='command')

    # browser-use
    p = sub.add_parser(
        'browser-use',
        help='browser_use でブラウザ操作タスクを実行 (stdin: タスク)',
    )
    p.add_argument('--max-steps', type=int, default=7)
    p.add_argument('--url', type=str, default=None)
    p.set_defaults(func=cmd_browser_use)

    # get-source
    p = sub.add_parser(
        'get-source',
        help='ページの HTML ソースを取得して Downloads に保存',
    )
    p.add_argument('--url', type=str, default=None)
    p.set_defaults(func=cmd_get_source)

    # visible-screenshot
    p = sub.add_parser(
        'visible-screenshot',
        help='表示領域のスクリーンショットを取得',
    )
    p.add_argument('--url', type=str, default=None)
    p.add_argument(
        '--scroll', type=float, default=0.0,
        help='ビューポート高さの倍率でスクロール (例: 1.0=1ページ分)',
    )
    p.set_defaults(func=cmd_visible_screenshot)

    # full-screenshot
    p = sub.add_parser(
        'full-screenshot',
        help='ページ全体のスクリーンショットを取得',
    )
    p.add_argument('--url', type=str, default=None)
    p.set_defaults(func=cmd_full_screenshot)

    # run-js
    p = sub.add_parser(
        'run-js',
        help='JavaScript を実行 (stdin: JS コード)',
    )
    p.add_argument('--url', type=str, default=None)
    p.set_defaults(func=cmd_run_js)

    # python-script
    p = sub.add_parser(
        'python-script',
        help='Playwright Python スクリプトを実行 (stdin: コード)',
    )
    p.add_argument('--url', type=str, default=None)
    p.set_defaults(func=cmd_python_script)

    # current-url
    p = sub.add_parser(
        'current-url',
        help='アクティブタブの URL とタイトルを取得',
    )
    p.set_defaults(func=cmd_current_url)

    # super-reload
    p = sub.add_parser(
        'super-reload',
        help='キャッシュ無視でページをリロード',
    )
    p.add_argument('--url', type=str, default=None)
    p.add_argument(
        '--mode', type=str, default='cdp',
        choices=['cdp', 'javascript', 'keyboard'],
    )
    p.set_defaults(func=cmd_super_reload)

    # launch-chrome
    p = sub.add_parser(
        'launch-chrome',
        help='Chrome をデバッグポート付きで起動',
    )
    p.add_argument(
        '--no-guest', action='store_true',
        help='通常モードで起動 (デフォルトはゲストモード)',
    )
    p.set_defaults(func=cmd_launch_chrome)

    # http-request
    p = sub.add_parser(
        'http-request',
        help='ブラウザセッションで HTTP リクエスト送信 (stdin: body)',
    )
    p.add_argument('request_url', help='リクエスト先 URL')
    p.add_argument(
        '--method', type=str, default='get',
        choices=[
            'get', 'post', 'put', 'delete',
            'patch', 'head', 'options',
        ],
    )
    p.add_argument('--preload-url', type=str, default=None)
    p.add_argument(
        '--headers', type=str, default=None,
        help='HTTP ヘッダー (JSON 文字列)',
    )
    p.set_defaults(func=cmd_http_request)

    # lighthouse
    p = sub.add_parser(
        'lighthouse',
        help='Lighthouse パフォーマンス監査を実行',
    )
    p.add_argument('--url', type=str, default=None)
    p.add_argument(
        '--categories', type=str, default=None,
        help='カンマ区切り (例: performance,accessibility)',
    )
    p.add_argument(
        '--device', type=str, default='desktop',
        choices=['desktop', 'mobile'],
    )
    p.add_argument('--timeout', type=int, default=120)
    p.set_defaults(func=cmd_lighthouse)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    try:
        args.func(args)
    except BrowserBotError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
