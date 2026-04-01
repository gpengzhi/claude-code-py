# Conformance Test Suite

Behavioral conformance tests that verify claude-code-py matches Claude Code's behavior.

## Approach

The suite tests **observable behavior**, not implementation details:

1. **Tool schema conformance** -- Do our tools produce the same JSON schemas sent to the API?
2. **Tool invocation conformance** -- Given the same tool_use input, do tools produce equivalent results?
3. **System prompt conformance** -- Does our system prompt contain the same key sections?
4. **Query loop conformance** -- Does the agentic loop handle tool_use/tool_result cycling correctly?
5. **Config conformance** -- Do we read the same settings files in the same precedence order?

## Running

```bash
# Run all conformance tests
python -m pytest conformance/ -v

# Run a specific category
python -m pytest conformance/ -v -k "tool_schema"
```

## What we compare

For each test, we capture:
- **API request params** -- model, tools, system prompt structure
- **Tool schemas** -- input_schema JSON sent to the API
- **Tool behavior** -- output given specific inputs
- **Message format** -- how messages are serialized for the API
- **File format compatibility** -- settings.json, MEMORY.md, session JSONL
