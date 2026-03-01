from larkin import tools
from larkin.tools import Tool, FunctionTool, ToolParam, generate_tool_docs


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


# ---------------------------------------------------------------------------
# Custom Tool via protocol conformance (no inheritance)
# ---------------------------------------------------------------------------


def test_custom_tool_protocol():
    """A hand-built object satisfying the Tool protocol works with generate_tool_docs."""

    class MyTool:
        name = "magic"
        description = "Do magic things."
        parameters = [ToolParam("spell", "str")]
        return_type = "str"

        def __call__(self, spell: str) -> str:
            return f"cast {spell}"

    docs = generate_tool_docs([MyTool()])  # type: ignore[list-item]
    assert "def magic(spell: str) -> str:" in docs
    assert "Do magic things." in docs


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


def test_builtin_tool_objects():
    """Module-level Tool objects have correct metadata."""
    assert tools.VISIT_WEBPAGE.name == "visit_webpage"
    assert tools.VISIT_WEBPAGE.parameters == [ToolParam("url", "str")]
    assert tools.VISIT_WEBPAGE.return_type == "str"
    assert "webpage" in tools.VISIT_WEBPAGE.description.lower()

    assert tools.EXTRACT_LINKS.name == "extract_links"
    assert tools.EXTRACT_LINKS.parameters == [ToolParam("markdown", "str")]


def test_generate_docs_for_builtin_tools():
    """Doc generation works on the module-level Tool objects."""
    docs = generate_tool_docs(
        [
            tools.VISIT_WEBPAGE,
            tools.DOWNLOAD_PDF,
            tools.EXTRACT_LINKS,
        ]
    )
    assert "def visit_webpage(url: str) -> str:" in docs
    assert "def download_pdf(url: str) -> str:" in docs
    assert "def extract_links(markdown: str)" in docs
