"""The contract between what the builders emit and what the stylesheets define.

Both bugs these lock in were found by cross-checking generated markup against
assets/: a ``var(--x)`` pointing at a token that does not exist (#224), and a
class emitted by three builders with no rule anywhere (#225). Neither breaks the
build — the page just renders wrong — so they need a test to stay fixed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from build import build_404_html

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
BUILDERS = ROOT / "src" / "build"

# Custom properties are declared in the stylesheets *and* inline by the builders
# (e.g. style="--team: #fff") — both count as definitions.
DEFINITION = re.compile(r"(--[a-zA-Z][\w-]*)\s*:")
REFERENCE = re.compile(r"var\(\s*(--[a-zA-Z][\w-]*)")

STYLE_CSS = (ASSETS / "style.css").read_text(encoding="utf-8")


def _sources() -> list[Path]:
    return (
        sorted(ASSETS.glob("*.css")) + sorted(ASSETS.glob("*.js")) + sorted(BUILDERS.glob("*.py"))
    )


def _token_block(selector: str) -> dict[str, str]:
    """The ``--token: value`` pairs declared by a selector in style.css."""
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", STYLE_CSS)
    assert match, f"{selector} block not found in style.css"
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", match.group(1)))


DARK = _token_block(":root")
LIGHT = {**DARK, **_token_block('[data-theme="light"]')}
THEMES = {"dark": DARK, "light": LIGHT}


def _relative_luminance(hex_color: str) -> float:
    h = hex_color.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    channels = []
    for i in (0, 2, 4):
        c = int(h[i : i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2.2 contrast ratio between two hex colours."""
    lighter, darker = sorted((_relative_luminance(fg), _relative_luminance(bg)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_every_css_variable_reference_is_defined():
    """A ``var(--x)`` naming a token nobody defines silently drops the declaration.

    With a fallback it is worse than silent: ``var(--text-muted, #888)`` looked
    theme-aware but always painted #888 (#224).
    """
    defined: set[str] = set()
    referenced: dict[str, str] = {}  # token -> first file that references it
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        defined.update(DEFINITION.findall(text))
        for token in REFERENCE.findall(text):
            referenced.setdefault(token, path.name)

    undefined = {t: f for t, f in sorted(referenced.items()) if t not in defined}
    assert not undefined, f"var() references to undefined custom properties: {undefined}"


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_404_message_meets_wcag_aa(theme: str):
    """The "DNF" line is 1.25rem normal weight, so AA wants >= 4.5:1 in both themes.

    It has to resolve through a real theme token to manage that — the hardcoded
    #888 fallback it used to land on measures 3.31:1 on the light background.
    """
    rule = re.search(r"\.error-msg\s*\{([^}]*)\}", build_404_html.render())
    assert rule, ".error-msg rule missing from the 404 page"
    declared = re.search(r"color:\s*([^;]+);", rule.group(1))
    assert declared, ".error-msg declares no colour"

    value = declared.group(1).strip()
    token = re.fullmatch(r"var\((--[\w-]+)\)", value)
    assert token, f"404 message colour must be a bare theme token, got {value!r}"

    tokens = THEMES[theme]
    name = token.group(1)
    assert name in tokens, f"{name} is not defined for the {theme} theme"
    ratio = contrast_ratio(tokens[name], tokens["--bg"])
    assert ratio >= 4.5, f"{name} on --bg is {ratio:.2f}:1 in {theme} theme, below AA 4.5:1"


def test_methodology_footnote_is_styled_as_fine_print():
    """``.as-of`` closes Overdue, Unlikeliest and Soulmates with a methodology note.

    Unstyled it rendered at full body size and brightness — louder than the
    captions above it, the opposite of a footnote (#225).
    """
    css = (ASSETS / "podigami.css").read_text(encoding="utf-8")
    rule = re.search(r"(?<![\w.-])\.as-of\s*\{([^}]*)\}", css)
    assert rule, ".as-of is emitted by three builders but styled by no stylesheet"

    body = rule.group(1)
    assert "var(--muted)" in body, "the footnote should use the muted text token"
    size = re.search(r"font-size:\s*(\d+)px", body)
    assert size, "the footnote should declare a font-size"
    assert int(size.group(1)) < 16, "the footnote must be smaller than 16px body text"


def _info_tip_ancestor_classes(html: str) -> list[list[str]]:
    """Every ``.info-tip``'s ancestor class lists, in document order."""
    from html.parser import HTMLParser

    VOID = {"br", "hr", "img", "input", "link", "meta", "source", "wbr"}

    class Walker(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.stack: list[list[str]] = []
            self.found: list[list[str]] = []

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            classes = dict(attrs).get("class", "") or ""
            names = classes.split()
            if "info-tip" in names:
                self.found.append([c for frame in self.stack for c in frame])
            if tag not in VOID:
                self.stack.append(names)

        def handle_startendtag(self, tag, attrs):  # <span ... /> never nests
            self.handle_starttag(tag, attrs)
            self.stack.pop()

        def handle_endtag(self, tag: str) -> None:
            if tag not in VOID and self.stack:
                self.stack.pop()

    walker = Walker()
    walker.feed(html)
    return walker.found


def test_info_tooltips_are_not_clipped_by_an_ancestor(dist):
    """``.info-bubble`` hangs *outside* its icon, so any ancestor with
    ``overflow: hidden`` cuts the tooltip in half.

    ``.hero`` did exactly that: the 45% card's bubble opened downwards and lost
    its last line at the hero's bottom edge. Ancestors of a tooltip must clip
    nothing — round a decorative child instead of clipping the parent.
    """
    stylesheets = "\n".join(p.read_text(encoding="utf-8") for p in sorted(ASSETS.glob("*.css")))
    offenders: set[str] = set()
    for page in sorted(dist.glob("*.html")):
        for ancestors in _info_tip_ancestor_classes(page.read_text(encoding="utf-8")):
            for name in ancestors:
                for rule in re.finditer(
                    r"(?<![\w.-])\." + re.escape(name) + r"\s*\{([^}]*)\}", stylesheets
                ):
                    if re.search(r"overflow(-[xy])?:\s*hidden", rule.group(1)):
                        offenders.add(f"{page.name}: .{name}")

    assert not offenders, "these ancestors of an .info-tip clip its tooltip: " + ", ".join(
        sorted(offenders)
    )


def test_both_table_systems_share_the_row_padding_token():
    """The ranked tables mirror the combinations table cell for cell, so their
    rows take the same padding from one token instead of two matching numbers."""
    assert "--pad-row" in DARK, "the density tokens live in :root"
    index = (ASSETS / "index.css").read_text(encoding="utf-8")
    podigami = (ASSETS / "podigami.css").read_text(encoding="utf-8")
    assert re.search(r"tbody tr\.combo>td\s*\{[^}]*padding:\s*var\(--pad-row\)", index)
    assert re.search(r"\.rr-face\s*\{[^}]*padding:\s*var\(--pad-row\)", podigami)
