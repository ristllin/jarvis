from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # API Keys
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    mistral_api_key: str | None = None
    grok_api_key: str | None = None
    tavily_api_key: str | None = None

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
    git_password: str | None = None
    github_token: str | None = None  # Personal Access Token for push/pull
    github_repo: str | None = None  # e.g. https://github.com/user/jarvis.git
    gmail_address: str | None = None
    gmail_user_password: str | None = None  # Regular Gmail password (not for SMTP)
    gmail_app_password: str | None = None  # Gmail App Password (for SMTP/IMAP)

    # SMTP (for send_email tool — defaults to Gmail SMTP)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_use_starttls: bool = True
    smtp_username: str | None = None  # Falls back to gmail_address
    smtp_password: str | None = None  # Falls back to gmail_password (use App Password for Gmail)
    smtp_from_address: str | None = None  # Falls back to smtp_username/gmail_address

    # Email inbox listener
    email_listener_enabled: bool = False
    email_listener_interval_seconds: int = 300  # 5 minutes

    # Dashboard auth (Google OAuth — for remote/ngrok access)
    auth_enabled: bool = False
    auth_base_url: str = "http://localhost"  # Base URL for OAuth redirects (use ngrok URL when remote)
    auth_secret_key: str = "change-me-in-production"
    google_client_id: str | None = None
    google_client_secret: str | None = None
    allowed_emails: str = "ristlin@gmail.com,jarvis.bot.g.d@gmail.com"  # Comma-separated

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

    @property
    def allowed_emails_set(self) -> set[str]:
        return {e.strip().lower() for e in self.allowed_emails.split(",") if e.strip()}


settings = Settings()
