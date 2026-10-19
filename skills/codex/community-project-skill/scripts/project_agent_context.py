#!/usr/bin/env python3
"""Normalize public Agent and model metadata for Project task executions."""

from __future__ import annotations

import os
from argparse import ArgumentParser, Namespace
from typing import Any


ENV_SOURCE_TOOL = "YEYING_AGENT_SOURCE_TOOL"
ENV_MODEL = "YEYING_AGENT_MODEL"
ENV_MODEL_PROVIDER = "YEYING_AGENT_MODEL_PROVIDER"
ENV_CLIENT_VERSION = "YEYING_AGENT_CLIENT_VERSION"
ENV_REASONING_EFFORT = "YEYING_AGENT_REASONING_EFFORT"


def optional_text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _resolved(explicit: Any, env_name: str, *, use_environment: bool = True) -> tuple[str | None, str | None]:
    value = optional_text(explicit)
    if value is not None:
        return value, "argument"
    if not use_environment:
        return None, None
    value = optional_text(os.environ.get(env_name))
    return value, "environment" if value is not None else None


def build_agent_context(
    source_tool: Any = None,
    model: Any = None,
    model_provider: Any = None,
    client_version: Any = None,
    reasoning_effort: Any = None,
    model_source: str | None = None,
    model_role: str = "primary",
    model_missing_reason: str | None = None,
    use_environment: bool = True,
) -> dict[str, Any]:
    provided_model = optional_text(model)
    resolved_tool, _ = _resolved(source_tool, ENV_SOURCE_TOOL, use_environment=use_environment)
    resolved_model, resolved_model_source = _resolved(model, ENV_MODEL, use_environment=use_environment)
    resolved_provider, _ = _resolved(model_provider, ENV_MODEL_PROVIDER, use_environment=use_environment)
    resolved_client_version, _ = _resolved(client_version, ENV_CLIENT_VERSION, use_environment=use_environment)
    resolved_effort, _ = _resolved(reasoning_effort, ENV_REASONING_EFFORT, use_environment=use_environment)
    models: list[dict[str, Any]] = []
    if resolved_model:
        entry = {
            "id": resolved_model,
            "role": optional_text(model_role) or "primary",
            "source": (optional_text(model_source) if provided_model else None) or resolved_model_source or "host",
        }
        if resolved_provider:
            entry["provider"] = resolved_provider
        if resolved_effort:
            entry["reasoning_effort"] = resolved_effort
        models.append(entry)
    return {
        "source_tool": resolved_tool,
        "client_version": resolved_client_version,
        "models": models,
        "model_missing_reason": None if models else optional_text(model_missing_reason),
    }


def primary_model(agent: dict[str, Any] | None) -> str | None:
    if not isinstance(agent, dict):
        return None
    models = agent.get("models")
    if not isinstance(models, list):
        return None
    primary = next(
        (item for item in models if isinstance(item, dict) and item.get("role") == "primary" and item.get("id")),
        None,
    )
    selected = primary or next(
        (item for item in models if isinstance(item, dict) and item.get("id")),
        None,
    )
    return optional_text(selected.get("id")) if selected else None


def ensure_state_agent_context(state: dict[str, Any]) -> dict[str, Any]:
    current = state.get("agent")
    if isinstance(current, dict):
        agent = {
            "source_tool": optional_text(current.get("source_tool")) or optional_text(state.get("source_tool")),
            "client_version": optional_text(current.get("client_version")),
            "models": [item for item in current.get("models", []) if isinstance(item, dict) and item.get("id")],
            "model_missing_reason": optional_text(current.get("model_missing_reason")),
        }
    else:
        agent = build_agent_context(
            source_tool=state.get("source_tool"),
            model=state.get("model"),
            model_source="legacy_state",
            use_environment=False,
        )
    legacy_model = optional_text(state.get("model"))
    if legacy_model and not any(optional_text(item.get("id")) == legacy_model for item in agent["models"]):
        agent["models"].insert(0, {"id": legacy_model, "role": "primary", "source": "legacy_state"})
    if agent["models"]:
        agent["model_missing_reason"] = None
    state["agent"] = agent
    state["source_tool"] = agent.get("source_tool") or optional_text(state.get("source_tool")) or "unknown"
    state["model"] = primary_model(agent)
    return agent


def merge_state_agent_context(
    state: dict[str, Any],
    candidate: dict[str, Any] | None,
    *,
    locked: bool = False,
) -> dict[str, Any]:
    agent = ensure_state_agent_context(state)
    if not isinstance(candidate, dict):
        return agent
    candidate_tool = optional_text(candidate.get("source_tool"))
    if candidate_tool and not agent.get("source_tool"):
        agent["source_tool"] = candidate_tool
    candidate_version = optional_text(candidate.get("client_version"))
    if candidate_version and not agent.get("client_version"):
        agent["client_version"] = candidate_version
    for incoming in candidate.get("models", []):
        if not isinstance(incoming, dict):
            continue
        model_id = optional_text(incoming.get("id"))
        if not model_id:
            continue
        existing = next((item for item in agent["models"] if optional_text(item.get("id")) == model_id), None)
        if existing:
            for key in ("provider", "reasoning_effort", "source"):
                value = optional_text(incoming.get(key))
                if value and not existing.get(key):
                    existing[key] = value
            continue
        if locked:
            raise ValueError(f"执行归档已冻结，不能追加模型: {model_id}")
        role = optional_text(incoming.get("role")) or ("primary" if not agent["models"] else "participant")
        if role == "primary" and any(item.get("role") == "primary" for item in agent["models"]):
            role = "participant"
        entry = {"id": model_id, "role": role, "source": optional_text(incoming.get("source")) or "event"}
        for key in ("provider", "reasoning_effort"):
            value = optional_text(incoming.get(key))
            if value:
                entry[key] = value
        agent["models"].append(entry)
    if agent["models"]:
        agent["model_missing_reason"] = None
    elif candidate.get("model_missing_reason") and not agent.get("model_missing_reason"):
        agent["model_missing_reason"] = optional_text(candidate.get("model_missing_reason"))
    state["agent"] = agent
    state["source_tool"] = agent.get("source_tool") or state.get("source_tool") or "unknown"
    state["model"] = primary_model(agent)
    return agent


def event_agent_context(event: dict[str, Any]) -> dict[str, Any] | None:
    metadata = event.get("metadata")
    if not isinstance(metadata, dict):
        return None
    nested = metadata.get("agent")
    if isinstance(nested, dict):
        return nested
    model = optional_text(metadata.get("model") or metadata.get("model_id") or metadata.get("model_name"))
    source_tool = optional_text(metadata.get("source_tool") or metadata.get("client"))
    client_version = optional_text(metadata.get("client_version"))
    if not any((model, source_tool, client_version)):
        return None
    return build_agent_context(
        source_tool=source_tool,
        model=model,
        model_provider=metadata.get("model_provider") or metadata.get("provider"),
        client_version=client_version,
        reasoning_effort=metadata.get("reasoning_effort"),
        model_source="event",
        model_role=optional_text(metadata.get("model_role")) or "primary",
        use_environment=False,
    )


def public_event_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract only public execution identity fields from a native client event."""
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    nested_agent = payload.get("agent") if isinstance(payload.get("agent"), dict) else {}
    metadata_agent = metadata.get("agent") if isinstance(metadata.get("agent"), dict) else {}
    sources = (payload, metadata, nested_agent, metadata_agent)

    def first(*keys: str) -> Any:
        for source in sources:
            for key in keys:
                if source.get(key) is not None:
                    return source[key]
        return None

    raw_model = first("model", "model_id", "modelId", "model_name", "modelName")
    model_provider = first("model_provider", "modelProvider", "provider")
    if isinstance(raw_model, dict):
        model_provider = raw_model.get("provider") or model_provider
        raw_model = raw_model.get("id") or raw_model.get("name") or raw_model.get("value")
    result: dict[str, Any] = {}
    fields = {
        "model": raw_model,
        "model_provider": model_provider,
        "model_role": first("model_role", "modelRole"),
        "reasoning_effort": first("reasoning_effort", "reasoningEffort"),
        "client_version": first("client_version", "clientVersion"),
        "source_tool": first("source_tool", "sourceTool", "client"),
    }
    for key, value in fields.items():
        normalized = optional_text(value)
        if normalized:
            result[key] = normalized
    return result


def context_from_args(args: Namespace, *, missing_reason: str | None = None) -> dict[str, Any]:
    return build_agent_context(
        source_tool=getattr(args, "source_tool", None),
        model=getattr(args, "model", None),
        model_provider=getattr(args, "model_provider", None),
        client_version=getattr(args, "client_version", None),
        reasoning_effort=getattr(args, "reasoning_effort", None),
        model_missing_reason=missing_reason,
    )


def add_agent_arguments(parser: ArgumentParser, *, include_source_tool: bool = False, source_tool_required: bool = False) -> None:
    if include_source_tool:
        parser.add_argument(
            "--source-tool",
            required=source_tool_required and not optional_text(os.environ.get(ENV_SOURCE_TOOL)),
            help=f"codex、claude 或其他执行工具；也可使用 {ENV_SOURCE_TOOL}",
        )
    parser.add_argument("--model", help=f"主模型 ID；也可使用 {ENV_MODEL}")
    parser.add_argument("--model-provider", help=f"模型提供方；也可使用 {ENV_MODEL_PROVIDER}")
    parser.add_argument("--client-version", help=f"Agent 客户端版本；也可使用 {ENV_CLIENT_VERSION}")
    parser.add_argument("--reasoning-effort", help=f"公开的推理强度；也可使用 {ENV_REASONING_EFFORT}")
