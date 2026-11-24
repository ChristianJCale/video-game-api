"""Reads the API key from Azure Key Vault and caches it for a short time.

Locally, DefaultAzureCredential uses your `az login`; in Azure it uses the
Function App's managed identity. The key is never logged.
"""
import logging
import os
import threading
import time

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

SECRET_NAME = os.environ.get("API_KEY_SECRET_NAME", "api-key")
# Short TTL: a rotated key takes effect within this many seconds, with no redeploy
CACHE_TTL_SECONDS = int(os.environ.get("API_KEY_CACHE_TTL_SECONDS", "60"))

_client = None
_value = None
_fetched_at = 0.0
_lock = threading.Lock()


def _get_client():
    global _client
    if _client is None:
        vault_url = os.environ.get("KEY_VAULT_URL")
        if not vault_url:
            raise RuntimeError("KEY_VAULT_URL is not configured")
        _client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())
    return _client


def get_api_key(now=time.monotonic):
    """Return the API key, re-reading it from Key Vault once the cache is older than the TTL.

    `now` can be replaced in a unit test with a fake clock.
    """
    global _value, _fetched_at
    if _value is not None and now() - _fetched_at < CACHE_TTL_SECONDS:
        return _value
    with _lock:
        # Re-check inside the lock: another request may have refreshed it while we waited
        if _value is not None and now() - _fetched_at < CACHE_TTL_SECONDS:
            return _value
        secret = _get_client().get_secret(SECRET_NAME)
        if not secret.value:
            raise RuntimeError("The api-key secret is empty")
        _value, _fetched_at = secret.value, now()
        # Log the version id (never the value): it proves a rotation was picked up
        logging.info("api_key_refreshed secretVersion=%s", secret.properties.version)
        return _value