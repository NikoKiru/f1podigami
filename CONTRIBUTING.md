# Contributing to F1 Podigami

Thanks for your interest in contributing! Here's how to get started.

## Getting Started

1. Fork the repository and clone your fork.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

3. Create a branch for your change:

   ```bash
   git checkout -b your-branch-name
   ```

## Development

Rebuild the site from committed JSON data (no network needed):

```bash
python src/build_site.py
```

Run the full pipeline (fetches latest data from the API):

```bash
python src/update.py
```

## Before Submitting

Make sure lint, format, and tests all pass — these are enforced in CI:

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
```

## Pull Requests

- Keep PRs focused on a single change.
- Write a clear title and description of what changed and why.
- Make sure CI checks pass before requesting review.

## Reporting Issues

Open an issue on [GitHub Issues](https://github.com/NikoKiru/f1podigami/issues) with steps to reproduce the problem.

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold it.
