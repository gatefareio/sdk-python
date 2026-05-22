# Changelog

All notable changes to the `gatefare` Python SDK are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-05-21

### Fixed

- `get_api()` now surfaces `publisher.reputation` and
  `sample_response` from `/catalog/:slug` detail responses. v0.1.0
  declared `CatalogApi` with only the catalog-list field subset, so
  the two detail-only fields were silently dropped. Consumers calling
  `gf.get_api(slug)` could not read a publisher's trust badges or the
  publisher-provided sample response without bypassing the SDK. Both
  are now exposed. Parity with `@gatefare/client@0.1.1` (TypeScript).

### Added

- `AccountReputation` dataclass — positive-only publisher trust
  badges (`established`, `top_contributor`, `highly_rated`) plus the
  raw counters behind them.
- `PublisherInfo` dataclass — publisher handle, display name,
  verification tier, optional reputation.
- `publisher` and `sample_response` on the `CatalogApi` dataclass.
  Both optional: populated by `get_api()` detail responses, `None`
  on `list_catalog()` list responses.
- `AccountReputation` and `PublisherInfo` re-exported from the
  package root.

### Compatibility

Additive only. No breaking change from 0.1.0. Code written against
0.1.0 keeps working; the new dataclasses and fields are extra.

## [0.1.0] - 2026-05-21

### Added

- Initial public release. Sister package to `@gatefare/client`
  (TypeScript) — same protocol, same defense layers, Pythonic naming.
- `Gatefare` client class with three primitives: `list_catalog`,
  `call_api`, `check_balance` (plus `get_api`).
- Full x402 v2 flow: 402 challenge handling, EIP-3009 USDC signing,
  `X-Payment` header, response decoding.
- SDK-local spend caps (per-call + per-day, UTC-day reset) enforced
  before any signature is produced. `SpendCapError` raised on
  refusal.
- Quote-price cross-check against the catalog listing; refuses to
  sign if the server quote diverges more than 1%.
- Automatic claim retry via `/p/_claim/<id>` with exponential
  backoff for upstream failures after a successful settle.
- Framework adapters (no runtime dependency on the host framework):
  `gatefare.adapters.langchain`, `.llamaindex`, `.openai_tools`,
  `.anthropic_tools`.
- 28 pytest unit tests; live smoke script.
- Runtime dependencies: `httpx` and `eth-account` only (no
  `web3.py` — a single `eth_call` over httpx covers the one
  on-chain read).
