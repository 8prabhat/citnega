"""
Key store implementations.

KeyringKeyStore   — OS-native secret storage (macOS Keychain / Windows
                    Credential Manager / Linux Secret Service).
EnvVarKeyStore    — Reads from environment variables (CI / containers).
CompositeKeyStore — Tries keyring first, falls back to env vars.
"""

from __future__ import annotations

import os

from citnega.packages.protocol.interfaces.key_store import IKeyStore
from citnega.packages.shared.errors import KeyStoreError


class KeyringKeyStore(IKeyStore):
    """Stores and retrieves secrets using the OS keyring."""

    def get_key(self, service: str, key_name: str) -> str | None:
        try:
            import keyring  # only imported here

            return keyring.get_password(service, key_name)
        except Exception as exc:
            raise KeyStoreError(
                f"Keyring get failed for service={service!r} key={key_name!r}: {exc}",
                original=exc,
            ) from exc

    def set_key(self, service: str, key_name: str, value: str) -> None:
        try:
            import keyring

            keyring.set_password(service, key_name, value)
        except Exception as exc:
            raise KeyStoreError(
                f"Keyring set failed for service={service!r} key={key_name!r}: {exc}",
                original=exc,
            ) from exc

    def delete_key(self, service: str, key_name: str) -> None:
        try:
            import keyring

            keyring.delete_password(service, key_name)
        except Exception as exc:
            raise KeyStoreError(
                f"Keyring delete failed for service={service!r} key={key_name!r}: {exc}",
                original=exc,
            ) from exc


class EnvVarKeyStore(IKeyStore):
    """
    Reads secrets from environment variables.

    Convention: CITNEGA_<SERVICE>_<KEY_NAME> (upper-cased, hyphens → underscores).
    """

    @staticmethod
    def _env_var_name(service: str, key_name: str) -> str:
        return f"CITNEGA_{service}_{key_name}".upper().replace("-", "_")

    def get_key(self, service: str, key_name: str) -> str | None:
        return os.environ.get(self._env_var_name(service, key_name))

    def set_key(self, service: str, key_name: str, value: str) -> None:
        os.environ[self._env_var_name(service, key_name)] = value

    def delete_key(self, service: str, key_name: str) -> None:
        os.environ.pop(self._env_var_name(service, key_name), None)


class CompositeKeyStore(IKeyStore):
    """
    Tries each store in order, returning the first non-None value.

    Default order: KeyringKeyStore → EnvVarKeyStore.
    ``set_key`` and ``delete_key`` operate on the first store only (keyring).
    """

    def __init__(self, stores: list[IKeyStore] | None = None) -> None:
        if stores is None:
            stores = [KeyringKeyStore(), EnvVarKeyStore()]
        self._stores = stores

    def get_key(self, service: str, key_name: str) -> str | None:
        for store in self._stores:
            try:
                value = store.get_key(service, key_name)
                if value is not None:
                    return value
            except KeyStoreError:
                continue
        return None

    def set_key(self, service: str, key_name: str, value: str) -> None:
        self._stores[0].set_key(service, key_name, value)

    def delete_key(self, service: str, key_name: str) -> None:
        self._stores[0].delete_key(service, key_name)
