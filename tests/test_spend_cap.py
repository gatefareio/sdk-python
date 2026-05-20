import time

import pytest

from gatefare import SpendCapError
from gatefare.spend_cap import DEFAULT_SPEND_CAPS, SpendCapManager


def test_authorizes_call_under_both_caps():
    m = SpendCapManager()
    m.authorize(0.5)  # must not raise


def test_throws_spend_cap_error_when_per_call_cap_exceeded():
    m = SpendCapManager(caps={"per_call_usdc": 0.1})
    with pytest.raises(SpendCapError) as exc_info:
        m.authorize(0.2)
    err = exc_info.value
    assert err.reason == "per_call_cap_exceeded"
    assert err.cap_usdc == 0.1
    assert err.attempted_usdc == 0.2


def test_per_call_override_respected():
    m = SpendCapManager(caps={"per_call_usdc": 0.1})
    m.authorize(5.0, per_call_override_usdc=10.0)  # override allows


def test_daily_cap_blocks_cumulative():
    m = SpendCapManager(caps={"per_call_usdc": 5, "per_day_usdc": 10})
    m.record(7)
    with pytest.raises(SpendCapError) as exc_info:
        m.authorize(5)
    assert exc_info.value.reason == "per_day_cap_exceeded"
    assert exc_info.value.cap_usdc == 10


def test_authorize_does_not_charge():
    m = SpendCapManager()
    m.authorize(0.5)
    m.authorize(0.5)
    assert m.spent_today_usdc() == 0


def test_record_accumulates():
    m = SpendCapManager()
    m.record(0.10)
    m.record(0.20)
    m.record(0.05)
    assert m.spent_today_usdc() == pytest.approx(0.35, abs=1e-6)


def test_utc_day_rollover_resets_counter():
    # 2026-01-01 23:59 UTC → 2026-01-02 00:01 UTC
    now_holder = {"t": 1_767_311_940.0}
    m = SpendCapManager(
        caps={"per_day_usdc": 1.0},
        now=lambda: now_holder["t"],
    )
    m.record(0.80)
    assert m.spent_today_usdc() == pytest.approx(0.80, abs=1e-6)

    now_holder["t"] = 1_767_312_060.0  # next UTC day
    assert m.spent_today_usdc() == 0
    assert m.remaining_today_usdc() == pytest.approx(1.0, abs=1e-6)


def test_default_caps():
    assert DEFAULT_SPEND_CAPS["per_call_usdc"] == 1.0
    assert DEFAULT_SPEND_CAPS["per_day_usdc"] == 10.0


def test_rejects_nan_and_negative():
    m = SpendCapManager()
    with pytest.raises(SpendCapError):
        m.authorize(float("nan"))
    with pytest.raises(SpendCapError):
        m.authorize(-1)


def test_remaining_floors_at_zero():
    m = SpendCapManager(caps={"per_day_usdc": 1.0})
    m.record(1.5)
    assert m.remaining_today_usdc() == 0
