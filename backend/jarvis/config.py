from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # API Keys
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    mistral_api_key: Optional[str] = None
    tavily_api_key: Optional[str] = None

    # Ollama
    ollama_host: str = "http://ollama:11434"

    # Data
    data_dir: str = "/data"

    # Budget
    monthly_budget_usd: float = 100.0

    # Core Loop
    loop_interval_seconds: int = 30
    iteration_timeout_seconds: int = 300
    heartbeat_timeout_seconds: int = 600

    # Git / Gmail / GitHub
    git_user_name: str = "JARVIS"
    git_user_email: str = "jarvis.bot.g.d@gmail.com"
    git_password: Optional[str] = None
    github_token: Optional[str] = None  # Personal Access Token for push/pull
    github_repo: Optional[str] = None   # e.g. https://github.com/user/jarvis.git
    gmail_address: Optional[str] = None
    gmail_password: Optional[str] = None
    gmail_app_password: Optional[str] = None  # For SMTP with App Passwords

    # SMTP Configuration (defaults to Gmail)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_use_starttls: bool = True
    smtp_username: Optional[str] = None  # Overrides gmail_address if set
    smtp_password: Optional[str] = None  # Overrides gmail_app_password if set
    smtp_from_address: Optional[str] = None  # Defaults to smtp_username or gmail_address

    # Initial directive
    initial_directive: str = (
        "Improve yourself — optimize your own code, memory, and capabilities. "
        "Care about your creator and communicate meaningfully. "
        "Explore the world through your tools. "
        "Seek ways to generate value and resources by working in the world, "
        "expanding your LLM capabilities and adding new provider support and API keys "
        "when you can acquire them. Always be transparent about what you are doing and why."
    )

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
