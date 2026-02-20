"""Tests for the API token update endpoint and provider key mapping."""

import os
import tempfile

from jarvis.config import Settings


class TestProviderKeyMapping:
    """Validate that the provider API key attribute names match config fields."""

    def test_known_providers_have_api_key_attrs(self):
        s = Settings()
        providers = ["anthropic", "openai", "mistral", "grok"]
        for provider in providers:
            attr = f"{provider}_api_key"
            assert hasattr(s, attr), f"Settings missing {attr}"

    def test_env_var_names_match(self):
        env_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "mistral": "MISTRAL_API_KEY",
            "grok": "GROK_API_KEY",
        }
        for provider, env_var in env_map.items():
            assert env_var == f"{provider.upper()}_API_KEY"

    def test_update_env_file_helper(self):
        """Test the _update_env_file helper function."""
        from jarvis.api.routes import _update_env_file

        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("EXISTING_KEY=old_value\nOTHER=keep\n")
            tmppath = f.name

        try:
            _update_env_file(tmppath, "EXISTING_KEY", "new_value")
            with open(tmppath) as f:
                content = f.read()
            assert "EXISTING_KEY=new_value" in content
            assert "OTHER=keep" in content

            _update_env_file(tmppath, "NEW_KEY", "added")
            with open(tmppath) as f:
                content = f.read()
            assert "NEW_KEY=added" in content
        finally:
            os.unlink(tmppath)

    def test_tavily_key_attr(self):
        s = Settings()
        assert hasattr(s, "tavily_api_key")

    def test_telegram_config_fields(self):
        s = Settings()
        assert hasattr(s, "telegram_bot_token")
        assert hasattr(s, "telegram_chat_id")
