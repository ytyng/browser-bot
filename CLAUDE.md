# Browser Bot - Claude Code Development Guide

This document is a guide for developing and maintaining the Browser Bot project with Claude Code.

## Project Overview

Browser Bot is an MCP (Model Context Protocol) server that automates the Chrome browser. Using the browser_use library, it can perform browser operations from natural-language instructions.

### Main features

- **Browser automation**: Perform browser operations from natural-language instructions
- **Screenshots**: Screenshots of the visible area or the full page
- **Source retrieval**: The HTML source of the currently displayed page
- **Multiple LLMs**: Supports OpenAI GPT and Google Gemini

## Architecture

### Core components

- **browser_bot.py**: The main operation execution engine
- **mcp_server.py**: MCP protocol implementation and tool definitions
- **launch-mcp-server.sh**: MCP server launch script
- **launch-chrome.sh**: Chrome launch script

### Dependencies

- **browser_use**: Browser automation library
- **fastmcp**: MCP server implementation framework
- **langchain_openai**: OpenAI LLM integration
- **langchain_google_genai**: Google Gemini LLM integration
- **playwright**: Browser control
- **httpx**: HTTP client
- **pillow**: Image processing
- **pydantic**: Data validation

## Key Points for Development

### 1. Logging

- All logs are written to `/tmp/browser-bot.log`
- The MCP server does not write logs to stdout (it would interfere with stdio communication)
- The log level is controlled with the environment variable `BROWSER_USE_LOGGING_LEVEL=result`

### 2. Error handling

- Proper handling of Chrome connection errors
- Detailed logging of task execution errors
- User-friendly error messages

### 3. MCP protocol support

- Initialization sequence: `initialize` → `notifications/initialized` → `tools/list`
- Detailed parameter descriptions using Pydantic Field
- Input validation with JSON Schema
- Implements 4 MCP tools:
  - `browser_use_local_chrome_9222`: Browser automation
  - `get_page_source`: Get the HTML source
  - `get_visible_screenshot`: Screenshot of the visible area
  - `get_full_screenshot`: Screenshot of the full page

## Coding Conventions

### 1. Code style

- Lint and format with **ruff** (maximum line length: 79 characters)
- See `[tool.ruff]` in `pyproject.toml` for the rule settings
- Type hints are required (typing, Annotated, Pydantic Field)

### 2. File layout

```python
# Import order
import os
import sys
from typing import Annotated

from dotenv import load_dotenv
from pydantic import Field
import fastmcp

from browser_bot import run_task, logger
```

### 3. Function design

- Use keyword-only arguments (the `*` parameter)
- Proper use of async/await
- Detailed documentation

## Testing Procedure

### 1. Development environment setup

```bash
# Install dependencies
uv sync

# Launch Chrome
./launch-chrome.sh

# Check environment variables
cat .env  # OPENAI_API_KEY or GOOGLE_API_KEY must be set
```

### 2. Running tests

```bash
# Initialization test
./tests/test-mcp-initialize.sh

# Tool list test
./tests/test-mcp-tools-list.sh

# Direct execution test
./tests/test-run.sh

# Execution-via-path test
./tests/test-run-with-path.sh
```

### 3. MCP server test

```bash
# Start the server
./launch-mcp-server.sh

# Client test in another terminal
./tests/test-mcp-tools-list.sh
```

## Debugging

### 1. Checking logs

```bash
# Watch the log in real time
tail -f /tmp/browser-bot.log
```

### 2. Chrome debugging

```bash
# Check Chrome's status
curl http://localhost:9222/json/version

# List active tabs
curl http://localhost:9222/json
```

### 3. MCP protocol debugging

```bash
# Inspect JSON-RPC messages
echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {...}}' | ./launch.sh
```

## Common Problems and Solutions

### 1. Chrome connection error

**Problem**: `Chrome が :9222 で起動していません` (the app's Japanese error message: "Chrome is not running on :9222")

**Solution**:
```bash
# Quit the existing Chrome
pkill -f chrome
# Restart it with the debugging port
./launch-chrome.sh
```

### 2. MCP server error

**Problem**: `Invalid request parameters`

**Solution**:
- Check the order `initialize` → `notifications/initialized`
- Check the format of the JSON-RPC messages

### 3. LLM connection error

**Problem**: OpenAI or Google API connection error

**Solution**:
- Check the API key in the `.env` file
- Check that the model name is correct (e.g. `gemini-2.5-flash`)
- Check that you have not hit a usage limit

### 4. Task execution failure

**Problem**: The task ends partway because of the `max_steps` limit

**Solution**:
- Increase the `max_steps` parameter
- Describe the task more specifically

## Performance Optimization

### 1. Adjusting the number of steps

- Simple operations: 3-5 steps
- Moderate operations: 5-10 steps
- Complex operations: 10-15 steps

### 2. Adjusting the log level

```python
# Development: DEBUG
# Production: INFO or WARNING
```

### 3. Timeout settings

```python
# Chrome connection timeout: 5 seconds
# Agent execution: depends on max_steps
```

## Extension Points

### 1. Adding new features

- Define the new tool in `mcp_server.py`
- Add the implementation logic to `browser_bot.py`
- Create a test script
- Add new dependencies to `pyproject.toml` as needed

### 2. Stronger error handling

- More detailed error classification
- Implement retries
- Error recovery

### 3. Performance improvements

- Parallel execution support
- Caching
- Browser pool management

## Release Procedure

### 1. Code quality checks

```bash
# Update dependencies
uv sync

# Lint and format
uv run ruff check --fix .
uv run ruff format .

# Run tests
./tests/test-mcp-initialize.sh
./tests/test-mcp-tools-list.sh
./tests/test-run.sh
```

### 2. Updating documentation

- Update the usage examples in README.md
- Update the development guide in CLAUDE.md
- Comments and documentation

### 3. Dependency management

```bash
# Add a new dependency
uv add <package_name>

# Add a development dependency
uv add --dev <package_name>

# Update the lock file
uv lock

# Sync
uv sync
```

## Security Considerations

### 1. API key management

- Add the `.env` file to `.gitignore`
- Manage API keys through environment variables
- Do not write secret information to logs

### 2. Browser security

- Restrict external access to the debugging port
- Control access to untrusted sites
- Running in a sandboxed environment is recommended

### 3. Input validation

- Strict input validation with Pydantic Field
- Countermeasures against vulnerabilities such as SQL injection
- Prevent execution of malicious scripts

## Troubleshooting

### Development environment

- Check the Python version: 3.12+
- Check the Chrome version: the latest version is recommended
- Check for port conflicts: 9222 must be free

### Production environment

- Monitor the log file size
- Monitor memory usage
- Check the stability of the Chrome process

Use this guide for safe and efficient development.
