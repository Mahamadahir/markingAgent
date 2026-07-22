import unittest
from types import SimpleNamespace

from marking_agent.config import provider_settings
from marking_agent.providers import (
    AnthropicProvider,
    AzureOpenAIProvider,
    GeminiProvider,
    OpenAIProvider,
    build_provider,
    split_data_url,
)


class FakeModelsClient:
    def __init__(self, ids):
        self.models = SimpleNamespace(list=lambda: [SimpleNamespace(id=model_id) for model_id in ids])


class ListModelsTests(unittest.TestCase):
    def test_openai_lists_sorted_model_ids(self):
        provider = OpenAIProvider("gpt-4o", client=FakeModelsClient(["gpt-4o-mini", "gpt-4o"]))

        self.assertEqual(provider.list_models(), ["gpt-4o", "gpt-4o-mini"])

    def test_azure_reports_no_listable_models(self):
        provider = AzureOpenAIProvider("dep", "https://x.openai.azure.com", "2024-08-01-preview", client=object())

        self.assertEqual(provider.list_models(), [])


class ProviderTests(unittest.TestCase):
    def test_builds_openai_provider_by_default(self):
        provider = build_provider(provider_settings("gpt-4o", provider="openai"))

        self.assertIsInstance(provider, OpenAIProvider)
        self.assertEqual(provider.model, "gpt-4o")

    def test_builds_azure_provider_with_deployment_as_model(self):
        settings = provider_settings(
            "grading-deployment",
            provider="azure",
            azure_endpoint="https://example.openai.azure.com",
            azure_api_version="2024-08-01-preview",
        )
        provider = build_provider(settings)

        self.assertIsInstance(provider, AzureOpenAIProvider)
        self.assertEqual(provider.model, "grading-deployment")

    def test_builds_anthropic_and_gemini_providers(self):
        anthropic = build_provider(provider_settings("claude-opus-4-8", provider="anthropic"))
        gemini = build_provider(provider_settings("gemini-1.5-pro", provider="gemini"))

        self.assertIsInstance(anthropic, AnthropicProvider)
        self.assertIsInstance(gemini, GeminiProvider)

    def test_rejects_unknown_provider(self):
        with self.assertRaises(ValueError):
            build_provider(provider_settings("gpt-4o", provider="mistral"))

    def test_splits_data_url_into_media_type_and_payload(self):
        media_type, encoded = split_data_url("data:image/png;base64,QUJD")

        self.assertEqual(media_type, "image/png")
        self.assertEqual(encoded, "QUJD")


if __name__ == "__main__":
    unittest.main()
