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
    gmail_user_password: Optional[str] = None  # Regular Gmail password (not for SMTP)
    gmail_app_password: Optional[str] = None   # Gmail App Password (for SMTP/IMAP)

    # SMTP (for send_email tool — defaults to Gmail SMTP)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_use_starttls: bool = True
    smtp_username: Optional[str] = None   # Falls back to gmail_address
    smtp_password: Optional[str] = None   # Falls back to gmail_password (use App Password for Gmail)
    smtp_from_address: Optional[str] = None  # Falls back to smtp_username/gmail_address

    # Email inbox listener
    email_listener_enabled: bool = False
    email_listener_interval_seconds: int = 300  # 5 minutes

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
