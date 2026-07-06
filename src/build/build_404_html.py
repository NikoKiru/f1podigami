"""Render the static 404 error page into dist/404.html."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _layout import FOOTER, head, nav  # noqa: E402

OUT_PATH = ROOT / "dist" / "404.html"


def render() -> str:
    return f"""{
        head(
            "404 — Page Not Found | F1 Podigami",
            description="This page doesn't exist. Head back to F1 Podigami.",
            page_path="404.html",
            noindex=True,
        )
    }
<body>
{nav("")}
<main class="container error-main">
<style>
.error-main {{
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 60vh;
    text-align: center;
    gap: 1rem;
}}
.error-code {{
    font-size: clamp(5rem, 20vw, 10rem);
    font-weight: 700;
    line-height: 1;
    color: var(--accent, #e10600);
}}
.error-msg {{
    font-size: 1.25rem;
    color: var(--text-muted, #888);
}}
.error-home {{
    margin-top: 1.5rem;
    padding: 0.6rem 1.4rem;
    border: 2px solid var(--accent, #e10600);
    border-radius: 4px;
    color: var(--accent, #e10600);
    text-decoration: none;
    font-weight: 600;
    letter-spacing: 0.04em;
}}
.error-home:hover {{
    background: var(--accent, #e10600);
    color: #fff;
}}
</style>
<p class="error-code">404</p>
<p class="error-msg">DNF — this page retired from the race.</p>
<a href="index.html" class="error-home">Back to the grid &#x2192;</a>
</main>
{FOOTER}
</body>
</html>"""


if __name__ == "__main__":
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(render(), encoding="utf-8")
    print(f"Written -> {OUT_PATH}")
