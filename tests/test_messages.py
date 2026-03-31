"""Tests for message types."""

from claude_code.types.message import (
    AssistantMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    UserMessage,
    Usage,
    make_uuid,
)


def test_text_block():
    block = TextBlock(text="hello")
    assert block.type == "text"
    assert block.text == "hello"


def test_tool_use_block():
    block = ToolUseBlock(id="123", name="bash", input={"command": "ls"})
    assert block.type == "tool_use"
    assert block.name == "bash"
    assert block.input == {"command": "ls"}


def test_tool_result_block():
    block = ToolResultBlock(tool_use_id="123", content="output", is_error=False)
    assert block.type == "tool_result"
    assert block.tool_use_id == "123"


def test_user_message():
    msg = UserMessage(content="hello")
    assert msg.role == "user"
    assert msg.uuid  # Should have auto-generated UUID


def test_assistant_message():
    msg = AssistantMessage(
        content=[TextBlock(text="hello")],
        model="claude-sonnet-4-20250514",
    )
    assert msg.role == "assistant"
    assert len(msg.content) == 1
    assert msg.cost_usd == 0.0


def test_usage():
    usage = Usage(input_tokens=100, output_tokens=50)
    assert usage.input_tokens == 100
    assert usage.cost_usd == 0.0


def test_make_uuid():
    id1 = make_uuid()
    id2 = make_uuid()
    assert id1 != id2
    assert len(id1) == 36  # UUID format
