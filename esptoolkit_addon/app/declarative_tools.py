"""
Declarative tool registry for MCP tools.

The manifest is the source of truth for tool intent and routing.
Handlers remain Python callables so complex behavior can still live in code.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Awaitable, Callable


HandlerCallable = Callable[..., Any] | Callable[..., Awaitable[Any]]


class DeclarativeToolRegistry:
    """Load tool definitions from JSON and dispatch execution by tool name."""

    def __init__(self, manifest_path: Path, handlers: dict[str, HandlerCallable]) -> None:
        self._manifest_path = manifest_path
        self._handlers = handlers
        self._tools = self._load_manifest(manifest_path)

    @staticmethod
    def _load_manifest(path: Path) -> dict[str, dict[str, Any]]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        tools = raw.get("tools")
        if not isinstance(tools, list):
            raise ValueError(f"Invalid manifest: 'tools' must be a list ({path})")

        by_name: dict[str, dict[str, Any]] = {}
        for tool in tools:
            if not isinstance(tool, dict):
                raise ValueError("Invalid manifest: each tool entry must be an object")
            name = tool.get("name")
            if not isinstance(name, str) or not name:
                raise ValueError("Invalid manifest: each tool must have a non-empty string 'name'")
            if name in by_name:
                raise ValueError(f"Duplicate tool definition in manifest: {name}")
            by_name[name] = tool
        return by_name

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self._tools

    def execute_sync(self, tool_name: str, **kwargs: Any) -> Any:
        tool = self._tools.get(tool_name)
        if not tool:
            raise KeyError(f"Unknown declarative tool: {tool_name}")
        if tool.get("executor") != "builtin":
            raise ValueError(f"Unsupported executor for {tool_name}: {tool.get('executor')!r}")
        handler_name = tool.get("handler")
        if not isinstance(handler_name, str) or not handler_name:
            raise ValueError(f"Tool {tool_name} has invalid handler")
        handler = self._handlers.get(handler_name)
        if not handler:
            raise KeyError(f"Tool {tool_name} references missing handler: {handler_name}")
        manifest_args = tool.get("args", {})
        if manifest_args and not isinstance(manifest_args, dict):
            raise ValueError(f"Tool {tool_name} has invalid args section; expected object")
        call_kwargs = dict(manifest_args)
        call_kwargs.update(kwargs)
        result = handler(**call_kwargs)
        if hasattr(result, "__await__"):
            raise TypeError(f"Tool {tool_name} is async; call execute() instead")
        return result

    async def execute(self, tool_name: str, **kwargs: Any) -> Any:
        tool = self._tools.get(tool_name)
        if not tool:
            raise KeyError(f"Unknown declarative tool: {tool_name}")

        if tool.get("executor") != "builtin":
            raise ValueError(f"Unsupported executor for {tool_name}: {tool.get('executor')!r}")

        handler_name = tool.get("handler")
        if not isinstance(handler_name, str) or not handler_name:
            raise ValueError(f"Tool {tool_name} has invalid handler")
        handler = self._handlers.get(handler_name)
        if not handler:
            raise KeyError(f"Tool {tool_name} references missing handler: {handler_name}")

        manifest_args = tool.get("args", {})
        if manifest_args and not isinstance(manifest_args, dict):
            raise ValueError(f"Tool {tool_name} has invalid args section; expected object")
        call_kwargs = dict(manifest_args)
        call_kwargs.update(kwargs)
        result = handler(**call_kwargs)
        if hasattr(result, "__await__"):
            return await result  # async handler
        return result
