# Contributing to gatefare (Python SDK)

Thanks for considering a contribution. This is a small, focused SDK;
the bar is "does it make the package more correct, safer, or easier to
use" rather than "does it add features".

## Setup

```bash
git clone https://github.com/gatefareio/sdk-python
cd sdk-python
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Requires Python 3.10+.

## Workflow

```bash
.venv/bin/python -m pytest -ra      # all green
.venv/bin/ruff check .              # lint clean
.venv/bin/python -m build           # builds wheel + sdist
.venv/bin/python scripts/smoke_live.py   # 12-point live check vs gatefare.io
```

Open a PR against `main`. CI runs the pytest matrix (Python 3.10
through 3.13) + a build. Keep PRs single-purpose.

## Ground rules

- **Minimal runtime dependencies.** The package ships with `httpx` and
  `eth-account` only. We deliberately do NOT pull in `web3.py` — it is
  a heavy dependency and a single `eth_call` over httpx covers the one
  on-chain read we need. New runtime deps need a strong reason.
- **Spend-cap and price-divergence logic is load-bearing.** Any change
  near `gatefare/spend_cap.py` or the cap checks in `call_api` needs a
  test that proves the wallet cannot sign past the cap. These are the
  lines that stand between a user and a drained wallet.
- **Adapters import nothing.** The framework adapters under
  `gatefare/adapters/` deliberately do NOT import langchain /
  llamaindex / openai / anthropic. They return plain dicts the host
  framework consumes. Keep it that way.
- **Tests use mocked HTTP.** Unit tests use `pytest-httpx` and must not
  hit the network. The one exception is `scripts/smoke_live.py`, which
  is a manual / scheduled check, not part of `pytest`.

## Style

- Type hints everywhere; `from __future__ import annotations` at the
  top of every module.
- Plain `@dataclass` over Pydantic — keeps the install cheap.
- Comments explain *why*, not *what*. The existing source is the
  reference for tone and density.
- No emoji in source or commit messages.

## Releasing (maintainers)

1. Bump `version` in `pyproject.toml` and `__version__` in
   `src/gatefare/__init__.py` (keep them in sync).
2. Update the README if the public surface changed.
3. Commit, then `git tag vX.Y.Z && git push origin vX.Y.Z`.
4. The `publish.yml` workflow runs pytest + build and publishes to
   PyPI automatically via Trusted Publishers (OIDC, no token).

## Security

Found a vulnerability? Do not open a public issue. See
[SECURITY.md](./SECURITY.md).
