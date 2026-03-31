# claude-code-py

A Python reimplementation of [Claude Code](https://claude.ai/code) -- Anthropic's CLI coding agent.

## Installation

```bash
pip install claude-code-py
```

Or from source:

```bash
git clone https://github.com/anthropics/claude-code-py.git
cd claude-code-py
pip install -e ".[dev]"
```

## Usage

### Non-interactive (print) mode

```bash
export ANTHROPIC_API_KEY=your-key-here
claude-code-py -p "What is 2+2?"
```

### Interactive REPL

```bash
claude-code-py
```

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check src/ tests/
mypy src/
```

## Architecture

This is a faithful Python port of Claude Code's TypeScript codebase, using:

- **asyncio** for concurrency
- **Textual** for terminal UI (replaces Ink/React)
- **Click** for CLI (replaces Commander.js)
- **Pydantic** for schemas (replaces Zod)
- **anthropic** Python SDK for API calls

## License

MIT
