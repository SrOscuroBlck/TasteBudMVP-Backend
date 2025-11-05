from __future__ import annotations
from typing import Dict, Any, cast
from config.settings import settings


def _client():
    if not settings.OPENAI_API_KEY:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=settings.OPENAI_API_KEY)
    except Exception:
        return None


def generate_onboarding_question(context: Dict[str, Any]) -> Dict[str, Any]:
    client = _client()
    if not client:
        return {}
    sys = (
        "Return a single JSON object only matching the schema with fields: question_id (uuid), prompt, "
        "options (two with id A and B), and axis_hints. Culturally neutral foods. Avoid allergens in user filters."
    )
    msg = [{"role": "system", "content": sys}, {"role": "user", "content": str(context)}]
    try:
        # The OpenAI client expects a specific message param type; cast to Any to satisfy type checkers
        r = client.chat.completions.create(model=settings.OPENAI_MODEL, messages=cast(Any, msg), temperature=0.5, max_tokens=250)
        content = r.choices[0].message.content or ""
        txt = content.strip()
        import json
        data = json.loads(txt)
        # minimal validation
        if all(k in data for k in ("question_id", "prompt", "options")):
            return data
    except Exception:
        pass
    return {}


def generate_rationale(context: Dict[str, Any]) -> str:
    client = _client()
    if not client:
        return ""
    sys = "Return JSON like {\"reason\": \"...\"} based on provided matched axes and key ingredients."
    msg = [{"role": "system", "content": sys}, {"role": "user", "content": str(context)}]
    try:
        # cast messages to Any to avoid strict SDK typing issues in editor
        r = client.chat.completions.create(model=settings.OPENAI_MODEL, messages=cast(Any, msg), temperature=0.6, max_tokens=60)
        import json
        content = r.choices[0].message.content or ""
        txt = content.strip()
        data = json.loads(txt)
        return data.get("reason", "")
    except Exception:
        return ""


def infer_ingredients(context: Dict[str, Any]) -> Dict[str, Any]:
    client = _client()
    if not client:
        return {}
    sys = (
        "Return JSON with fields: candidates (list of {ingredient, confidence}), tags, axis_hints. "
        "Never include allergens or dietary flags."
    )
    msg = [{"role": "system", "content": sys}, {"role": "user", "content": str(context)}]
    try:
        r = client.chat.completions.create(model=settings.OPENAI_MODEL, messages=cast(Any, msg), temperature=0.5, max_tokens=200)
        import json
        content = r.choices[0].message.content or ""
        data = json.loads(content.strip())
        if "candidates" in data:
            return data
    except Exception:
        pass
    return {}
