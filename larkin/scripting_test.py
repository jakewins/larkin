from larkin import scripting, tools
from larkin.tools import FunctionTool, OpaqueValue


def _ws(*extra_tools: tools.Tool) -> scripting.ScriptWorkspace:
    """Create a workspace with the given tools (or no tools for pure Starlark tests)."""
    return scripting.ScriptWorkspace(list(extra_tools))


# ---------------------------------------------------------------------------
# Stub tools for opaque-value tests
# ---------------------------------------------------------------------------


def _get_secret() -> OpaqueValue:
    """Return an opaque handle wrapping secret data."""
    return OpaqueValue("TOP SECRET DATA")


_GET_SECRET = FunctionTool.from_function(_get_secret)


def _accept_opaque(handle: OpaqueValue) -> str:
    """A tool that explicitly accepts an opaque value and returns its length."""
    return str(len(str(handle.value)))


_ACCEPT_OPAQUE = FunctionTool.from_function(_accept_opaque)


def _accept_str(text: str) -> str:
    """A tool that accepts a plain string."""
    return text.upper()


_ACCEPT_STR = FunctionTool.from_function(_accept_str)


def _accept_str_list(items: list[str]) -> str:
    """A tool that accepts a list of plain strings."""
    return ", ".join(items)


_ACCEPT_STR_LIST = FunctionTool.from_function(_accept_str_list)


def _accept_opaque_list(handles: list[OpaqueValue]) -> str:
    """A tool that accepts a list of opaque values."""
    return str(len(handles))


_ACCEPT_OPAQUE_LIST = FunctionTool.from_function(_accept_opaque_list)


def _accept_opaque_dict(mapping: dict[str, OpaqueValue]) -> str:
    """A tool that accepts a dict with opaque values."""
    return ", ".join(mapping.keys())


_ACCEPT_OPAQUE_DICT = FunctionTool.from_function(_accept_opaque_dict)


# ---------------------------------------------------------------------------
# Opaque value security tests
# ---------------------------------------------------------------------------


def test_opaque_cannot_be_printed():
    res = _ws(_GET_SECRET).eval("x = _get_secret()\nprint(x)")
    assert isinstance(res, scripting.ScriptError), f"Expected ScriptError, got: {res}"
    assert "opaque" in res.error.lower()


def test_opaque_in_list_cannot_be_printed():
    res = _ws(_GET_SECRET).eval("x = _get_secret()\nprint([x, 1, 2])")
    assert isinstance(res, scripting.ScriptError), f"Expected ScriptError, got: {res}"
    assert "opaque" in res.error.lower()


def test_opaque_cannot_be_final_answered():
    res = _ws(_GET_SECRET).eval("x = _get_secret()\nfinal_answer(x)")
    assert isinstance(res, scripting.ScriptError), f"Expected ScriptError, got: {res}"
    assert "opaque" in res.error.lower()


def test_opaque_cannot_be_passed_to_str_param():
    res = _ws(_GET_SECRET, _ACCEPT_STR).eval("x = _get_secret()\n_accept_str(x)")
    assert isinstance(res, scripting.ScriptError), f"Expected ScriptError, got: {res}"
    assert "opaque" in res.error.lower()
    assert "_accept_str" in res.error


def test_opaque_can_be_passed_to_opaque_param():
    res = _ws(_GET_SECRET, _ACCEPT_OPAQUE).eval(
        "x = _get_secret()\nresult = _accept_opaque(x)\nprint(result)"
    )
    assert isinstance(res, scripting.ScriptOk), f"Expected ScriptOk, got: {res}"
    assert res.prints == [str(len("TOP SECRET DATA"))]


def test_opaque_can_be_stored_and_passed_around():
    """Opaque values can be assigned, stored in lists, and forwarded to opaque-aware tools."""
    res = _ws(_GET_SECRET, _ACCEPT_OPAQUE).eval(
        "x = _get_secret()\ny = x\nitems = [y]\nresult = _accept_opaque(items[0])\nprint(result)"
    )
    assert isinstance(res, scripting.ScriptOk), f"Expected ScriptOk, got: {res}"
    assert res.prints == [str(len("TOP SECRET DATA"))]


def test_opaque_str_repr_safe():
    """OpaqueValue.__str__ and __repr__ never leak the wrapped content."""
    ov = OpaqueValue("super secret")
    assert "super secret" not in str(ov)
    assert "super secret" not in repr(ov)
    assert str(ov) == "<opaque value>"
    assert repr(ov) == "OpaqueValue(<redacted>)"


def test_non_opaque_tools_unaffected():
    """Regular tools work normally through the validation wrapper."""
    res = _ws(tools.EXTRACT_LINKS).eval(
        "links = extract_links('[Example](https://example.com)')\nprint(links)"
    )
    assert isinstance(res, scripting.ScriptOk), f"Expected ScriptOk, got: {res}"
    assert "Example" in res.prints[0]


def test_opaque_auto_wrap_return():
    """A tool returning OpaqueValue gets auto-wrapped so Starlark can store it,
    then pass it to an opaque-accepting tool which unwraps it."""
    res = _ws(_GET_SECRET, _ACCEPT_OPAQUE).eval(
        "handle = _get_secret()\n"
        "# Starlark can store it and pass around but not inspect\n"
        "copy = handle\n"
        "print(_accept_opaque(copy))"
    )
    assert isinstance(res, scripting.ScriptOk), f"Expected ScriptOk, got: {res}"
    assert res.prints == [str(len("TOP SECRET DATA"))]


def test_opaque_visit_webpage():
    """opaque_visit_webpage returns an opaque handle whose inner value is the page content."""
    ov = tools.opaque_visit_webpage("https://www.example.com")
    assert isinstance(ov, OpaqueValue)
    assert isinstance(ov.value, str)
    assert len(str(ov.value)) > 0


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


def test_opaque_in_list_cannot_reach_str_list_param():
    """An opaque value smuggled inside a list[str] argument is caught."""
    res = _ws(_GET_SECRET, _ACCEPT_STR_LIST).eval(
        "x = _get_secret()\n_accept_str_list([x, 'hello'])"
    )
    assert isinstance(res, scripting.ScriptError), f"Expected ScriptError, got: {res}"
    assert "opaque" in res.error.lower()


def test_opaque_in_list_can_reach_opaque_list_param():
    """A tool declaring list[OpaqueValue] can receive a list containing opaque values."""
    res = _ws(_GET_SECRET, _ACCEPT_OPAQUE_LIST).eval(
        "x = _get_secret()\nresult = _accept_opaque_list([x, x])\nprint(result)"
    )
    assert isinstance(res, scripting.ScriptOk), f"Expected ScriptOk, got: {res}"
    assert res.prints == ["2"]


def test_opaque_in_dict_can_reach_opaque_dict_param():
    """A tool declaring dict[str, OpaqueValue] can receive a dict with opaque values."""
    res = _ws(_GET_SECRET, _ACCEPT_OPAQUE_DICT).eval(
        "x = _get_secret()\nresult = _accept_opaque_dict({'a': x})\nprint(result)"
    )
    assert isinstance(res, scripting.ScriptOk), f"Expected ScriptOk, got: {res}"
    assert res.prints == ["a"]


def test_download_pdf():
    res = _ws(tools.DOWNLOAD_PDF).eval("""
pdf_content = download_pdf(url='https://pdfobject.com/pdf/sample.pdf')
print(pdf_content)
""")
    assert isinstance(res, scripting.ScriptOk), f"Expected ScriptOk, got: {res}"
    assert "Sample PDF" in res.prints[0]
