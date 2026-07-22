from .grading import GRADING_RESPONSE_SCHEMA


def build_openai_content(user_text, image_data_urls=None):
    if not image_data_urls:
        return user_text
    content = [{"type": "text", "text": user_text}]
    for image_url in image_data_urls:
        content.append({"type": "image_url", "image_url": {"url": image_url}})
    return content


class OpenAIProvider:
    def __init__(self, model, client=None):
        self.model = model
        self._client = client

    def _ensure_client(self):
        if self._client is None:
            self._client = self._create_client()
        return self._client

    def _create_client(self):
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError(
                "The openai package is not installed. Run: pip install -r requirements.txt"
            ) from error
        return OpenAI()

    def complete_json(self, system_prompt, user_text, image_data_urls=None):
        response = self._ensure_client().chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": build_openai_content(user_text, image_data_urls)},
            ],
            response_format={"type": "json_schema", "json_schema": GRADING_RESPONSE_SCHEMA},
            temperature=0,
        )
        return response.choices[0].message.content


class AzureOpenAIProvider(OpenAIProvider):
    def __init__(self, deployment, endpoint, api_version, client=None):
        super().__init__(model=deployment, client=client)
        self._endpoint = endpoint
        self._api_version = api_version

    def _create_client(self):
        try:
            from openai import AzureOpenAI
        except ImportError as error:
            raise RuntimeError(
                "The openai package is not installed. Run: pip install -r requirements.txt"
            ) from error
        if not self._endpoint:
            raise RuntimeError("Azure provider requires AZURE_OPENAI_ENDPOINT to be set.")
        return AzureOpenAI(azure_endpoint=self._endpoint, api_version=self._api_version)


def build_provider(settings):
    if settings.provider == "openai":
        return OpenAIProvider(settings.model)
    if settings.provider == "azure":
        return AzureOpenAIProvider(settings.model, settings.azure_endpoint, settings.azure_api_version)
    raise ValueError(f"Unknown grading provider: {settings.provider}")
