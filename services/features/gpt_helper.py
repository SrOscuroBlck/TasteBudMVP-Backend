from __future__ import annotations
import json
import re
from typing import Dict, Any, List, cast
from uuid import uuid4
from config.settings import settings

TASTE_AXES_LIST = ["sweet", "sour", "salty", "bitter", "umami", "fatty", "spicy"]


def _client():
    if not settings.OPENAI_API_KEY:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=settings.OPENAI_API_KEY)
    except Exception:
        return None


def _strip_markdown_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def generate_onboarding_question(target_axes: List[str], allergies: List[str]) -> Dict[str, Any]:
    client = _client()
    if not client:
        return {}

    allergen_note = f"The user is allergic to: {', '.join(allergies)}. Do NOT include these ingredients." if allergies else ""
    axes_csv = ", ".join(target_axes) if target_axes else ", ".join(TASTE_AXES_LIST[:3])

    system_prompt = (
        "You generate food preference questions for a taste profiling system.\n"
        "The ONLY valid taste axes are: sweet, sour, salty, bitter, umami, fatty, spicy.\n"
        "Return ONLY a JSON object (no markdown, no explanation) matching this exact schema:\n"
        "{\n"
        '  "question_id": "<uuid>",\n'
        '  "prompt": "Would you rather have <food A> or <food B>?",\n'
        '  "options": [\n'
        '    {"id": "A", "label": "<food>", "tags": [...], "ingredient_keys": [...], "axis_impacts": {"<axis>": <float -0.5..0.5>, ...}},\n'
        '    {"id": "B", "label": "<food>", "tags": [...], "ingredient_keys": [...], "axis_impacts": {"<axis>": <float -0.5..0.5>, ...}}\n'
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "- axis_impacts keys MUST be from: sweet, sour, salty, bitter, umami, fatty, spicy. No other keys.\n"
        "- Each option gets its OWN axis_impacts reflecting what choosing it reveals about the user.\n"
        "- The two foods should contrast on the target axes so the choice is informative.\n"
        "- Use real, recognizable dishes. Keep labels short (2-4 words).\n"
        "- axis_impacts values range from -0.5 to 0.5. Use 2-4 axes per option.\n"
        f"{allergen_note}"
    )

    user_prompt = f"Generate a question targeting these taste axes: {axes_csv}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=cast(Any, messages),
            temperature=0.7,
            max_tokens=350,
        )
        raw = response.choices[0].message.content or ""
        cleaned = _strip_markdown_fences(raw)
        data = json.loads(cleaned)

        if not all(k in data for k in ("question_id", "prompt", "options")):
            return {}
        if len(data["options"]) != 2:
            return {}

        for option in data["options"]:
            impacts = option.get("axis_impacts", {})
            filtered = {k: v for k, v in impacts.items() if k in TASTE_AXES_LIST}
            option["axis_impacts"] = filtered

        return data
    except Exception:
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


def explain_similarity(original_item: str, similar_item: str, cuisine: list, score: float) -> str:
    client = _client()
    if not client:
        return ""
    
    context = {
        "original": original_item,
        "similar": similar_item,
        "cuisine": cuisine,
        "score": score
    }
    
    sys = "Explain in one concise sentence why these dishes are similar. Focus on flavors, ingredients, or cooking style. Return JSON with 'explanation' field."
    msg = [{"role": "system", "content": sys}, {"role": "user", "content": str(context)}]
    
    try:
        r = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=cast(Any, msg),
            temperature=0.6,
            max_tokens=50
        )
        import json
        content = r.choices[0].message.content or ""
        data = json.loads(content.strip())
        return data.get("explanation", "")
    except Exception:
        return ""
