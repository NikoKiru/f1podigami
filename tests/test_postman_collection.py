"""The Postman collection in postman/collections/ stays in step with the fetchers.

It's a hand tool for checking the upstream APIs, kept in Postman's own folder
format (one YAML file per request), in the folder Postman lists in its
Collections panel, so a Postman workspace opened on this repo syncs it through
git. Nothing in the pipeline reads it, so nothing else would
notice if a base URL moved in the code and the collection kept the old one, or
a request used a variable that no longer exists.

The files are read line by line rather than with a YAML library, which keeps a
dependency out of the test run: Postman writes every value checked here on a
line of its own.
"""

import json
import re
from pathlib import Path

from fetch import fetch_podiums, fetch_race_links, openf1

REPO = Path(__file__).resolve().parents[1]
COLLECTION = REPO / "postman" / "collections" / "F1 Podigami upstream APIs"
F1COM_ROOT = fetch_race_links.INDEX_URL.split("{year}")[0]
VAR_RE = re.compile(r"\{\{([^{}]+)\}\}")


def _scalar(raw: str) -> str:
    """A one-line YAML scalar, as Postman writes it: plain, '...' or "..."."""
    raw = raw.strip()
    if raw.startswith('"'):
        return json.loads(raw)
    if raw.startswith("'"):
        return raw[1:-1].replace("''", "'")
    return raw


def _variables() -> dict[str, str]:
    lines = (COLLECTION / ".resources" / "definition.yaml").read_text(encoding="utf-8")
    lines = lines.splitlines()
    out = {}
    for line in lines[lines.index("variables:") + 1 :]:
        if not line.startswith("  "):
            break
        key, _, value = line.strip().partition(":")
        out[key] = _scalar(value)
    return out


def _requests() -> dict[str, str]:
    """Each request file's name and URL."""
    out = {}
    for path in sorted(COLLECTION.rglob("*.request.yaml")):
        lines = path.read_text(encoding="utf-8").splitlines()
        out[path.name] = _scalar(next(ln for ln in lines if ln.startswith("url:"))[4:])
    return out


def test_the_collection_has_requests():
    assert _requests()


def test_base_urls_match_the_fetchers():
    variables = _variables()
    assert variables["jolpica"] == fetch_podiums.API_ROOT
    assert variables["openf1"] == openf1.API_ROOT


def test_every_request_targets_a_source_the_pipeline_uses():
    for name, url in _requests().items():
        assert url.startswith(("{{jolpica}}/", "{{openf1}}/", F1COM_ROOT)), (name, url)


def test_every_variable_used_is_defined():
    defined = set(_variables())
    for name, url in _requests().items():
        # {{$timestamp}} and friends are Postman's own dynamic variables.
        missing = {v for v in VAR_RE.findall(url) if not v.startswith("$")} - defined
        assert not missing, (name, missing)


def test_request_names_are_unique():
    paths = list(COLLECTION.rglob("*.request.yaml"))
    assert len(paths) == len({p.name for p in paths})
