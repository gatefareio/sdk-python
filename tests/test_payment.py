import base64
import json
import re

from gatefare.payment import (
    PaymentRequirements,
    sign_eip3009_authorization,
    usdc_to_micros,
)
from gatefare.wallet import create_wallet_state


def test_signed_payload_structure(test_private_key):
    wallet = create_wallet_state(test_private_key, "eip155:84532")
    signed = sign_eip3009_authorization(
        wallet,
        PaymentRequirements(
            value="10000",  # $0.01 in micros
            pay_to="0x0000000000000000000000000000000000000001",
            network="eip155:84532",
            resource="https://gatefare.io/p/alice/weather-now",
        ),
        now=1_716_000_000.0,
    )

    assert signed.value_micros == 10_000
    assert re.match(r"^0x[0-9a-f]{64}$", signed.nonce_hex)
    assert signed.valid_before_sec == 1_716_000_300

    decoded = json.loads(base64.b64decode(signed.x_payment_header).decode("utf-8"))
    assert decoded["x402Version"] == 2
    assert decoded["scheme"] == "exact"
    assert decoded["network"] == "eip155:84532"
    assert re.match(r"^0x[0-9a-f]{130}$", decoded["payload"]["signature"])
    assert decoded["payload"]["authorization"]["value"] == "10000"
    assert decoded["payload"]["authorization"]["validBefore"] == "1716000300"
    assert decoded["payload"]["authorization"]["nonce"] == signed.nonce_hex


def test_signature_address_matches_account(test_private_key):
    wallet = create_wallet_state(test_private_key, "eip155:8453")
    signed = sign_eip3009_authorization(
        wallet,
        PaymentRequirements(
            value="1000000",
            pay_to="0x0000000000000000000000000000000000000001",
            network="eip155:8453",
            resource="https://gatefare.io/p/foo/bar",
        ),
    )
    decoded = json.loads(base64.b64decode(signed.x_payment_header).decode("utf-8"))
    assert decoded["payload"]["authorization"]["from"].lower() == wallet.account.address.lower()


def test_usdc_to_micros():
    assert usdc_to_micros(1) == 1_000_000
    assert usdc_to_micros("0.01") == 10_000
    assert usdc_to_micros("0.000001") == 1
    assert usdc_to_micros("1234.56") == 1_234_560_000
