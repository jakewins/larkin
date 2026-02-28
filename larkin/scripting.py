import io
import starlark as sl
import typing as t
import re
import httpx
import os
import json
import dataclasses
import markdownify
import markitdown

from larkin import models

MAX_TOOL_OUTPUT = 30_000


@dataclasses.dataclass
class ScriptOk:
    prints: list[str]
    final_answer: str | None = None


@dataclasses.dataclass
class ScriptError:
    prints: list[str]
    error: str


class WebSearchEntry(t.TypedDict):
    title: str
    url: str
    content: str


class ScriptWorkspace:
    def __init__(self):
        self.globals = sl.Globals.standard()
        self.mod = sl.Module()

        self.final_answer: str | None = None
        self.prints = []

        def visit_webpage(url: str) -> str:
            res = httpx.get(url)
            if res.status_code < 200 or res.status_code > 299:
                return f"[visit_webpage()]: HTTP {res.status_code}"
            mk_content = markdownify.markdownify(res.text)
            if len(mk_content) > MAX_TOOL_OUTPUT:
                mk_content = mk_content[:MAX_TOOL_OUTPUT]
                mk_content += "\n[..]\n_[visit_webpage()]: This page has been truncated to stay below {MAX_TOOL_OUTPUT} characters._\n"
            return mk_content

        self.mod.add_callable("visit_webpage", visit_webpage)

        def download_pdf(url: str) -> str:
            res = httpx.get(url, follow_redirects=True)
            if res.status_code < 200 or res.status_code > 299:
                return f"[download_pdf()]: HTTP {res.status_code}"
            md = markitdown.MarkItDown(enable_plugins=False)
            pdf_file = io.BytesIO(res.content)
            result = md.convert(pdf_file)
            return result.text_content

        self.mod.add_callable("download_pdf", download_pdf)

        def web_search(query: str) -> list[WebSearchEntry]:
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

        self.mod.add_callable("web_search", web_search)

        def analyze(instruction: str, text: str) -> str:
            m = models.GoogleModel(model="gemini-2.5-flash")
            res = m.generate(
                [
                    models.ChatMessage(
                        models.MessageRole.SYSTEM,
                        [
                            models.TextContent(ANALYSIS_SYSTEM_PROMPT),
                        ],
                    ),
                    models.ChatMessage(
                        models.MessageRole.USER,
                        [
                            models.TextContent(f"""Instruction: {instruction}"""),
                            models.TextContent(f"""Text: {text}"""),
                        ],
                    ),
                ],
                with_code_tool=False,
            )
            assert isinstance(res.content[0], models.TextContent)
            return res.content[0].text.strip()

        self.mod.add_callable("analyze", analyze)

        def categorize(instruction: str, text: str, categories: list[str]) -> str:
            m = models.GoogleModel(model="gemini-2.5-flash")
            res = m.generate(
                [
                    models.ChatMessage(
                        models.MessageRole.SYSTEM,
                        [
                            models.TextContent(ANALYSIS_SYSTEM_PROMPT),
                        ],
                    ),
                    models.ChatMessage(
                        models.MessageRole.USER,
                        [
                            models.TextContent(f"""Instruction: {instruction}"""),
                            models.TextContent(
                                f"""Categories: {json.dumps(categories)}"""
                            ),
                            models.TextContent(f"""Text: {text}"""),
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

        self.mod.add_callable("categorize", categorize)

        def extract_links(markdown: str) -> list[tuple[str, str]]:
            # [title](url) links
            named = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", markdown)
            # <url> autolinks — use the url as the title
            bare = [(url, url) for url in re.findall(r"<(https?://[^>]+)>", markdown)]
            # Return in document order
            all_links = named + bare
            all_links.sort(key=lambda link: markdown.index(link[1]))
            return all_links

        self.mod.add_callable("extract_links", extract_links)

        def _print(*args):
            self.prints.append(str(args[0]) if len(args) == 1 else str(args))

        self.mod.add_callable("print", _print)

        def final_answer(answer: str):
            self.final_answer = answer

        self.mod.add_callable("final_answer", final_answer)

        def load(name: str):
            raise FileNotFoundError(f"loading is not available")

        self.file_loader = sl.FileLoader(load)

    def eval(self, script: str) -> ScriptOk | ScriptError:
        try:
            dialect = sl.Dialect.extended()
            dialect.enable_top_level_stmt = True
            ast = sl.parse("script.star", script, dialect=dialect)

            # Clear the side-effects of any prior runs, other than variables
            self.prints = []

            sl.eval(self.mod, ast, self.globals, self.file_loader)

            return ScriptOk(self.prints, self.final_answer)
        except sl.StarlarkError as e:
            return ScriptError(prints=self.prints, error=str(e))
        except FileNotFoundError as e:
            return ScriptError(prints=self.prints, error=str(e))


ANALYSIS_SYSTEM_PROMPT = """
You are an expert text analysis professional, providing crisp, short summaries of text content.
You will be given an analysis instruction and a text, and should output an analysis.

Keep the output very focused and crisp, no extraneous details, as your output will be machine analyzed.
"""

CATEGORIZATION_SYSTEM_PROMPT = """
You are an expert text categorization professional, grouping text into categories.
You will be given an analysis instruction, a text, and a list of categories. 
You should read the text and pick the category that is most applicable.

Only respond with exactly one category string, exactly as specified in the list of allowed categories.
"""
