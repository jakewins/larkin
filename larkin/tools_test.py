from larkin import tools
from larkin.tools import tool_info, generate_tool_docs


def test_tool_info_basic():
    def greet(name: str, excited: bool) -> str:
        """Say hello to someone."""
        return f"Hello, {name}{'!' if excited else '.'}"

    info = tool_info(greet)
    assert info.name == "greet"
    assert info.params == [("name", "str"), ("excited", "bool")]
    assert info.return_annotation == "str"
    assert info.docstring == "Say hello to someone."


def test_tool_info_no_return_annotation():
    def do_thing(x: int):
        """Does a thing."""

    info = tool_info(do_thing)
    assert info.name == "do_thing"
    assert info.params == [("x", "int")]
    assert info.return_annotation is None
    assert info.docstring == "Does a thing."


def test_tool_info_complex_types():
    def search(query: str) -> list[dict[str, str]]:
        """Search for stuff."""
        return []

    info = tool_info(search)
    assert info.params == [("query", "str")]
    assert info.return_annotation == "list[dict[str, str]]"


def test_generate_tool_docs_single():
    def visit_webpage(url: str) -> str:
        """Visit a webpage, return its contents as markdown."""
        return ""

    docs = generate_tool_docs([visit_webpage])
    assert "def visit_webpage(url: str) -> str:" in docs
    assert "Visit a webpage, return its contents as markdown." in docs


def test_generate_tool_docs_multiple():
    def fetch(url: str) -> str:
        """Fetch a URL."""
        return ""

    def analyze(text: str) -> str:
        """Analyze text."""
        return ""

    docs = generate_tool_docs([fetch, analyze])
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

    docs = generate_tool_docs([web_search])
    assert "def web_search(query: str) -> list[str]:" in docs
    assert "Search the web." in docs
    assert "Returns a list of results." in docs


# ---------------------------------------------------------------------------
# Built-in tool direct tests
# ---------------------------------------------------------------------------


def test_extract_links_direct():
    md = (
        "Check out [Google](https://google.com) and "
        "[GitHub](https://github.com) for more info.\n"
        "Also see <https://bare.example.com>."
    )
    result = tools.extract_links(md)
    assert result == [
        ("Google", "https://google.com"),
        ("GitHub", "https://github.com"),
        ("https://bare.example.com", "https://bare.example.com"),
    ]


def test_tool_info_on_builtin_tools():
    """Verify that introspection works on the actual built-in tools."""
    info = tool_info(tools.visit_webpage)
    assert info.name == "visit_webpage"
    assert info.params == [("url", "str")]
    assert info.return_annotation == "str"
    assert "webpage" in info.docstring.lower()

    info = tool_info(tools.extract_links)
    assert info.name == "extract_links"
    assert info.params == [("markdown", "str")]


def test_generate_docs_for_builtin_tools():
    """Verify doc generation works on the actual built-in tools (no model-dependent ones)."""
    docs = generate_tool_docs(
        [
            tools.visit_webpage,
            tools.download_pdf,
            tools.extract_links,
        ]
    )
    assert "def visit_webpage(url: str) -> str:" in docs
    assert "def download_pdf(url: str) -> str:" in docs
    assert "def extract_links(markdown: str)" in docs
