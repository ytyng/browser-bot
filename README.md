# Browser Bot

![](./documents/images/featured-image.png)

An MCP (Model Context Protocol) server for automating Chrome browser operations. It connects to a locally running Chrome instance (:9222) using the browser_use library to automate web browser interactions.

## Features

- **Browser Automation**: Execute browser operations via natural language instructions
- **Screenshot Capture**: Take screenshots of the visible area or the entire page
- **Source Code Retrieval**: Get the HTML source of the currently displayed page
- **MCP Protocol Support**: Operable from AI assistants such as Claude

## Requirements

- Python 3.12+
- Chrome browser
- OpenAI API key or Google API key (when using Gemini)
- uv (Python package manager)

## Installation and Setup

### 1. Install Dependencies

```shell
uv sync
```

### 2. Configure Environment Variables

Create a `.env` file with the following settings:

#### Using OpenAI

```env
OPENAI_API_KEY=your_openai_api_key_here
# Default model is gpt-5-mini
# Set BROWSER_USE_LLM_MODEL to use a different model
# BROWSER_USE_LLM_MODEL=gpt-4o
```

#### Using Google Gemini

```env
GOOGLE_API_KEY=your_google_api_key_here
BROWSER_USE_LLM_MODEL=gemini-2.5-flash
```

### 3. Launch Chrome

Start Chrome with the debug port enabled:

```shell
./launch-chrome.sh
```

## Usage

### As an MCP Server

```shell
./launch-mcp-server.sh
```

### Direct Execution

Register the following script in your PATH:

browser-bot
```shell
#!/usr/bin/env zsh

cd ${HOME}/<your-workspace>/browser-bot
.venv/bin/python3 ./browser_bot.py
```

```shell
echo "Open https://www.google.com and search for 'Python tutorial'" | browser-bot
```

## MCP Tool Specifications

### 1. browser_use_local_chrome_9222

Executes automated operations in the Chrome browser.

#### Parameters

- **task_text** (str, required): Detailed description of the browser operation task to execute
- **max_steps** (int, optional): Maximum number of execution steps (default: 7, range: 1-30)

### 2. get_page_source

Retrieves the source code of the currently active tab. Use this when you want to analyze the HTML structure of a page.

### 3. get_visible_screenshot

Takes a screenshot of the visible area of the currently active tab. Use this to check the current state of what's displayed.

### 4. get_full_screenshot

Takes a screenshot of the entire page of the currently active tab. Use this to check the overall page layout.

#### Tips for Writing Tasks

1. **Use fully qualified URLs**
   - ✅ `https://example.com`
   - ❌ `example.com`

2. **Describe click targets specifically**
   - ✅ `the blue button labeled 'Submit'`
   - ❌ `the button`

3. **Specify input content clearly**
   - ✅ `type 'test@example.com' in the email field`
   - ❌ `enter the email address`

4. **List multiple operations in order using bullet points**

#### Examples

**Simple search operation (3-5 steps):**
```
Open https://www.google.com, type 'Python tutorial' in the search box, and click the search button
```

**Form input operation (5-10 steps):**
```
On the current page, fill in the contact form: enter 'Taro Yamada' in the name field, 'yamada@example.com' in the email field, and 'This is a test message' in the message field, then click the submit button
```

**Complex operation (10-15 steps):**
```
Open https://www.amazon.co.jp, type 'Python programming' in the search box, execute the search, then click the first search result
```

## File Structure

```
browser-bot/
├── browser_bot.py              # Main operation execution engine
├── mcp_server.py              # MCP server implementation
├── launch-mcp-server.sh       # MCP server launch script
├── launch-chrome.sh           # Chrome launch script (with debug port)
├── pyproject.toml             # Project configuration and dependencies
├── uv.lock                    # Dependency lock file
├── tests/                     # Test scripts
│   ├── test-mcp-initialize.sh
│   ├── test-mcp-tools-list.sh
│   ├── test-run.sh
│   └── test-run-with-path.sh
├── README.md
└── CLAUDE.md
```

## Dependencies

- **browser-use**: Browser automation library
- **fastmcp**: MCP server implementation framework
- **langchain_openai**: OpenAI LLM integration
- **langchain_google_genai**: Google Gemini LLM integration
- **playwright**: Browser control
- **httpx**: HTTP client
- **pillow**: Image processing
- **python-dotenv**: Environment variable management

## Logging

All logs are recorded in the following file:

- **Log file**: `/tmp/browser-bot.log`

Note: The MCP server does not output logs to stdout (to avoid interfering with stdio communication).

## Testing

### Initialization Test
```bash
./tests/test-mcp-initialize.sh
```

### Tool List Test
```bash
./tests/test-mcp-tools-list.sh
```

### Direct Execution Test
```bash
./tests/test-run.sh
```

### PATH Execution Test
```bash
./tests/test-run-with-path.sh
```

## Troubleshooting

### Chrome Won't Start

1. Quit Chrome if it's already running
2. Run `./launch-chrome.sh`
3. Make sure port 9222 is not in use

### MCP Server Errors

1. Verify that `OPENAI_API_KEY` is set in the `.env` file
2. Confirm Chrome is running with the debug port enabled
3. Check the log file (`/tmp/browser-bot.log`)

### Operations Stop Midway

- Try increasing the `max_steps` parameter
- Write more specific task descriptions

### Super Reload Not Working as Expected

Browser Bot implements super reload (cache-ignoring reload) using multiple methods:

1. **super_reload**: 3-stage fallback approach
   - Chrome DevTools Protocol (CDP) (most reliable)
   - Keyboard shortcut (Ctrl+Shift+R / Cmd+Shift+R)
   - Normal reload (fallback)

2. **force_reload_with_javascript**: Forced reload via JavaScript
   - Uses `location.reload(true)`
   - Reload with cache-busting timestamp

Either method ensures the cache is cleared reliably.
