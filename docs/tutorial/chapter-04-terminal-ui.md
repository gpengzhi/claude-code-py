# Chapter 4: A Real Terminal UI

Chapters 1-3 built an agent that streams text and executes tools. But the output was plain `print()` statements. This chapter builds a real terminal UI -- with live-updating markdown, a spinner, a status bar, permission dialogs, and slash commands. We use Textual, which is essentially React for the terminal.

## What You'll Learn

- Textual framework basics (App, Screen, Widget)
- Component architecture and how pieces compose together
- Real-time streaming display (update a widget as text arrives)
- Spinner with elapsed time
- Status bar showing model, cost, and turn count
- Permission dialog for approving/denying tool execution
- Slash commands (/help, /clear, /cost)
- Wiring the async query engine to a reactive UI

## Why Textual?

Terminal UIs have been built with curses for decades. Textual replaces that with a modern model:

| Concept | React (web) | Textual (terminal) |
|---|---|---|
| Root | `<App>` | `App` |
| Pages | Routes / `<Page>` | `Screen` |
| Components | `<Component>` | `Widget` |
| Styling | CSS | CSS (yes, real CSS) |
| State updates | `setState` | `reactive` properties |
| Events | `onClick` | `on_button_pressed` |
| Layout | Flexbox | Flexbox (dock, grid) |

If you know React, you already know the mental model.

## Step 1: The Component Tree

Here's what the full UI looks like and how the widgets compose:

```
┌─ ClaudeCodeApp ──────────────────────────────────┐
│ ┌─ REPLScreen ─────────────────────────────────┐ │
│ │ ┌─ MessageList ────────────────────────────┐ │ │
│ │ │  claude-code-py v0.1.0                   │ │ │
│ │ │                                          │ │ │
│ │ │  > What files are in src/?               │ │ │
│ │ │                                          │ │ │
│ │ │  The src/ directory contains...          │ │ │
│ │ │    [Bash] ls src/                        │ │ │
│ │ │    main.py  utils.py  config.py          │ │ │
│ │ │                                          │ │ │
│ │ └──────────────────────────────────────────┘ │ │
│ │ ┌─ Spinner ────────────────────────────────┐ │ │
│ │ │  ⠹ Thinking...  (2.3s)                   │ │ │
│ │ └──────────────────────────────────────────┘ │ │
│ │ ┌─ PromptInput ────────────────────────────┐ │ │
│ │ │  > _                                     │ │ │
│ │ └──────────────────────────────────────────┘ │ │
│ │ ┌─ StatusBar ──────────────────────────────┐ │ │
│ │ │  claude-sonnet-4  |  $0.0312  |  3 turns │ │ │
│ │ └──────────────────────────────────────────┘ │ │
│ └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

In code, the tree is:

```python
ClaudeCodeApp          # Textual App (root)
  └── REPLScreen       # Screen (the only screen)
        ├── MessageList    # Scrollable conversation history
        ├── Spinner        # Activity indicator (hidden when idle)
        ├── PromptInput    # Text input with history
        └── StatusBar      # Bottom bar with session stats
```

## Step 2: The App Shell

```python
# src/tui/app.py
from textual.app import App
from textual.binding import Binding

class ClaudeCodeApp(App):
    """Root application. Manages screens and global keybindings."""

    CSS = """
    Screen { background: $surface; }
    #message-container { height: 1fr; overflow-y: auto; padding: 0 1; }
    #input-area { dock: bottom; height: auto; max-height: 40%; }
    #status-bar { dock: bottom; height: 1; }
    #spinner-area { dock: bottom; height: auto; display: none; }
    #spinner-area.visible { display: block; }
    """

    BINDINGS = [
        Binding("ctrl+c", "interrupt", "Interrupt", show=False),
        Binding("ctrl+d", "quit", "Quit", show=False),
    ]

    def __init__(self, model, system_prompt, tools, initial_prompt=None):
        super().__init__()
        self._model = model
        self._system_prompt = system_prompt
        self._tools = tools
        self._initial_prompt = initial_prompt

    async def on_mount(self):
        """Push the REPL screen when the app starts."""
        screen = REPLScreen(
            model=self._model,
            system_prompt=self._system_prompt,
            tools=self._tools,
        )
        await self.push_screen(screen)

        # Auto-submit initial prompt if provided (e.g., from CLI -p flag)
        if self._initial_prompt:
            self.set_timer(0.2, lambda: screen.post_message(
                PromptSubmitted(self._initial_prompt)
            ))
```

**Key points**:
- `CSS` is real CSS with Textual's layout properties (`dock`, `height: 1fr`)
- `BINDINGS` map keyboard shortcuts to action methods
- `on_mount` is the Textual lifecycle hook (like React's `componentDidMount`)
- The initial prompt uses `set_timer` to fire after the screen is mounted

## Step 3: The REPL Screen

This is the central hub. It wires the query engine (Chapter 3) to the UI widgets:

```python
# src/tui/screens/repl.py
from textual.screen import Screen

class REPLScreen(Screen):
    """Main interactive screen -- connects query engine to widgets."""

    def __init__(self, model, system_prompt, tools):
        super().__init__()
        self._engine = QueryEngine(model=model, system_prompt=system_prompt, tools=tools)
        self._is_querying = False
        self._streaming_text = ""
        self._current_task = None

    def compose(self):
        """Declare the widget tree. Textual calls this once on mount."""
        yield MessageList(id="message-container")
        yield Spinner(id="spinner-area")
        yield PromptInput(id="input-area")
        yield StatusBar(id="status-bar")
```

`compose()` is Textual's equivalent of React's `render()`. It returns the widget tree. Textual handles mounting, layout, and CSS application automatically.

## Step 4: Real-Time Streaming Display

When the user submits a prompt, we run the query engine and update widgets as events arrive:

```python
async def on_prompt_submitted(self, event: PromptSubmitted):
    """Handle user prompt submission."""
    text = event.text

    # Handle slash commands
    if text.startswith("/"):
        await self._handle_slash_command(text)
        return

    # Show user message in the conversation
    messages = self.query_one("#message-container", MessageList)
    messages.add_user_message(text)

    # Disable input and show spinner
    self._set_querying(True)

    # Run query in background (don't block the UI)
    self._current_task = asyncio.create_task(self._run_query(text))
```

The actual streaming happens in `_run_query`:

```python
async def _run_query(self, prompt):
    messages = self.query_one("#message-container", MessageList)
    spinner = self.query_one("#spinner-area", Spinner)
    spinner.show("Thinking...")
    self._streaming_text = ""

    try:
        async for event in self._engine.submit_message(prompt):
            if isinstance(event, AssistantMessage):
                # Streaming finished -- finalize the message
                if self._streaming_text:
                    messages.finish_streaming()
                    self._streaming_text = ""

                # Show tool use indicators
                for block in event.content:
                    if isinstance(block, ToolUseBlock):
                        messages.add_tool_use(block.name, block.input)

            elif isinstance(event, dict):
                event_type = event.get("type")

                if event_type == "stream_event":
                    # Live text chunk -- update the streaming widget
                    delta = event.get("text", "")
                    if not self._streaming_text:
                        messages.start_streaming()  # Create the widget
                    self._streaming_text += delta
                    messages.update_streaming(self._streaming_text)

                elif event_type == "tool_result_display":
                    spinner.update_text(f"Running {event.get('tool_name', 'tool')}...")

    except asyncio.CancelledError:
        messages.add_system_message("Query cancelled.", level="warning")
    finally:
        spinner.hide()
        self._set_querying(False)
        # Update status bar with latest cost/turns
        status = self.query_one("#status-bar", StatusBar)
        status.update_stats(
            cost_usd=self._engine.total_usage.cost_usd,
            turn_count=self._engine.turn_count,
        )
```

The streaming flow looks like this:

```
Engine yields:               UI does:
─────────────                ─────────
stream_event("The")    ───►  start_streaming() + update("The")
stream_event(" src/")  ───►  update("The src/")
stream_event(" dir")   ───►  update("The src/ dir")
stream_event("...")    ───►  update("The src/ dir...")
AssistantMessage       ───►  finish_streaming()
  with ToolUseBlock    ───►  add_tool_use("Bash", {command: "ls"})
tool_result_display    ───►  spinner: "Running Bash..."
stream_event("Based")  ───►  start_streaming() (new message)
stream_event("...")    ───►  update(...)
AssistantMessage       ───►  finish_streaming()
  (no tools)                 loop exits, spinner.hide()
```

**Why `start_streaming()` / `update_streaming()` / `finish_streaming()`?** We create one `Static` widget with a temporary ID (`#streaming-msg`), update its content on every chunk, then remove the ID when done. This avoids creating a new widget per character.

## Step 5: The Spinner

The spinner shows activity with an elapsed timer:

```python
# src/tui/widgets/spinner.py
SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

class Spinner(Widget):
    _visible = reactive(False)
    _text = reactive("Thinking...")

    def show(self, text="Thinking..."):
        self._text = text
        self._start_time = time.monotonic()
        self.add_class("visible")
        self._timer = self.set_interval(0.08, self._animate)

    def hide(self):
        self.remove_class("visible")
        if self._timer:
            self._timer.stop()

    def _animate(self):
        self._frame = (self._frame + 1) % len(SPINNER_FRAMES)
        elapsed = time.monotonic() - self._start_time
        frame_char = SPINNER_FRAMES[self._frame]
        # Output: "  ⠹ Thinking...  (2.3s)"
        self.query_one("#spinner-content", Static).update(
            f"  {frame_char} {self._text}  ({elapsed:.1f}s)"
        )
```

**Why 80ms interval?** Fast enough to look smooth, slow enough to not waste CPU. The Braille characters (`⠋⠙⠹...`) cycle through a pattern that looks like rotation.

## Step 6: The Status Bar

The status bar uses Textual's `reactive` properties. When a value changes, the display updates automatically:

```python
# src/tui/widgets/status_bar.py
class StatusBar(Widget):
    model: reactive[str] = reactive("claude-sonnet-4-20250514")
    cost_usd: reactive[float] = reactive(0.0)
    turn_count: reactive[int] = reactive(0)

    def watch_cost_usd(self):
        """Called automatically when cost_usd changes."""
        self._update_display()

    def _update_display(self):
        # " claude-sonnet-4  |  $0.0312  |  3 turns"
        text = Text()
        text.append(f" {self.model}", style="bold")
        text.append("  |  ", style="dim")
        text.append(f"${self.cost_usd:.4f}",
                    style="green" if self.cost_usd < 1.0 else "yellow")
        text.append("  |  ", style="dim")
        text.append(f"{self.turn_count} turns", style="dim")
        self.query_one("#status-content", Static).update(text)
```

`reactive` + `watch_*` is Textual's equivalent of React's `useState` + `useEffect`. You set the value, and the framework calls your watcher. No manual re-rendering needed.

## Step 7: The Permission Dialog

Write tools (Bash, Edit, Write) need user approval. The dialog shows what the tool wants to do and offers three options:

```python
# src/tui/widgets/permission_dialog.py
class PermissionDialog(Widget):
    def show_permission(self, tool_use_id, tool_name, tool_input):
        """Show: 'Allow Bash? Command: rm -rf node_modules'"""
        self.query_one("#perm-title").update(f"Allow {tool_name}?")

        # Show the relevant detail
        if "command" in tool_input:
            detail = f"Command: {tool_input['command']}"
        elif "file_path" in tool_input:
            detail = f"File: {tool_input['file_path']}"

        self.query_one("#perm-detail").update(detail)
        self.add_class("visible")

    def on_key(self, event):
        """Keyboard shortcuts: y=allow, a=always, n=deny"""
        if event.key == "y":
            self.post_message(PermissionResponse(self._tool_use_id, allowed=True))
        elif event.key == "a":
            self.post_message(PermissionResponse(
                self._tool_use_id, allowed=True, always_allow=True
            ))
        elif event.key == "n":
            self.post_message(PermissionResponse(self._tool_use_id, allowed=False))
        self.hide_permission()
```

```
┌─────────────────────────────────────────────────┐
│  Allow Bash?                                    │
│  Command: rm -rf node_modules                   │
│                                                 │
│  [Allow (y)]  [Always Allow (a)]  [Deny (n)]   │
└─────────────────────────────────────────────────┘
```

**Three options, not two.** "Always Allow" remembers the decision for the rest of the session, so you don't have to approve every `Read` or `ls` call. The permission state lives in the `ToolUseContext` from Chapter 2.

## Step 8: Slash Commands

Slash commands are handled before the query engine. They never go to the model:

```python
async def _handle_slash_command(self, text):
    """Route /commands to their handlers."""
    parts = text.strip().split(None, 1)
    cmd_name = parts[0].lstrip("/").lower()  # "/help" -> "help"
    cmd_args = parts[1] if len(parts) > 1 else ""

    cmd = get_command(cmd_name)
    if cmd is None:
        messages.add_system_message(f"Unknown command: /{cmd_name}")
        return

    result = await cmd.handler(engine=self._engine, args=cmd_args)

    if result.message == "__quit__":
        self.app.exit()
        return
    if cmd_name == "clear":
        for child in list(messages.children):
            child.remove()
    if result.message:
        messages.add_system_message(result.message)
```

Common commands:

| Command | What it does |
|---|---|
| `/help` | List available commands |
| `/clear` | Clear the message display |
| `/cost` | Show total token usage and cost |
| `/compact` | Force a context compaction |
| `/model` | Show or switch the current model |
| `/quit` | Exit the application |

## Step 9: Wiring Async Engine to Reactive UI

The trickiest part is connecting an `async for` loop (the query engine) to Textual's event-driven UI. The key is `asyncio.create_task`:

```python
# When user submits a prompt:
self._current_task = asyncio.create_task(self._run_query(text))

# When user presses Ctrl+C:
def cancel_query(self):
    if self._current_task and not self._current_task.done():
        self._engine.abort()          # Signal the query loop to stop
        self._current_task.cancel()   # Cancel the asyncio task
```

```
Textual Event Loop (runs forever)
    │
    ├── UI events (key presses, mouse clicks, redraws)
    │
    ├── Timer callbacks (spinner animation every 80ms)
    │
    └── Background tasks
         └── _run_query()
              │
              async for event in engine.submit_message():
              │   ├── Update MessageList widget
              │   ├── Update Spinner text
              │   └── Update StatusBar stats
              │
              (all widget updates happen on the event loop,
               so they're thread-safe by default)
```

Textual runs on a single asyncio event loop. Both UI events and our query engine share this loop. When `_run_query` does `await`, control returns to Textual so it can process UI events (like Ctrl+C). This is cooperative multitasking -- no threads, no locks, no race conditions.

## Try It

```bash
pip install textual
python -m claude_code --model claude-sonnet-4-20250514
```

You should see:
1. The styled welcome message
2. A prompt input with `> ` prefix
3. A status bar at the bottom
4. Live streaming text as the model responds
5. Spinner with elapsed time during tool execution

Try typing `/help` to see available commands, or ask it to read a file to see the tool approval dialog.

## What Just Happened

```
App starts
    │
    ├── ClaudeCodeApp.__init__()
    │       stores model, tools, prompt
    │
    ├── on_mount()
    │       pushes REPLScreen
    │
    ├── REPLScreen.compose()
    │       creates MessageList, Spinner, PromptInput, StatusBar
    │
    ├── User types "Read agent.py" + Enter
    │       │
    │       ├── PromptInput fires PromptSubmitted
    │       ├── REPLScreen.on_prompt_submitted()
    │       │     adds user message to MessageList
    │       │     creates background task: _run_query()
    │       │
    │       ├── _run_query() iterates engine events:
    │       │     stream_event → update streaming widget
    │       │     AssistantMessage → finish streaming, show tool_use
    │       │     tool_result → update spinner text
    │       │     (loops until no more tool_use)
    │       │
    │       └── finally: hide spinner, update status bar
    │
    └── User presses Ctrl+D → app.exit()
```

## Code Reference

The production version of this chapter lives in:
- [`src/claude_code/tui/app.py`](../../src/claude_code/tui/app.py) -- App shell, CSS, keybindings
- [`src/claude_code/tui/screens/repl.py`](../../src/claude_code/tui/screens/repl.py) -- REPL screen (the central hub)
- [`src/claude_code/tui/widgets/message_list.py`](../../src/claude_code/tui/widgets/message_list.py) -- Conversation display with streaming
- [`src/claude_code/tui/widgets/spinner.py`](../../src/claude_code/tui/widgets/spinner.py) -- Animated spinner with elapsed time
- [`src/claude_code/tui/widgets/status_bar.py`](../../src/claude_code/tui/widgets/status_bar.py) -- Reactive status bar
- [`src/claude_code/tui/widgets/prompt_input.py`](../../src/claude_code/tui/widgets/prompt_input.py) -- Input with history

---

**[← Chapter 3: The Agentic Loop](chapter-03-agentic-loop.md) | [Chapter 5: Context Engineering →](chapter-05-context-engineering.md)**
