"""
Provider-neutral agent conversation over two wire protocols:

- OpenAI-compatible chat completions with function tools (ZYT Foundry, OpenAI, ...)
- Anthropic-compatible Messages API with tool use

Both keep the history append-only: every model turn is stored as returned and
tool results are appended after it.
"""

import json
from dataclasses import dataclass, field
from urllib.parse import urlparse

import anthropic
import openai

from settings import ProviderConfig

REQUEST_TIMEOUT_SEC = 600
ANTHROPIC_MAX_TOKENS = 32000


class LLMError(Exception):
    """A provider failure, with a message fit to show in the UI."""


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict
    error: str = ""         # set when the arguments were not valid JSON


@dataclass
class Turn:
    texts: list = field(default_factory=list)
    tool_calls: list = field(default_factory=list)


def _friendly(config: ProviderConfig, error: Exception) -> LLMError:
    where = f"{config.label} ({config.base_url}, model {config.model})"
    status = getattr(error, "status_code", None)
    if isinstance(error, (openai.AuthenticationError, anthropic.AuthenticationError)):
        return LLMError(f"{where} rejected the API key. Check it in Settings.")
    if isinstance(error, (openai.PermissionDeniedError, anthropic.PermissionDeniedError)):
        return LLMError(f"{where} denied access to this model with this key.")
    if isinstance(error, (openai.NotFoundError, anthropic.NotFoundError)):
        return LLMError(f"{where}: model or endpoint not found. Check the base URL and model name.")
    if isinstance(error, (openai.RateLimitError, anthropic.RateLimitError)):
        return LLMError(f"{where} is rate limiting requests. Wait a moment and try again.")
    if isinstance(error, (openai.APIConnectionError, anthropic.APIConnectionError)):
        return LLMError(f"Could not reach {config.base_url}. Check the URL and your network.")
    if isinstance(error, (openai.APIStatusError, anthropic.APIStatusError)):
        detail = getattr(error, "message", "") or str(error)
        return LLMError(f"{where} returned HTTP {status}: {detail[:300]}")
    return LLMError(f"{where}: {error}")


def _parse_args(raw) -> tuple[dict, str]:
    if isinstance(raw, dict):
        return raw, ""
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError as e:
        return {}, f"tool arguments were not valid JSON ({e})"
    return (value, "") if isinstance(value, dict) else ({}, "tool arguments must be a JSON object")


class Conversation:
    def __init__(self, config: ProviderConfig, system: str, tools: list):
        self.config = config
        self.system = system
        self.tools = tools

    def add_user_text(self, text: str):
        raise NotImplementedError

    def add_tool_results(self, results: list):
        """results: [(ToolCall, dict)] for every call of the last turn, in order."""
        raise NotImplementedError

    def next_turn(self) -> Turn:
        raise NotImplementedError


class OpenAIConversation(Conversation):
    def __init__(self, config, system, tools):
        super().__init__(config, system, tools)
        self.client = openai.OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=REQUEST_TIMEOUT_SEC,
            max_retries=2,
        )
        self.messages = [{"role": "system", "content": system}]
        self.tool_specs = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                },
            }
            for t in tools
        ]

    def add_user_text(self, text):
        self.messages.append({"role": "user", "content": text})

    def add_tool_results(self, results):
        for call, result in results:
            self.messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result),
            })

    def next_turn(self):
        try:
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=self.messages,
                tools=self.tool_specs,
                tool_choice="auto",
            )
        except openai.OpenAIError as e:
            raise _friendly(self.config, e) from e

        if not response.choices:
            raise LLMError(f"{self.config.label} returned no choices.")
        message = response.choices[0].message

        assistant = {"role": "assistant", "content": message.content or ""}
        turn = Turn(texts=[message.content] if message.content else [])
        if message.tool_calls:
            assistant["tool_calls"] = []
            for call in message.tool_calls:
                assistant["tool_calls"].append({
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.function.name, "arguments": call.function.arguments},
                })
                args, error = _parse_args(call.function.arguments)
                turn.tool_calls.append(ToolCall(call.id, call.function.name, args, error))
        self.messages.append(assistant)
        return turn


class AnthropicConversation(Conversation):
    FALLBACK_BETA = "server-side-fallback-2026-07-01"

    def __init__(self, config, system, tools):
        super().__init__(config, system, tools)
        self.client = anthropic.Anthropic(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=REQUEST_TIMEOUT_SEC,
            max_retries=2,
        )
        self.messages = []
        self.tool_specs = [
            {"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
            for t in tools
        ]
        # Server-side refusal fallbacks exist only on Anthropic's own API, not on compatible gateways.
        self.official = urlparse(config.base_url).netloc == "api.anthropic.com"

    def add_user_text(self, text):
        self.messages.append({"role": "user", "content": text})

    def add_tool_results(self, results):
        self.messages.append({
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": json.dumps(result),
                    "is_error": bool(call.error),
                }
                for call, result in results
            ],
        })

    def next_turn(self):
        params = {
            "model": self.config.model,
            "max_tokens": ANTHROPIC_MAX_TOKENS,
            "system": self.system,
            "tools": self.tool_specs,
            "messages": self.messages,
        }
        try:
            if self.official:
                with self.client.beta.messages.stream(
                    **params, betas=[self.FALLBACK_BETA], fallbacks="default"
                ) as stream:
                    message = stream.get_final_message()
            else:
                with self.client.messages.stream(**params) as stream:
                    message = stream.get_final_message()
        except anthropic.AnthropicError as e:
            raise _friendly(self.config, e) from e

        if message.stop_reason == "refusal":
            raise LLMError(f"{self.config.label} declined this request (refusal).")

        self.messages.append({"role": "assistant", "content": message.content})
        turn = Turn()
        for block in message.content:
            if block.type == "text" and block.text:
                turn.texts.append(block.text)
            elif block.type == "tool_use":
                args, error = _parse_args(block.input)
                turn.tool_calls.append(ToolCall(block.id, block.name, args, error))
        return turn


def open_conversation(config: ProviderConfig, system: str, tools: list) -> Conversation:
    if not config.api_key:
        raise LLMError(f"No API key set for {config.label}. Open Settings to add one.")
    if not config.model:
        raise LLMError(f"No model set for {config.label}. Open Settings to choose one.")
    if config.kind == "anthropic":
        return AnthropicConversation(config, system, tools)
    return OpenAIConversation(config, system, tools)


def check_connection(config: ProviderConfig) -> str:
    """Send one tiny request. Returns the model's reply; raises LLMError on failure."""
    conversation = open_conversation(config, "You are a connectivity check.", [])
    conversation.add_user_text("Reply with the single word OK.")
    if isinstance(conversation, OpenAIConversation):
        try:
            response = conversation.client.chat.completions.create(
                model=config.model, messages=conversation.messages
            )
        except openai.OpenAIError as e:
            raise _friendly(config, e) from e
        return (response.choices[0].message.content or "").strip() if response.choices else ""
    try:
        message = conversation.client.messages.create(
            model=config.model, max_tokens=1024, messages=conversation.messages
        )
    except anthropic.AnthropicError as e:
        raise _friendly(config, e) from e
    return " ".join(b.text for b in message.content if b.type == "text").strip()


def list_models(config: ProviderConfig) -> list[str]:
    """Model ids from the provider's /models endpoint. Raises LLMError on failure."""
    if not config.api_key:
        raise LLMError(f"Save an API key for {config.label} first, then load its models.")
    try:
        if config.kind == "anthropic":
            client = anthropic.Anthropic(api_key=config.api_key, base_url=config.base_url, timeout=30)
            return [m.id for m in client.models.list()]
        client = openai.OpenAI(api_key=config.api_key, base_url=config.base_url, timeout=30)
        return [m.id for m in client.models.list()]
    except (openai.OpenAIError, anthropic.AnthropicError) as e:
        raise _friendly(config, e) from e
