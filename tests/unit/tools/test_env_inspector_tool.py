"""Tests for EnvInspectorTool — sensitive var redaction."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from citnega.packages.tools.builtin.env_inspector_tool import EnvInspectorInput, EnvInspectorTool


@pytest.fixture()
def tool():
    return EnvInspectorTool.__new__(EnvInspectorTool)


async def test_sensitive_vars_redacted(tool) -> None:
    env = {"MY_API_KEY": "supersecret", "HOME": "/home/user", "AUTH_TOKEN": "abc123"}
    with patch.dict(os.environ, env, clear=True):
        result = await tool._execute(EnvInspectorInput(), context=None)

    names = {e.name for e in result.env_vars}
    assert "MY_API_KEY" in names
    assert "AUTH_TOKEN" in names

    for entry in result.env_vars:
        if entry.name in ("MY_API_KEY", "AUTH_TOKEN"):
            assert entry.value == "***REDACTED***"
            assert entry.is_redacted


async def test_non_sensitive_vars_visible(tool) -> None:
    env = {"HOME": "/home/user", "SHELL": "/bin/zsh"}
    with patch.dict(os.environ, env, clear=True):
        result = await tool._execute(EnvInspectorInput(), context=None)

    for entry in result.env_vars:
        if entry.name in ("HOME", "SHELL"):
            assert not entry.is_redacted
            assert entry.value != "***REDACTED***"


async def test_filter_prefix(tool) -> None:
    env = {"MY_VAR": "1", "MY_OTHER": "2", "OTHER": "3"}
    with patch.dict(os.environ, env, clear=True):
        result = await tool._execute(EnvInspectorInput(filter_prefix="MY_"), context=None)

    names = {e.name for e in result.env_vars}
    assert "MY_VAR" in names
    assert "MY_OTHER" in names
    assert "OTHER" not in names


async def test_redacted_count_correct(tool) -> None:
    env = {"API_KEY": "x", "SECRET": "y", "NORMAL": "z"}
    with patch.dict(os.environ, env, clear=True):
        result = await tool._execute(EnvInspectorInput(), context=None)

    assert result.redacted_count == 2


async def test_include_packages(tool) -> None:
    result = await tool._execute(EnvInspectorInput(include_packages=True), context=None)
    assert result.packages is not None
    assert any("pytest" in pkg for pkg in result.packages)
