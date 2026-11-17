import os


class Config:
    timeout: int = 30
    max_retries: int = 3
    user_agent: str = "Mozilla/5.0 (AI Agent)"

    def __init__(self, timeout: int, max_retries: int, user_agent: str) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.user_agent = user_agent

    @classmethod
    def load(cls) -> "Config":
        return cls(
            timeout=int(os.getenv("FETCH_TIMEOUT", cls.timeout)),
            max_retries=int(os.getenv("MAX_RETRIES", cls.max_retries)),
            user_agent=os.getenv("UA", cls.user_agent),
        )