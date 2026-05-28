from __future__ import annotations

import os
from pathlib import Path

from texas_holdem_trainer.ai.profiles import BotStyle
from texas_holdem_trainer.api.schemas import CreateTableRequest
from texas_holdem_trainer.runtime.config import (
    build_default_table_manager,
    build_profile_templates,
    build_providers,
    load_env_file,
)


def test_env_and_yaml_config_wire_llm_provider_into_table_manager(
    tmp_path: Path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=test-key",
                "AI_DEFAULT_PROVIDER=openai",
                "AI_PLAYERS_CONFIG=" + str(tmp_path / "ai_players.yaml"),
            ]
        ),
        encoding="utf-8",
    )
    config_file = tmp_path / "ai_players.yaml"
    config_file.write_text(
        """
providers:
  openai:
    base_url: "https://api.openai.test/v1"
    api_key_env: "OPENAI_API_KEY"
    model: "test-gpt"
profiles:
  - name: "TAG Bot"
    style: "tight_aggressive"
    provider: "openai"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("THT_ENV_FILE", str(env_file))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AI_DEFAULT_PROVIDER", raising=False)
    monkeypatch.delenv("AI_PLAYERS_CONFIG", raising=False)

    manager = build_default_table_manager()
    state = manager.create_table(
        CreateTableRequest(
            bot_count=1,
            bot_styles=["tight_aggressive"],
            starting_stack=500,
            small_blind=5,
            big_blind=10,
        )
    )

    assert state.ai_provider_status == "openai/test-gpt"


def test_missing_llm_key_falls_back_to_heuristic_provider(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("AI_DEFAULT_PROVIDER", "openai")
    config = {
        "providers": {
            "openai": {
                "base_url": "https://api.openai.test/v1",
                "api_key_env": "OPENAI_API_KEY",
                "model": "test-gpt",
            }
        },
        "profiles": [
            {
                "style": "tight_aggressive",
                "provider": "openai",
            }
        ],
    }

    providers = build_providers(config["providers"])
    templates = build_profile_templates(config, providers)

    assert set(providers) == {"heuristic"}
    assert templates[BotStyle.TIGHT_AGGRESSIVE].provider == "heuristic"


def test_codex_app_server_provider_does_not_require_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = {
        "providers": {
            "codex_app": {
                "runtime": "codex_app_server",
                "command": "codex",
                "model": "gpt-5.5",
                "timeout_seconds": 60,
            }
        },
        "profiles": [
            {
                "style": "gto_leaning",
                "provider": "codex_app",
            }
        ],
    }

    providers = build_providers(config["providers"])
    templates = build_profile_templates(config, providers)

    assert set(providers) == {"heuristic", "codex_app"}
    assert templates[BotStyle.GTO_LEANING].provider == "codex_app"
    assert templates[BotStyle.GTO_LEANING].model == "gpt-5.5"


def test_load_env_file_does_not_override_existing_environment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=file-key\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "shell-key")

    load_env_file(env_file)

    assert os.environ["OPENAI_API_KEY"] == "shell-key"
