from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from texas_holdem_trainer.ai.profiles import BotStyle
from texas_holdem_trainer.ai.providers import (
    AIProvider,
    CodexAppServerProvider,
    HeuristicProvider,
    LLMProvider,
)
from texas_holdem_trainer.ai.service import AIService
from texas_holdem_trainer.runtime.table_manager import BotProviderTemplate, TableManager


DEFAULT_CONFIG_PATHS = (
    Path("config/ai_players.yaml"),
    Path("config/ai_players.example.yaml"),
)


def build_default_table_manager() -> TableManager:
    load_env_file(Path(os.getenv("THT_ENV_FILE", ".env")))
    config = load_ai_config()
    providers = build_providers(config.get("providers", {}))
    profile_templates = build_profile_templates(config, providers)
    reviewer_template = build_reviewer_template(config, providers)
    heuristic = providers["heuristic"]
    return TableManager(
        ai_service=AIService(
            primary_provider=heuristic,
            fallback_provider=heuristic,
            providers=providers,
            reviewer_provider=reviewer_template.provider,
            reviewer_model=reviewer_template.model,
        ),
        bot_provider_templates=profile_templates,
    )


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def load_ai_config() -> dict[str, Any]:
    configured_path = os.getenv("AI_PLAYERS_CONFIG")
    if configured_path:
        return _read_yaml(Path(configured_path))

    for path in DEFAULT_CONFIG_PATHS:
        if path.exists():
            return _read_yaml(path)
    return {}


def build_providers(raw_providers: Any) -> dict[str, AIProvider]:
    providers: dict[str, AIProvider] = {"heuristic": HeuristicProvider()}
    if not isinstance(raw_providers, dict):
        return providers

    timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "12") or "12")
    for name, raw_config in raw_providers.items():
        if not isinstance(name, str) or name == "heuristic":
            continue
        if not isinstance(raw_config, dict):
            continue

        if raw_config.get("runtime") == "codex_app_server":
            model = raw_config.get("model")
            if not isinstance(model, str):
                continue
            command = raw_config.get("command", "codex")
            if not isinstance(command, str):
                command = "codex"
            provider_timeout = raw_config.get("timeout_seconds", timeout)
            try:
                provider_timeout = float(provider_timeout)
            except (TypeError, ValueError):
                provider_timeout = timeout
            providers[name] = CodexAppServerProvider(
                command=command,
                model=model,
                timeout=provider_timeout,
            )
            continue

        api_key_env = raw_config.get("api_key_env")
        api_key = os.getenv(api_key_env) if isinstance(api_key_env, str) else None
        base_url = raw_config.get("base_url")
        model = raw_config.get("model")
        if not api_key or not isinstance(base_url, str) or not isinstance(model, str):
            continue

        providers[name] = LLMProvider(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout=timeout,
        )
    return providers


def build_profile_templates(
    config: dict[str, Any],
    providers: dict[str, AIProvider],
) -> dict[BotStyle, BotProviderTemplate]:
    default_provider = os.getenv("AI_DEFAULT_PROVIDER", "heuristic") or "heuristic"
    if default_provider not in providers:
        default_provider = "heuristic"

    templates = {
        style: BotProviderTemplate(
            provider=default_provider,
            model=_model_for_provider(default_provider, config),
        )
        for style in BotStyle
    }

    raw_profiles = config.get("profiles")
    if not isinstance(raw_profiles, list):
        return templates

    for raw_profile in raw_profiles:
        if not isinstance(raw_profile, dict):
            continue
        try:
            style = BotStyle(raw_profile.get("style"))
        except ValueError:
            continue

        provider = raw_profile.get("provider", default_provider)
        if not isinstance(provider, str) or provider not in providers:
            provider = "heuristic"
        model = raw_profile.get("model")
        if not isinstance(model, str):
            model = _model_for_provider(provider, config)
        templates[style] = BotProviderTemplate(provider=provider, model=model)

    return templates


def build_reviewer_template(
    config: dict[str, Any],
    providers: dict[str, AIProvider],
) -> BotProviderTemplate:
    raw_reviewer = config.get("reviewer")
    if not isinstance(raw_reviewer, dict):
        return BotProviderTemplate()
    provider = raw_reviewer.get("provider", "heuristic")
    if not isinstance(provider, str) or provider not in providers:
        provider = "heuristic"
    model = raw_reviewer.get("model")
    if not isinstance(model, str):
        model = _model_for_provider(provider, config)
    return BotProviderTemplate(provider=provider, model=model)


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        return {}
    return data


def _model_for_provider(provider: str, config: dict[str, Any]) -> str | None:
    if provider == "heuristic":
        return None
    providers = config.get("providers")
    if not isinstance(providers, dict):
        return None
    provider_config = providers.get(provider)
    if not isinstance(provider_config, dict):
        return None
    model = provider_config.get("model")
    return model if isinstance(model, str) else None
