"""Tests for JSONQueryTool."""

from __future__ import annotations

import json

import pytest

from citnega.packages.tools.builtin.json_query_tool import JSONQueryInput, JSONQueryTool


@pytest.fixture()
def tool():
    return JSONQueryTool.__new__(JSONQueryTool)


async def test_simple_key(tool) -> None:
    data = json.dumps({"name": "alice"})
    result = await tool._execute(JSONQueryInput(source=data, query="name"), context=None)
    assert result.result == "alice"
    assert result.result_type == "str"


async def test_nested_dot_path(tool) -> None:
    data = json.dumps({"user": {"age": 30}})
    result = await tool._execute(JSONQueryInput(source=data, query="user.age"), context=None)
    assert result.result == 30


async def test_array_index(tool) -> None:
    data = json.dumps({"items": ["a", "b", "c"]})
    result = await tool._execute(JSONQueryInput(source=data, query="items[1]"), context=None)
    assert result.result == "b"


async def test_wildcard(tool) -> None:
    data = json.dumps({"users": [{"id": 1}, {"id": 2}]})
    result = await tool._execute(JSONQueryInput(source=data, query="users[*]"), context=None)
    assert isinstance(result.result, list)
    assert result.count == 2


async def test_file_source(tool, tmp_path) -> None:
    f = tmp_path / "data.json"
    f.write_text(json.dumps({"key": "value"}))
    result = await tool._execute(JSONQueryInput(source=str(f), query="key"), context=None)
    assert result.result == "value"


async def test_missing_key_raises(tool) -> None:
    data = json.dumps({"a": 1})
    with pytest.raises(Exception):
        await tool._execute(JSONQueryInput(source=data, query="b.c"), context=None)
