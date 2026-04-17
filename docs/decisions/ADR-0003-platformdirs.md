# ADR-0003: platformdirs via PathResolver

**Status:** Accepted  
**Date:** 2026-04-08

## Context

Citnega runs on Linux, macOS, and Windows. Each platform has different conventions for where applications store data, config, and logs. Hard-coding paths like `~/.citnega` works on Linux/macOS but is incorrect on Windows.

## Decision

All path construction goes through a single `PathResolver` class in `packages/storage/path_resolver.py`. This is the **only** module permitted to import `platformdirs`. No other module constructs application paths directly.

Platform-resolved directories:
- **Linux:** `~/.local/share/citnega/`  
- **macOS:** `~/Library/Application Support/citnega/`  
- **Windows:** `%APPDATA%\citnega\`

On Unix-like systems, `PathResolver` applies permissions: 0700 for directories, 0600 for files. On Windows, the OS default permissions apply.

## Consequences

- Cross-platform path correctness by construction.
- Single point of change if path conventions evolve.
- Import-linter can verify that only `storage/path_resolver.py` imports `platformdirs`.
