"""WebFetchTool -- Fetch URL content and process it.

"""

from __future__ import annotations

import html
import logging
import re

from pydantic import BaseModel, Field

from claude_code.tool.base import Tool, ToolResult, ToolUseContext

logger = logging.getLogger(__name__)

MAX_CONTENT_LENGTH = 500_000  # 500KB text limit


def strip_html_tags(html_content: str) -> str:
    """Convert HTML to plain text by stripping tags."""
    # Remove script and style elements entirely
    text = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Replace common block elements with newlines
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|h[1-6]|li|tr|blockquote)>", "\n", text, flags=re.IGNORECASE)
    # Remove all remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode HTML entities
    text = html.unescape(text)
    # Collapse excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


class WebFetchInput(BaseModel):
    url: str = Field(description="The URL to fetch content from")
    prompt: str = Field(description="The prompt to process the fetched content with")


class WebFetchTool(Tool):
    name = "WebFetch"
    aliases = ["web_fetch", "fetch"]
    input_model = WebFetchInput
    max_result_size_chars = MAX_CONTENT_LENGTH

    def get_description(self) -> str:
        return "Fetches content from a URL and processes it."

    def get_prompt(self) -> str:
        return (
            "Fetches content from a specified URL and processes it.\n"
            "- Takes a URL and a prompt as input\n"
            "- Fetches the URL content, converts HTML to text\n"
            "- Returns the content for analysis\n"
            "- The URL must be a fully-formed valid URL\n"
            "- HTTP URLs will be automatically upgraded to HTTPS"
        )

    def is_read_only(self, input_data: BaseModel) -> bool:
        return True

    def is_concurrency_safe(self, input_data: BaseModel) -> bool:
        return True

    async def call(
        self,
        args: BaseModel,
        context: ToolUseContext,
    ) -> ToolResult:
        assert isinstance(args, WebFetchInput)

        url = args.url.strip()
        if not url:
            return ToolResult(data="Error: url is required", is_error=True)

        # Upgrade HTTP to HTTPS
        if url.startswith("http://"):
            url = "https://" + url[7:]
        elif not url.startswith("https://"):
            url = "https://" + url

        try:
            import aiohttp
        except ImportError:
            return ToolResult(
                data="Error: aiohttp is required for WebFetchTool. Install with: pip install aiohttp",
                is_error=True,
            )

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    url,
                    headers={"User-Agent": "Claude-Code/1.0"},
                    allow_redirects=True,
                ) as response:
                    if response.status != 200:
                        return ToolResult(
                            data=f"HTTP {response.status} error fetching {url}",
                            is_error=True,
                        )

                    content_type = response.headers.get("Content-Type", "")
                    raw = await response.text(errors="replace")

                    # Convert HTML to text
                    if "html" in content_type.lower():
                        text = strip_html_tags(raw)
                    else:
                        text = raw

                    # Truncate if needed
                    if len(text) > MAX_CONTENT_LENGTH:
                        text = text[:MAX_CONTENT_LENGTH] + "\n\n[Content truncated]"

                    return ToolResult(
                        data=f"URL: {url}\nPrompt: {args.prompt}\n\nContent:\n{text}"
                    )

        except Exception as e:
            logger.error("WebFetchTool error: %s", e)
            return ToolResult(
                data=f"Error fetching URL {url}: {e}",
                is_error=True,
            )
