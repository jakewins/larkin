from larkin import tools, scripting
from larkin.tools import Tool, FunctionTool, ToolParam, generate_tool_docs

from larkin.scripting_test import _ws

# ---------------------------------------------------------------------------
# Tool.from_function / FunctionTool.from_function introspection tests
# ---------------------------------------------------------------------------


def test_from_function_basic():
    def greet(name: str, excited: bool) -> str:
        """Say hello to someone."""
        return f"Hello, {name}{'!' if excited else '.'}"

    tool = Tool.from_function(greet)
    assert tool.name == "greet"
    assert tool.parameters == [ToolParam("name", "str"), ToolParam("excited", "bool")]
    assert tool.return_type == "str"
    assert tool.description == "Say hello to someone."
    # callable
    assert tool("world", True) == "Hello, world!"


def test_from_function_no_return_annotation():
    def do_thing(x: int):
        """Does a thing."""

    tool = FunctionTool.from_function(do_thing)
    assert tool.name == "do_thing"
    assert tool.parameters == [ToolParam("x", "int")]
    assert tool.return_type is None
    assert tool.description == "Does a thing."


def test_from_function_complex_types():
    def search(query: str) -> list[dict[str, str]]:
        """Search for stuff."""
        return []

    tool = Tool.from_function(search)
    assert tool.parameters == [ToolParam("query", "str")]
    assert tool.return_type == "list[dict[str, str]]"


# ---------------------------------------------------------------------------
# generate_tool_docs tests
# ---------------------------------------------------------------------------


def test_generate_tool_docs_single():
    def visit_webpage(url: str) -> str:
        """Visit a webpage, return its contents as markdown."""
        return ""

    docs = generate_tool_docs([Tool.from_function(visit_webpage)])
    assert "def visit_webpage(url: str) -> str:" in docs
    assert "Visit a webpage, return its contents as markdown." in docs


def test_generate_tool_docs_multiple():
    def fetch(url: str) -> str:
        """Fetch a URL."""
        return ""

    def analyze(text: str) -> str:
        """Analyze text."""
        return ""

    docs = generate_tool_docs([Tool.from_function(fetch), Tool.from_function(analyze)])
    assert "def fetch(url: str) -> str:" in docs
    assert "def analyze(text: str) -> str:" in docs
    assert "Fetch a URL." in docs
    assert "Analyze text." in docs


def test_generate_tool_docs_multiline_docstring():
    def web_search(query: str) -> list[str]:
        """Search the web.

        Returns a list of results.
        Use wisely.
        """
        return []

    docs = generate_tool_docs([Tool.from_function(web_search)])
    assert "def web_search(query: str) -> list[str]:" in docs
    assert "Search the web." in docs
    assert "Returns a list of results." in docs


# Built-in tool tests
# We test the full script harness because it's just as fast, and gives us much better coverage, making sure the tools
# work in the actual scripting env.


def test_extract_links():
    md = (
        "Check out [Google](https://google.com) and "
        "[GitHub](https://github.com) for more info.\n"
        "Also see [Docs](https://docs.example.com/path?q=1)."
    )
    res = _ws(tools.EXTRACT_LINKS).eval(
        f"links = extract_links({md!r})\nprint(links)\n"
    )
    assert isinstance(res, scripting.ScriptOk), f"Expected ScriptOk, got: {res}"
    assert res.prints == [
        "[['Google', 'https://google.com'], ['GitHub', 'https://github.com'], ['Docs', 'https://docs.example.com/path?q=1']]"
    ]


def test_extract_links_bare_urls():
    md = (
        "Visit [Google](https://google.com) or "
        "just go to <https://bare-link.example.com> for more."
    )
    res = _ws(tools.EXTRACT_LINKS).eval(
        f"links = extract_links({md!r})\nprint(links)\n"
    )
    assert isinstance(res, scripting.ScriptOk), f"Expected ScriptOk, got: {res}"
    assert res.prints == [
        "[['Google', 'https://google.com'], ['https://bare-link.example.com', 'https://bare-link.example.com']]"
    ]


def test_web_search():
    res = _ws(tools.WEB_SEARCH).eval(
        "shops = web_search('garden shops selling apple trees near New York City')\nprint(shops)"
    )
    assert isinstance(res, scripting.ScriptOk), f"Expected ScriptOk, got: {res}"


def test_visit_webpage():
    res = _ws(tools.VISIT_WEBPAGE).eval(
        "content = visit_webpage('https://www.google.com')\nprint(len(content) > 0)\n"
    )
    assert isinstance(res, scripting.ScriptOk), f"Expected ScriptOk, got: {res}"
    assert res.prints == ["True"]


def test_download_pdf():
    res = _ws(tools.DOWNLOAD_PDF).eval("""
pdf_content = download_pdf(url='https://pdfobject.com/pdf/sample.pdf')
print(pdf_content)
""")
    assert isinstance(res, scripting.ScriptOk), f"Expected ScriptOk, got: {res}"
    assert "Sample PDF" in res.prints[0]
