import base64
import json


def split_data_url(data_url):
    header, encoded = data_url.split(",", 1)
    media_type = header[len("data:"):].split(";", 1)[0] or "image/png"
    return media_type, encoded


def build_openai_content(user_text, image_data_urls=None):
    if not image_data_urls:
        return user_text
    content = [{"type": "text", "text": user_text}]
    for image_url in image_data_urls:
        content.append({"type": "image_url", "image_url": {"url": image_url}})
    return content


def missing_package_error():
    return RuntimeError(
        "A required package is not installed. Run: pip install -r requirements.txt"
    )


class OpenAIProvider:
    def __init__(self, model, api_key="", client=None):
        self.model = model
        self.api_key = api_key
        self._client = client

    def _ensure_client(self):
        if self._client is None:
            self._client = self._create_client()
        return self._client

    def _create_client(self):
        try:
            from openai import OpenAI
        except ImportError as error:
            raise missing_package_error() from error
        return OpenAI(api_key=self.api_key) if self.api_key else OpenAI()

    def complete_json(self, system_prompt, user_text, schema, image_data_urls=None):
        response = self._ensure_client().chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": build_openai_content(user_text, image_data_urls)},
            ],
            response_format={"type": "json_schema", "json_schema": schema},
            temperature=0,
        )
        return response.choices[0].message.content

    def list_models(self):
        return sorted(model.id for model in self._ensure_client().models.list())


class AzureOpenAIProvider(OpenAIProvider):
    def __init__(self, deployment, endpoint, api_version, api_key="", client=None):
        super().__init__(model=deployment, api_key=api_key, client=client)
        self._endpoint = endpoint
        self._api_version = api_version

    def _create_client(self):
        try:
            from openai import AzureOpenAI
        except ImportError as error:
            raise missing_package_error() from error
        if not self._endpoint:
            raise RuntimeError("Azure provider requires AZURE_OPENAI_ENDPOINT to be set.")
        arguments = {"azure_endpoint": self._endpoint, "api_version": self._api_version}
        if self.api_key:
            arguments["api_key"] = self.api_key
        return AzureOpenAI(**arguments)

    def list_models(self):
        return []


class AnthropicProvider:
    def __init__(self, model, api_key="", client=None):
        self.model = model
        self.api_key = api_key
        self._client = client

    def _ensure_client(self):
        if self._client is None:
            try:
                from anthropic import Anthropic
            except ImportError as error:
                raise missing_package_error() from error
            self._client = Anthropic(api_key=self.api_key) if self.api_key else Anthropic()
        return self._client

    def complete_json(self, system_prompt, user_text, schema, image_data_urls=None):
        response = self._ensure_client().messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_prompt,
            output_config={"format": {"type": "json_schema", "schema": schema["schema"]}},
            messages=[{"role": "user", "content": self._build_content(user_text, image_data_urls)}],
        )
        return next(block.text for block in response.content if block.type == "text")

    def list_models(self):
        return sorted(model.id for model in self._ensure_client().models.list())

    @staticmethod
    def _build_content(user_text, image_data_urls):
        content = [{"type": "text", "text": user_text}]
        for image_url in image_data_urls or []:
            media_type, encoded = split_data_url(image_url)
            content.append(
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": encoded},
                }
            )
        return content


class GeminiProvider:
    def __init__(self, model, api_key="", client=None):
        self.model = model
        self.api_key = api_key
        self._model = client

    def _ensure_genai(self):
        try:
            import google.generativeai as genai
        except ImportError as error:
            raise missing_package_error() from error
        if self.api_key:
            genai.configure(api_key=self.api_key)
        return genai

    def _ensure_model(self):
        if self._model is None:
            self._model = self._ensure_genai().GenerativeModel(self.model)
        return self._model

    def list_models(self):
        genai = self._ensure_genai()
        return sorted(
            model.name.removeprefix("models/")
            for model in genai.list_models()
            if "generateContent" in getattr(model, "supported_generation_methods", [])
        )

    def complete_json(self, system_prompt, user_text, schema, image_data_urls=None):
        schema_instruction = (
            f"{system_prompt}\n\nReturn only JSON matching this schema:\n"
            f"{json.dumps(schema['schema'])}"
        )
        parts = [schema_instruction, user_text]
        for image_url in image_data_urls or []:
            media_type, encoded = split_data_url(image_url)
            parts.append({"mime_type": media_type, "data": base64.b64decode(encoded)})

        response = self._ensure_model().generate_content(
            parts,
            generation_config={"response_mime_type": "application/json", "temperature": 0},
        )
        return response.text


def build_provider(settings):
    if settings.provider == "openai":
        return OpenAIProvider(settings.model, api_key=settings.api_key)
    if settings.provider == "azure":
        return AzureOpenAIProvider(
            settings.model, settings.azure_endpoint, settings.azure_api_version, api_key=settings.api_key
        )
    if settings.provider == "anthropic":
        return AnthropicProvider(settings.model, api_key=settings.api_key)
    if settings.provider == "gemini":
        return GeminiProvider(settings.model, api_key=settings.api_key)
    raise ValueError(f"Unknown grading provider: {settings.provider}")
