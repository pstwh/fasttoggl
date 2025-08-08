from typing import Optional

from langchain_google_genai import ChatGoogleGenerativeAI

from fasttoggl.core.credentials import CredentialsManager


def get_llm(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
):
    if provider is None or model is None or api_key is None:
        cm = CredentialsManager()
        saved_provider, saved_model, saved_key = cm.load_llm_config()
        provider = provider or saved_provider or "google"
        model = model or saved_model or "gemini-2.5-flash"
        api_key = api_key or saved_key
    if provider == "google":
        return ChatGoogleGenerativeAI(
            model=model or "gemini-2.5-flash",
            google_api_key=api_key,
            temperature=0,
            response_mime_type="application/json",
        )
    raise ValueError("Unsupported LLM provider")
