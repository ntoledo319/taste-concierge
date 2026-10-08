"""Shared fixtures: everything runs offline, no network, no env leakage."""

from __future__ import annotations

import pytest

from taste_concierge.agent import TasteConciergeAgent, TemplatePhraser
from taste_concierge.qloo_client import OfflineQlooClient


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Tests must never depend on (or leak) real credentials."""
    for var in ("QLOO_API_KEY", "QLOO_BASE_URL", "QLOO_OFFLINE",
                "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def offline_client():
    return OfflineQlooClient()


@pytest.fixture
def agent(offline_client):
    return TasteConciergeAgent(offline_client, phraser=TemplatePhraser())
