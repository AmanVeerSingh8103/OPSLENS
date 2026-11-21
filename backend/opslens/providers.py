import asyncio

import httpx

from .config import Settings


class ProviderError(Exception):
    """Safe-to-display provider failure (never contains keys or prompts)."""


class Provider:
    name = "base"

    async def complete_json(self, system: str, user: str, max_tokens: int = 2500) -> str:
        raise NotImplementedError


class _Http(Provider):
    transport = None  # tests inject httpx.MockTransport; production leaves None
    timeout = 60.0
    backoff = 1.5

    async def _post(self, url: str, headers: dict, body: dict) -> dict:
        last = "unknown error"
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=10.0), transport=self.transport) as c:
                    r = await c.post(url, headers=headers, json=body)
                if r.status_code in (429, 500, 502, 503, 529):
                    last = f"HTTP {r.status_code}"
                elif r.status_code >= 400:
                    raise ProviderError(f"{self.name} rejected the request (HTTP {r.status_code}). Check the API key, model name and quota.")
                else:
                    return r.json()
            except httpx.HTTPError as ex:
                last = type(ex).__name__
            await asyncio.sleep(self.backoff * (attempt + 1))
        raise ProviderError(f"{self.name} is unavailable ({last}) after 3 attempts.")


class AnthropicProvider(_Http):
    name = "anthropic"

    def __init__(self, key: str, model: str):
        self._key, self.model = key, model

    async def complete_json(self, system, user, max_tokens=2500):
        d = await self._post("https://api.anthropic.com/v1/messages",
                             {"x-api-key": self._key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                             {"model": self.model, "max_tokens": max_tokens, "system": system, "messages": [{"role": "user", "content": user}]})
        return "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")


class OpenAIProvider(_Http):
    name = "openai"

    def __init__(self, key: str, model: str):
        self._key, self.model = key, model

    async def complete_json(self, system, user, max_tokens=2500):
        d = await self._post("https://api.openai.com/v1/chat/completions", {"Authorization": f"Bearer {self._key}"},
                             {"model": self.model, "max_tokens": max_tokens, "response_format": {"type": "json_object"},
                              "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        try:
            return d["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError):
            raise ProviderError("openai returned an unexpected response shape.") from None


def get_provider(s: Settings) -> Provider | None:
    pref = s.ai_provider
    if pref in (None, "anthropic") and s.anthropic_key:
        return AnthropicProvider(s.anthropic_key, s.anthropic_model)
    if pref in (None, "openai") and s.openai_key:
        return OpenAIProvider(s.openai_key, s.openai_model)
    return None
