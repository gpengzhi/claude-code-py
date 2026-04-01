"""Message list widget -- displays conversation messages.

Maps to src/components/Messages.tsx and VirtualMessageList in the TypeScript codebase.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from rich.markdown import Markdown as RichMarkdown
from rich.text import Text


class MessageList(VerticalScroll):
    """Scrollable list of conversation messages."""

    can_focus = False

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._streaming_widget: Static | None = None

    def compose(self) -> ComposeResult:
        yield Static(
            Text.from_markup("[bold purple]claude-code-py[/] v0.1.0\n"
                           "Type your message below. Ctrl+C to interrupt, Ctrl+D to quit.\n"),
            classes="message-row",
        )

    def add_user_message(self, text: str) -> None:
        content = Text()
        content.append("> ", style="bold green")
        content.append(text, style="white")
        self.mount(Static(content, classes="message-row user-message"))
        self.scroll_end(animate=False)

    def add_assistant_text(self, text: str) -> None:
        try:
            md = RichMarkdown(text)
            widget = Static(md, classes="message-row assistant-message")
        except Exception:
            widget = Static(text, classes="message-row assistant-message")
        self.mount(widget)
        self.scroll_end(animate=False)

    def add_tool_use(self, tool_name: str, tool_input: dict) -> None:
        content = Text()
        content.append(f"  [{tool_name}] ", style="bold blue")
        if "command" in tool_input:
            content.append(str(tool_input["command"])[:100], style="dim")
        elif "file_path" in tool_input:
            content.append(str(tool_input["file_path"]), style="dim")
        elif "pattern" in tool_input:
            content.append(str(tool_input["pattern"]), style="dim")
        else:
            for k, v in list(tool_input.items())[:1]:
                content.append(f"{k}: {str(v)[:80]}", style="dim")
        self.mount(Static(content, classes="message-row tool-use-message"))
        self.scroll_end(animate=False)

    def add_tool_result(self, tool_use_id: str, content: str, is_error: bool = False) -> None:
        result = Text()
        if is_error:
            result.append("  Error: ", style="bold red")
            result.append(content[:500], style="red")
        else:
            display_content = content[:500]
            if len(content) > 500:
                display_content += f"\n  ... ({len(content)} chars total)"
            result.append(f"  {display_content}", style="dim")
        self.mount(Static(result, classes="message-row tool-result-message"))
        self.scroll_end(animate=False)

    def add_thinking(self, text: str) -> None:
        content = Text()
        content.append("  [thinking] ", style="bold yellow italic")
        content.append(text[:200] + ("..." if len(text) > 200 else ""), style="yellow italic")
        self.mount(Static(content, classes="message-row thinking-message"))
        self.scroll_end(animate=False)

    def add_system_message(self, text: str, level: str = "info") -> None:
        style = {"info": "dim", "warning": "yellow", "error": "red"}.get(level, "dim")
        content = Text()
        content.append(f"  {text}", style=style)
        self.mount(Static(content, classes="message-row"))
        self.scroll_end(animate=False)

    def start_streaming(self) -> None:
        """Start a new streaming assistant message."""
        self.finish_streaming()  # Clean up any previous streaming widget
        self._streaming_widget = Static("", classes="message-row assistant-message")
        self.mount(self._streaming_widget)
        self.scroll_end(animate=False)

    def update_streaming(self, text: str) -> None:
        """Update the current streaming message."""
        if self._streaming_widget is None:
            return
        try:
            md = RichMarkdown(text)
            self._streaming_widget.update(md)
        except Exception:
            self._streaming_widget.update(text)
        self.scroll_end(animate=False)

    def finish_streaming(self) -> None:
        """Finalize the streaming message."""
        self._streaming_widget = None
