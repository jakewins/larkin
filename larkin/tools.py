import dataclasses
import inspect
import io
import json
import os
import re
import typing as t

import httpx
import markdownify
import markitdown

from larkin import models

MAX_TOOL_OUTPUT = 30_000


# ---------------------------------------------------------------------------
# Tool introspection and doc generation
# ---------------------------------------------------------------------------


class ToolFunction(t.Protocol):
    __name__: str

    def __call__(self, *args: t.Any, **kwargs: t.Any) -> t.Any: ...


@dataclasses.dataclass
class ToolInfo:
    name: str
    params: list[tuple[str, str]]
    return_annotation: str | None
    docstring: str


def _annotation_str(annotation: t.Any) -> str:
    """Convert a type annotation to a readable string."""
    if annotation is inspect.Parameter.empty:
        return "Any"
    # Generic aliases like list[str], dict[str, int] — use their string repr
    if hasattr(annotation, "__args__"):
        return str(annotation).replace("typing.", "")
    if hasattr(annotation, "__name__"):
        return annotation.__name__
    return str(annotation).replace("typing.", "")


def tool_info(fn: ToolFunction) -> ToolInfo:
    """Extract metadata from a tool function using inspect."""
    sig = inspect.signature(fn)
    hints = t.get_type_hints(fn)

    params: list[tuple[str, str]] = []
    for name, param in sig.parameters.items():
        annotation = hints.get(name, param.annotation)
        params.append((name, _annotation_str(annotation)))

    ret = hints.get("return", sig.return_annotation)
    return_annotation = None if ret is inspect.Parameter.empty else _annotation_str(ret)

    docstring = inspect.getdoc(fn) or ""

    return ToolInfo(
        name=fn.__name__,
        params=params,
        return_annotation=return_annotation,
        docstring=docstring,
    )


def generate_tool_docs(tools: list[ToolFunction]) -> str:
    """Generate Starlark-style documentation for a list of tool functions."""
    parts: list[str] = []
    for fn in tools:
        info = tool_info(fn)

        param_str = ", ".join(f"{name}: {typ}" for name, typ in info.params)
        ret = f" -> {info.return_annotation}" if info.return_annotation else ""
        signature = f"def {info.name}({param_str}){ret}:"

        doc_lines = info.docstring.strip().splitlines()
        indented_doc = "\n".join(
            f"    {line}" if line.strip() else "" for line in doc_lines
        )
        parts.append(f"{signature}\n    '''\n{indented_doc}\n    '''")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Built-in tool functions
# ---------------------------------------------------------------------------


class WebSearchEntry(t.TypedDict):
    title: str
    url: str
    content: str


def visit_webpage(url: str) -> str:
    """Visit a webpage, return its contents as a markdown string."""
    res = httpx.get(url)
    if res.status_code < 200 or res.status_code > 299:
        return f"[visit_webpage()]: HTTP {res.status_code}"
    mk_content = markdownify.markdownify(res.text)
    if len(mk_content) > MAX_TOOL_OUTPUT:
        mk_content = mk_content[:MAX_TOOL_OUTPUT]
        mk_content += f"\n[..]\n_[visit_webpage()]: This page has been truncated to stay below {MAX_TOOL_OUTPUT} characters._\n"
    return mk_content


def download_pdf(url: str) -> str:
    """Fetch a PDF and return it as markdown."""
    res = httpx.get(url, follow_redirects=True)
    if res.status_code < 200 or res.status_code > 299:
        return f"[download_pdf()]: HTTP {res.status_code}"
    md = markitdown.MarkItDown(enable_plugins=False)
    pdf_file = io.BytesIO(res.content)
    result = md.convert(pdf_file)
    return result.text_content


def web_search(query: str) -> list[WebSearchEntry]:
    """Search the web, return a list of dictionaries containing "title", "url" and "content".

    Unless ABSOLUTELY NECESSARY, do not print the content to read it in full, it will
    take way too much of your precious time. Instead either print just the URL/Title or,
    if you need to know more than the title, use the summarize() function.

    ## Example, find pages and analyze them

    ```starlark
    bird_search_result = web_search("nice bids")
    for result in bird_search_result:
        print(result['url'], analyze(instruction="summarize this page, evaluate if it includes information about birds that are nice to people", text=result['contents']))
    ```

    ## Example, find pages and categorize them

    ```starlark
    bird_search_result = web_search("Enron Inc main website")
    for result in bird_search_result:
        if categorize(instruction="determine if this is the official website of Enron Inc", text=result['contents'], categories=['official', 'other'])) == 'official':
            print(extract_links(markdown=visit_webpage(result['url']))
    ```
    """
    res = httpx.post(
        "https://ollama.com/api/web_search",
        headers={"Authorization": f"Bearer {os.environ['OLLAMA_API_KEY']}"},
        json={"query": query},
        follow_redirects=True,
    )
    res.raise_for_status()
    return [
        WebSearchEntry(title=r["title"], url=r["url"], content=r["content"])
        for r in res.json()["results"]
    ]


def extract_links(markdown: str) -> list[tuple[str, str]]:
    """Parse any links in the given markdown document, and return them as a list of
    (title, url)-tuples.
    """
    # [title](url) links
    named = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", markdown)
    # <url> autolinks — use the url as the title
    bare = [(url, url) for url in re.findall(r"<(https?://[^>]+)>", markdown)]
    # Return in document order
    all_links = named + bare
    all_links.sort(key=lambda link: markdown.index(link[1]))
    return all_links


# ---------------------------------------------------------------------------
# Model-dependent tool factories
# ---------------------------------------------------------------------------

_ANALYSIS_SYSTEM_PROMPT = """
You are an expert text analysis professional, providing crisp, short summaries of text content.
You will be given an analysis instruction and a text, and should output an analysis.

Keep the output very focused and crisp, no extraneous details, as your output will be machine analyzed.
"""

_CATEGORIZATION_SYSTEM_PROMPT = """
You are an expert text categorization professional, grouping text into categories.
You will be given an analysis instruction, a text, and a list of categories.
You should read the text and pick the category that is most applicable.

Only respond with exactly one category string, exactly as specified in the list of allowed categories.
"""


def make_analyze_tool(model: models.Model) -> ToolFunction:
    """Create an analyze tool that delegates to the given model."""

    def analyze(instruction: str, text: str) -> str:
        """Instruct a fast low-cost LLM to analyze the given text per the given instructions.

        Use this to reduce the amount of text you yourself need to read, avoiding printing
        huge documents unless absolutely necessary.
        This can also be used for searching and extracting sections of large documents.
        """
        res = model.generate(
            [
                models.ChatMessage(
                    models.MessageRole.SYSTEM,
                    [models.TextContent(_ANALYSIS_SYSTEM_PROMPT)],
                ),
                models.ChatMessage(
                    models.MessageRole.USER,
                    [
                        models.TextContent(f"Instruction: {instruction}"),
                        models.TextContent(f"Text: {text}"),
                    ],
                ),
            ],
            with_code_tool=False,
        )
        assert isinstance(res.content[0], models.TextContent)
        return res.content[0].text.strip()

    return analyze


def make_categorize_tool(model: models.Model) -> ToolFunction:
    """Create a categorize tool that delegates to the given model."""

    def categorize(instruction: str, text: str, categories: list[str]) -> str:
        """Instruct a fast low-cost LLM to categorize the text per the instructions.

        The output will be one of the categories you provide.
        Use this to reduce the amount of text you yourself need to read.

        This can be used for branching logic for instance - ask it to return "yes" or "no" which
        you can then branch on in an if condition.
        """
        res = model.generate(
            [
                models.ChatMessage(
                    models.MessageRole.SYSTEM,
                    [models.TextContent(_CATEGORIZATION_SYSTEM_PROMPT)],
                ),
                models.ChatMessage(
                    models.MessageRole.USER,
                    [
                        models.TextContent(f"Instruction: {instruction}"),
                        models.TextContent(f"Categories: {json.dumps(categories)}"),
                        models.TextContent(f"Text: {text}"),
                    ],
                ),
            ],
            with_code_tool=False,
        )
        assert isinstance(res.content[0], models.TextContent)
        raw = res.content[0].text.strip()
        if raw in categories:
            return raw
        raise ValueError(
            f"tool did not pick a valid category: {raw} [categories: {categories}]"
        )

    return categorize


def default_tools(model: models.Model) -> list[ToolFunction]:
    """Return the default set of tools for an agent."""
    return [
        visit_webpage,
        download_pdf,
        web_search,
        extract_links,
        make_analyze_tool(model),
        make_categorize_tool(model),
    ]
