from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    # Gmail POP3
    gmail_email: str = "dijiaozhibei@gmail.com"
    gmail_app_password: str = ""
    gmail_pop3_host: str = "pop.gmail.com"
    gmail_pop3_port: int = 995

    # Account
    account_password: str = "AetherTest123!"
    account_email_base: str = "dijiaozhibei"

    # Batch
    batch_start: int = 2
    batch_end: int = 10

    # Aether
    aether_base_url: str = "https://to-aether.com"
    aether_api_base: str = "https://to-aether.com/api/v1"

    # CapSolver (optional)
    capsolver_api_key: Optional[str] = None

    # Manual Turnstile token (also optional)
    # If set, all accounts will use this same token.
    # Token expires ~5 minutes, so works for small batches.
    turnstile_token: Optional[str] = None

    # Target groups (comma separated, empty = all available)
    target_groups: str = ""

    # Wait time between registrations (seconds)
    register_interval: int = 30

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def target_group_list(self) -> List[str]:
        if not self.target_groups:
            return []
        return [g.strip() for g in self.target_groups.split(",") if g.strip()]


settings = Settings()
