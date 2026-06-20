"""Shared page chrome used by every page builder.

Keeping the footer here guarantees all four pages render an identical footer.
The import works both when a builder is run as a script
(``python src/build/build_*.py``) and when the builders are imported as
``build.*`` by the test-suite, because each builder adds its own directory to
``sys.path`` before importing this module.
"""

from __future__ import annotations

REPO_URL = "https://github.com/NikoKiru/f1_podigami"
DATA_URL = "https://api.jolpi.ca/ergast/f1/"

FOOTER = f"""<footer>
    <div class="container footer-inner">
        <nav class="footer-nav">
            <a href="index.html">Podigami</a>
            <a href="combos.html">Combinations</a>
            <a href="overdue.html">Overdue</a>
            <a href="soulmates.html">Soulmates</a>
        </nav>
        <p class="footer-meta">
            Data from <a href="{DATA_URL}" target="_blank" rel="noopener">Jolpica F1 API</a> (Ergast)
            &middot; F1 World Championship podiums since 1950
            &middot; For fun, not betting
            &middot; <a href="{REPO_URL}" target="_blank" rel="noopener">Source on GitHub</a>
        </p>
    </div>
</footer>"""
