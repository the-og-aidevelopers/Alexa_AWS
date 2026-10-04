"""Turn a tool result into a spoken sentence. Bedrock is optional and off by default."""

from __future__ import annotations

import json
import os
from typing import Any


def maybe_rephrase(result: dict[str, Any], fallback: str) -> tuple[str, bool]:
    """Return (speech, used_bedrock). A failed model call keeps the template."""
    if os.environ.get("SPEAK_WITH_BEDROCK") != "1":
        return fallback, False
    facts = {key: value for key, value in result.items() if key != "speech"}
    prompt = (
        "Rewrite these facts as one or two short spoken sentences for an older adult. "
        "Do not add a medicine, a time, a person, or a reason that is not in the facts. "
        "Do not give medical advice. Facts: "
        + json.dumps(facts, default=str)
    )
    try:
        import boto3

        client = boto3.client(
            "bedrock-runtime",
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
        )
        response = client.converse(
            modelId=os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-micro-v1:0"),
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 120, "temperature": 0},
        )
        text = response["output"]["message"]["content"][0]["text"].strip()
    except Exception:
        return fallback, False
    if not text:
        return fallback, False
    return text, True
