# Contributing

Thanks for helping. Contributions of code, species data, translations and
field observations are all welcome.

## Ground rules

- **Evidence first.** Any change to a species threshold must cite its
  source and state its evidence grade (A–D, see
  [docs/science.md](docs/science.md)). Use the *Species data* issue template
  to propose one.
- **Never present an index as a probability**, in code, UI strings or docs.
- **Privacy.** Never commit real coordinates of private places or of
  mushroom spots: not in fixtures, examples, tests or issues. Use public
  reference points (towns, summits, well-known passes).
- **The core stays Home Assistant-free.** `custom_components/mycomonitor/core/`
  must not import `homeassistant`.
- **No new runtime dependencies** without discussion. Home Assistant already
  ships aiohttp and PyYAML.

## Development setup

```sh
python3.14 -m venv .venv
.venv/bin/pip install -r tests/requirements.txt
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy
```

Tests never hit the network. API responses are recorded fixtures in
`tests/fixtures/`, refreshed with `scripts/record_fixtures.py` (public
reference points only).

## Pull requests

- One topic per pull request, with tests for new behaviour.
- Update `CHANGELOG.md` under *Unreleased*, and the docs if behaviour changes.
- User-facing strings go in `strings.json` and in both `translations/en.json`
  and `translations/es.json`.

## Code of conduct

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md).
