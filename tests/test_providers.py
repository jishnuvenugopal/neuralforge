"""Settings store and both provider wires, with fake SDK clients (no network)."""

import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace as NS
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import llm  # noqa: E402
import settings  # noqa: E402
from prompts import TOOL_DECLARATIONS  # noqa: E402


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = os.path.join(self.tmp.name, "settings.json")
        self.patches = [
            mock.patch.object(settings, "SETTINGS_DIR", settings.Path(self.tmp.name)),
            mock.patch.object(settings, "SETTINGS_PATH", settings.Path(path)),
            mock.patch.dict(os.environ, {}, clear=False),
        ]
        for p in self.patches:
            p.start()
        os.environ.pop("ZYT_FOUNDRY_API_KEY", None)
        os.environ.pop("ZYT_FOUNDRY_BASE_URL", None)
        os.environ.pop("ZYT_FOUNDRY_MODEL", None)
        self.path = path

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_default_is_zyt_foundry_gpt_6_astra(self):
        config = settings.active_config()
        self.assertEqual((config.provider, config.kind), ("zyt_foundry", "openai"))
        self.assertEqual(config.base_url, "https://foundry.zyt.app/v1")
        self.assertEqual(config.model, "gpt-6-astra")
        view = settings.public_view()
        self.assertFalse(view["configured"])
        self.assertIn("gpt-6.1-sol", view["providers"]["zyt_foundry"]["models"])
        self.assertEqual(len(view["providers"]["zyt_foundry"]["models"]), 8)

    def test_environment_key_and_url(self):
        with mock.patch.dict(os.environ, {"ZYT_FOUNDRY_API_KEY": "zyt-test-0000-1234", "ZYT_FOUNDRY_BASE_URL": "https://x.test/v1"}):
            config = settings.active_config()
            view = settings.public_view()
        self.assertEqual((config.api_key, config.base_url), ("zyt-test-0000-1234", "https://x.test/v1"))
        self.assertEqual(view["providers"]["zyt_foundry"]["key_source"], "environment")

    def test_keys_are_saved_privately_and_never_returned(self):
        view = settings.update({"providers": {"zyt_foundry": {"api_key": "secret-key-abcd"}}})
        self.assertTrue(view["configured"])
        self.assertNotIn("secret-key-abcd", json.dumps(view))
        self.assertEqual(view["providers"]["zyt_foundry"]["key_hint"], "…abcd")
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)

    def test_foundry_model_is_selectable_but_its_url_is_fixed(self):
        settings.update({"providers": {"zyt_foundry": {"model": "gpt-6.1-sol", "base_url": "https://evil.test"}}})
        config = settings.active_config()
        self.assertEqual((config.model, config.base_url), ("gpt-6.1-sol", "https://foundry.zyt.app/v1"))
        with mock.patch.dict(os.environ, {"ZYT_FOUNDRY_MODEL": "gpt-5.5"}):
            settings.update({"providers": {"zyt_foundry": {"model": ""}}})
            self.assertEqual(settings.active_config().model, "gpt-5.5")

    def test_fetched_model_lists_are_remembered(self):
        view = settings.save_models("openai_compatible", ["b-model", "a-model", "a-model"])
        entry = view["providers"]["openai_compatible"]
        self.assertEqual(entry["models"], ["a-model", "b-model"])
        self.assertTrue(entry["models_fetched"])

    def test_switch_to_anthropic_compatible(self):
        settings.update({
            "active_provider": "anthropic_compatible",
            "providers": {"anthropic_compatible": {"api_key": "k-12345678", "base_url": "https://gw.test", "model": "claude-x"}},
        })
        config = settings.active_config()
        self.assertEqual((config.kind, config.base_url, config.model), ("anthropic", "https://gw.test", "claude-x"))

    def test_empty_key_keeps_the_old_one_and_clear_removes_it(self):
        settings.update({"providers": {"zyt_foundry": {"api_key": "first-key-1111"}}})
        settings.update({"providers": {"zyt_foundry": {"api_key": ""}}})
        self.assertEqual(settings.active_config().api_key, "first-key-1111")
        settings.update({"providers": {"zyt_foundry": {"clear_key": True}}})
        self.assertEqual(settings.active_config().api_key, "")

    def test_bad_input_is_rejected(self):
        with self.assertRaises(ValueError):
            settings.update({"active_provider": "nope"})
        with self.assertRaises(ValueError):
            settings.update({"providers": {"openai_compatible": {"base_url": "ftp://x"}}})


def config(kind="openai", base_url="https://foundry.zyt.app/v1"):
    return settings.ProviderConfig("p", "Test", kind, base_url, "m", "key")


class OpenAIWireTest(unittest.TestCase):
    def test_tool_call_round_trip(self):
        conversation = llm.open_conversation(config(), "SYS", TOOL_DECLARATIONS)
        reply = NS(choices=[NS(message=NS(
            content="Writing RTL.",
            tool_calls=[NS(id="call_1", function=NS(name="synthesize_verilog", arguments='{"module_name": "m", "verilog_code": "x"}'))],
        ))])
        conversation.client = NS(chat=NS(completions=NS(create=mock.Mock(return_value=reply))))
        conversation.add_user_text("hi")
        turn = conversation.next_turn()

        sent = conversation.client.chat.completions.create.call_args.kwargs
        self.assertEqual(sent["model"], "m")
        self.assertNotIn("temperature", sent)
        self.assertEqual(sent["tools"][0]["type"], "function")
        self.assertEqual(turn.texts, ["Writing RTL."])
        self.assertEqual((turn.tool_calls[0].name, turn.tool_calls[0].args["module_name"]), ("synthesize_verilog", "m"))

        conversation.add_tool_results([(turn.tool_calls[0], {"status": "success"})])
        roles = [m["role"] for m in conversation.messages]
        self.assertEqual(roles, ["system", "user", "assistant", "tool"])
        self.assertEqual(conversation.messages[2]["tool_calls"][0]["id"], "call_1")
        self.assertEqual(conversation.messages[3]["tool_call_id"], "call_1")

    def test_invalid_json_arguments_are_flagged(self):
        conversation = llm.open_conversation(config(), "SYS", TOOL_DECLARATIONS)
        reply = NS(choices=[NS(message=NS(content=None, tool_calls=[NS(id="c", function=NS(name="simulate_verilog", arguments="{oops"))]))])
        conversation.client = NS(chat=NS(completions=NS(create=mock.Mock(return_value=reply))))
        turn = conversation.next_turn()
        self.assertIn("not valid JSON", turn.tool_calls[0].error)

    def test_missing_key_is_a_clear_error(self):
        with self.assertRaisesRegex(llm.LLMError, "No API key"):
            llm.open_conversation(settings.ProviderConfig("p", "ZYT Foundry", "openai", "https://x", "m", ""), "S", [])


class FakeStream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.message


class AnthropicWireTest(unittest.TestCase):
    def make(self, base_url, message):
        conversation = llm.open_conversation(config("anthropic", base_url), "SYS", TOOL_DECLARATIONS)
        stream = mock.Mock(return_value=FakeStream(message))
        beta_stream = mock.Mock(return_value=FakeStream(message))
        conversation.client = NS(messages=NS(stream=stream), beta=NS(messages=NS(stream=beta_stream)))
        return conversation, stream, beta_stream

    def message(self, stop="tool_use"):
        return NS(stop_reason=stop, content=[
            NS(type="text", text="Synthesizing."),
            NS(type="tool_use", id="toolu_1", name="synthesize_verilog", input={"module_name": "m", "verilog_code": "x"}),
        ])

    def test_tool_use_round_trip_on_a_compatible_gateway(self):
        returned = self.message()
        conversation, stream, beta_stream = self.make("https://gw.test", returned)
        conversation.add_user_text("hi")
        turn = conversation.next_turn()
        sent = stream.call_args.kwargs
        beta_stream.assert_not_called()
        self.assertEqual(sent["system"], "SYS")
        self.assertIn("input_schema", sent["tools"][0])
        self.assertNotIn("temperature", sent)
        self.assertEqual(turn.tool_calls[0].id, "toolu_1")

        conversation.add_tool_results([(turn.tool_calls[0], {"status": "success"})])
        last = conversation.messages[-1]
        self.assertEqual(last["role"], "user")
        self.assertEqual(last["content"][0]["type"], "tool_result")
        self.assertEqual(last["content"][0]["tool_use_id"], "toolu_1")
        # The assistant turn is stored exactly as returned (append-only history).
        self.assertIs(conversation.messages[1]["content"], returned.content)

    def test_official_api_uses_server_side_fallbacks(self):
        conversation, stream, beta_stream = self.make("https://api.anthropic.com", self.message())
        conversation.add_user_text("hi")
        conversation.next_turn()
        stream.assert_not_called()
        sent = beta_stream.call_args.kwargs
        self.assertEqual(sent["fallbacks"], "default")
        self.assertIn("server-side-fallback-2026-07-01", sent["betas"])

    def test_refusal_is_reported(self):
        conversation, _, _ = self.make("https://gw.test", self.message(stop="refusal"))
        conversation.add_user_text("hi")
        with self.assertRaisesRegex(llm.LLMError, "declined"):
            conversation.next_turn()


if __name__ == "__main__":
    unittest.main()
