"""Shared pytest fixtures."""

import pytest

# Pinned well-known throwaway key used by Web3 docs.
TEST_PRIVATE_KEY = "0x4c0883a69102937d6231471b5dbb6204fe5129617082792ae468d01a3f362318"


@pytest.fixture
def test_private_key() -> str:
    return TEST_PRIVATE_KEY
