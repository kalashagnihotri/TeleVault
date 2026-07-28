import logging
import json
from typing import Any

from src.config import Config

class RedactingFormatter(logging.Formatter):
    """
    A custom formatter that redacts sensitive information such as tokens and api hashes.
    """
    def __init__(self, secrets_to_redact: list[str], *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.secrets = [s for s in secrets_to_redact if s]

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        for secret in self.secrets:
            if secret in original:
                original = original.replace(secret, "***REDACTED***")
        return original

def setup_logger(config: Config) -> logging.Logger:
    logger = logging.getLogger("telegram_media")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        logger.handlers.clear()

    # Redact the bot_token and api_hash
    secrets_to_redact = [
        config.secrets.bot_token,
        config.secrets.api_hash
    ]

    formatter = RedactingFormatter(
        secrets_to_redact,
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    config.app.log_directory.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(config.app.log_directory / "app.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
