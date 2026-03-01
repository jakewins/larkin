from larkin import scripting, tools


def _ws(*extra_tools: tools.Tool) -> scripting.ScriptWorkspace:
    """Create a workspace with the given tools (or no tools for pure Starlark tests)."""
    return scripting.ScriptWorkspace(list(extra_tools))


def test_web_search():
    res = _ws(tools.WEB_SEARCH).eval(
        "shops = web_search('garden shops selling apple trees near New York City')\nprint(shops)"
    )
    assert isinstance(res, scripting.ScriptOk), f"Expected ScriptOk, got: {res}"


def test_top_level_for_loop():
    res = _ws().eval(
        "items = []\nfor i in range(3):\n    items.append(i)\nprint(items)\n"
    )
    assert isinstance(res, scripting.ScriptOk), f"Expected ScriptOk, got: {res}"
    assert res.prints == ["[0, 1, 2]"]


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
