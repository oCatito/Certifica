"""Modelos de email: troca de {variáveis} e conversão de HTML para texto."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

from app.core.text import variable_key

PLACEHOLDER_RE = re.compile(r"\{([^{}\n]+)\}")


def build_variables(row: dict[str, str], name: str, email: str, filename: str) -> dict[str, str]:
    """Todas as colunas da planilha viram variáveis, além de {nome}, {email} e {arquivo}."""
    variables = {variable_key(k): v for k, v in row.items()}
    variables.update({"nome": name, "email": email, "arquivo": filename})
    first = name.split()[0] if name.split() else name
    variables.setdefault("primeiro_nome", first)
    return variables


def render(template: str, variables: dict[str, str], escape_html: bool = False) -> str:
    """Troca {variavel} pelo valor. Variáveis desconhecidas ficam como estão."""

    def replace(match: re.Match) -> str:
        key = variable_key(match.group(1))
        if key not in variables:
            return match.group(0)
        value = variables[key]
        return html.escape(value) if escape_html else value

    return PLACEHOLDER_RE.sub(replace, template)


def unknown_variables(template: str, variables: dict[str, str]) -> list[str]:
    found = []
    for match in PLACEHOLDER_RE.finditer(template):
        if variable_key(match.group(1)) not in variables and match.group(0) not in found:
            found.append(match.group(0))
    return found


class _TextExtractor(HTMLParser):
    BLOCK = {"p", "div", "br", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "li", "table", "section"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0
        self._href: str | None = None

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script", "head"):
            self._skip += 1
        if tag in self.BLOCK:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("- ")
        if tag == "a":
            self._href = dict(attrs).get("href")

    def handle_endtag(self, tag):
        if tag in ("style", "script", "head"):
            self._skip = max(0, self._skip - 1)
        if tag in self.BLOCK and tag != "br":
            self.parts.append("\n")
        if tag == "a" and self._href and not self._href.startswith("mailto:"):
            self.parts.append(f" ({self._href})")
            self._href = None

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(re.sub(r"\s+", " ", data))


def html_to_text(markup: str) -> str:
    parser = _TextExtractor()
    parser.feed(markup)
    parser.close()
    text = "".join(parser.parts)
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
