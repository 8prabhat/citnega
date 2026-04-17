# ADR-0004: keyring for Secret Storage

**Status:** Accepted  
**Date:** 2026-04-08

## Context

Citnega uses API keys to talk to remote model providers (OpenAI, etc.). Storing these keys in plaintext config files is a security risk. Hard-coding them in environment variables works but leaks them into process listings.

## Decision

Use the **`keyring`** library as the primary secret store:
- **macOS:** macOS Keychain  
- **Windows:** Windows Credential Manager  
- **Linux:** Secret Service (GNOME Keyring / KWallet) or `keyrings.alt` fallback

Implementation: `CompositeKeyStore` tries `KeyringKeyStore` first, then `EnvVarKeyStore` (reads `CITNEGA_<SERVICE>_API_KEY`).

Keys are **never** written to config files, JSONL logs, or tracebacks. `LogScrubber` enforces this with a denylist on field names (api_key, token, secret, password, authorization, credential, bearer, auth).

## Consequences

- Secrets stored in the OS credential manager — survives reboots, is not in source control.
- Environment variable fallback works in CI and containerized environments.
- `LogScrubber` provides defense-in-depth against accidental key exposure.
- Setting a key: `citnega config set-key <service> <env_var>` (prompts, stores securely).
