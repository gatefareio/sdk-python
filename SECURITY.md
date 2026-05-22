# Security policy

## Reporting a vulnerability

Email [security@gatefare.io](mailto:security@gatefare.io). Please include:

- The version of `gatefare` (or git commit) you found it in
- A short description, repro steps, and the impact
- (Optional) a suggested fix

We respond within 72 hours and aim to release a patched version within
7 days for high-severity issues. We will credit you in the CHANGELOG
unless you ask us not to.

## Don't open public issues for security bugs

GitHub Issues is public. If a vulnerability is exploitable, posting it
publicly hands a free attack to anyone watching the repo before we ship
a fix. Email instead.

## What's in scope

- The SDK itself (`gatefare` published to PyPI)
- The EIP-3009 signing flow in `gatefare/payment.py`
- The spend-cap enforcement in `gatefare/spend_cap.py` — specifically
  any path where a call could exceed the configured cap, or sign an
  authorization before the cap check runs
- The price-divergence guard in `call_api` — any path where the SDK
  would sign for a larger amount than the catalog quoted
- The HTTP client to `gatefare.io`
- Any leakage of the configured wallet private key via raised
  exceptions, log output, or returned objects

## What's out of scope

- Vulnerabilities in `gatefare.io` itself — still email
  [security@gatefare.io](mailto:security@gatefare.io), but they go to a
  different triage queue
- Issues in upstream dependencies (`httpx`, `eth-account`) — please
  report directly to those projects
- "The SDK lets a caller spend their own wallet" — that is the design.
  Configure `spend_caps` and fund the wallet with only what you intend
  to spend.

## Disclosure

Once a fix is released:

1. We publish a patched version on PyPI.
2. We open a GitHub Security Advisory describing the issue and which
   versions are affected.
3. The CHANGELOG gets a `### Security` line for that version.

We will not request CVEs unless the issue is severe and exploitable in
default configurations.
