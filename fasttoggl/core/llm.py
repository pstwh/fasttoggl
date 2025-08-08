import base64
from typing import Optional

from fasttoggl.chains.chain import get_chain


def process_audio_with_llm(
    context: str,
    audio_file: Optional[str] = None,
    model_name: Optional[str] = "gemini-2.5-flash",
) -> dict:
    if audio_file:
        with open(audio_file, "rb") as f:
            audio_data = f.read()

        encoded_audio = base64.b64encode(audio_data).decode("utf-8")

        chain = get_chain(context, encoded_audio, "audio/wav", model=model_name)
    else:
        chain = get_chain(context, model=model_name)

    result = chain.invoke({})

    return result
