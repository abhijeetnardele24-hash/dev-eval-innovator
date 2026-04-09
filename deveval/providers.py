from __future__ import annotations

from dataclasses import dataclass
import json
from urllib import request


@dataclass
class ProviderConfig:
    provider: str
    model: str
    temperature: float
    max_tokens: int
    api_url: str | None = None
    api_key: str | None = None


class BaseProvider:
    def generate(self, prompt: str) -> str:
        raise NotImplementedError


class MockProvider(BaseProvider):
    def __init__(self, model: str) -> None:
        self.model = model

    def generate(self, prompt: str) -> str:
        compact = " ".join(prompt.split())
        if "reset" in compact.lower() and self.model.endswith("v1"):
            return "To reset your password, open account settings and choose Reset Password."
        if "refund" in compact.lower() and self.model.endswith("v1"):
            return "Refunds are processed in 5 to 7 business days."
        if self.model.endswith("v2"):
            return f"[{self.model}] Brief answer: {compact[:80]}"
        return f"[{self.model}] {compact[:120]}"


class OpenAICompatProvider(BaseProvider):
    def __init__(self, cfg: ProviderConfig) -> None:
        if not cfg.api_url:
            raise ValueError("api_url is required for openai_compat provider")
        if not cfg.api_key:
            raise ValueError("api_key is required for openai_compat provider")
        self.cfg = cfg

    def generate(self, prompt: str) -> str:
        body = {
            "model": self.cfg.model,
            "messages": [
                {"role": "user", "content": prompt},
            ],
            "temperature": self.cfg.temperature,
            "max_tokens": self.cfg.max_tokens,
        }
        data = json.dumps(body).encode("utf-8")
        req = request.Request(
            self.cfg.api_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.cfg.api_key}",
            },
            method="POST",
        )

        with request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            obj = json.loads(raw)

        choices = obj.get("choices", [])
        if not choices:
            return ""
        message = choices[0].get("message", {})
        return str(message.get("content", ""))


def build_provider(cfg: ProviderConfig) -> BaseProvider:
    provider = cfg.provider.strip().lower()
    if provider == "mock":
        return MockProvider(cfg.model)
    if provider == "openai_compat":
        return OpenAICompatProvider(cfg)
    raise ValueError(f"Unsupported provider: {cfg.provider}")
