"""
AI provider layer — the single place every AI call in the app goes through.

An admin chooses the provider on the Settings page (Off / Anthropic / OpenAI /
Local / Vertex AI) and the model; this module reads that choice plus the matching
API key from the .env and talks to the right service. If AI is Off, not fully
configured, or a call fails, generate() returns None so callers fall back to
their plain (no-AI) template — nothing ever breaks because of AI.

Following the rest of the app, API keys live in the .env (never the database):
    Anthropic  -> ANTHROPIC_API_KEY
    OpenAI     -> OPENAI_API_KEY
    Local      -> usually none (optional LOCAL_API_KEY); set the Base URL instead
    Vertex AI  -> VERTEX_ACCESS_TOKEN  (plus Project + Region on the settings page)

OpenAI, Local, and Vertex are all reached through the OpenAI-compatible client
(Vertex AI exposes an OpenAI-compatible endpoint), so they share one light
dependency and we avoid bundling any heavy cloud SDK into the Windows build.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from logging_setup import get_logger  # noqa: E402
import db  # noqa: E402

log = get_logger("AI")

# Sensible default model per provider (used when the settings field is blank).
DEFAULT_MODELS = {
    "anthropic": "claude-haiku-4-5",
    "openai": "gpt-4o-mini",
    "local": "llama3.1",
    "vertex": "google/gemini-2.0-flash-001",
}


def get_ai_settings():
    """
    Read the AI configuration from the settings row.
    Parameters: none.
    Returns: dict {provider, model, base_url, vertex_project, vertex_location}.
    """
    row = db.query_one("SELECT * FROM app_settings WHERE id = 1") or {}
    provider = (row.get("ai_provider") or "off").lower()
    model = row.get("ai_model") or DEFAULT_MODELS.get(provider, "")
    return {
        "provider": provider,
        "model": model,
        "base_url": row.get("ai_base_url") or "",
        "vertex_project": row.get("vertex_project") or "",
        "vertex_location": row.get("vertex_location") or "",
    }


def api_key_for(provider):
    """
    Get the API key/token for a provider from the environment (the .env file).
    Parameters: provider (str).
    Returns: str or None.
    """
    if provider == "anthropic":
        return os.getenv("ANTHROPIC_API_KEY")
    if provider == "openai":
        return os.getenv("OPENAI_API_KEY")
    if provider == "vertex":
        return os.getenv("VERTEX_ACCESS_TOKEN")
    if provider == "local":
        # A local server usually needs no key; send a placeholder if none set.
        return os.getenv("LOCAL_API_KEY") or "not-needed"
    return None


def is_configured(settings):
    """
    Tell whether the chosen provider has everything it needs to be used.
    Parameters: settings (dict from get_ai_settings).
    Returns: bool.
    """
    provider = settings["provider"]
    if provider == "off":
        return False
    if provider == "anthropic":
        return bool(os.getenv("ANTHROPIC_API_KEY"))
    if provider == "openai":
        return bool(os.getenv("OPENAI_API_KEY"))
    if provider == "local":
        return bool(settings["base_url"])
    if provider == "vertex":
        return bool(os.getenv("VERTEX_ACCESS_TOKEN") and settings["base_url"])
    return False


def is_enabled():
    """
    Tell whether AI is on and ready (used to decide template-vs-AI quickly).
    Parameters: none.
    Returns: bool.
    """
    return is_configured(get_ai_settings())


def generate(system_prompt, user_message, max_tokens=500):
    """
    Generate text from the configured provider.
    Returns the model's reply as a string, or None if AI is off / not configured
    / the call failed — callers treat None as "fall back to the template".
    Parameters: system_prompt (str), user_message (str), max_tokens (int).
    Returns: str or None.
    """
    settings = get_ai_settings()
    if not is_configured(settings):
        return None

    provider = settings["provider"]
    try:
        if provider == "anthropic":
            return call_anthropic(settings, system_prompt, user_message, max_tokens)
        # openai, local, and vertex all speak the OpenAI-compatible protocol.
        return call_openai_compatible(settings, provider, system_prompt,
                                      user_message, max_tokens)
    except Exception:
        log.exception("AI call failed (provider=%s) — falling back to template", provider)
        return None


def call_anthropic(settings, system_prompt, user_message, max_tokens):
    """
    Generate using Anthropic's own SDK (keeps prompt caching on the system text).
    Parameters: settings (dict), system_prompt (str), user_message (str), max_tokens (int).
    Returns: str.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=settings["model"],
        max_tokens=max_tokens,
        system=[{
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text


def call_openai_compatible(settings, provider, system_prompt, user_message, max_tokens):
    """
    Generate using the OpenAI-compatible client (OpenAI, a local server, or Vertex).
    The Base URL points at the right place; the key/token comes from the .env.
    Parameters: settings (dict), provider (str), system_prompt (str),
        user_message (str), max_tokens (int).
    Returns: str.
    """
    from openai import OpenAI

    base_url = settings["base_url"] or None   # None = OpenAI's default endpoint
    client = OpenAI(api_key=api_key_for(provider), base_url=base_url)
    response = client.chat.completions.create(
        model=settings["model"],
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    return response.choices[0].message.content


def status():
    """
    Describe the current AI setup for the settings page (no secrets included).
    Parameters: none.
    Returns: dict with the provider/model/urls, whether it's configured, and
        which provider keys are present in the .env.
    """
    settings = get_ai_settings()
    return {
        "provider": settings["provider"],
        "model": settings["model"],
        "baseUrl": settings["base_url"],
        "vertexProject": settings["vertex_project"],
        "vertexLocation": settings["vertex_location"],
        "configured": is_configured(settings),
        "keysPresent": {
            "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
            "openai": bool(os.getenv("OPENAI_API_KEY")),
            "vertex": bool(os.getenv("VERTEX_ACCESS_TOKEN")),
        },
    }


def test_connection():
    """
    Make one tiny call to confirm the chosen provider actually works.
    Parameters: none.
    Returns: dict {ok (bool), message (str)}.
    """
    settings = get_ai_settings()
    if settings["provider"] == "off":
        return {"ok": False, "message": "AI is set to Off (summaries use the built-in template)."}
    if not is_configured(settings):
        return {"ok": False,
                "message": "This provider isn't fully configured — check its API key in the .env and any required URL/region."}

    reply = generate("You are a connection test.",
                     "Reply with the single word: OK", max_tokens=20)
    if reply and reply.strip():
        return {"ok": True, "message": "Connected. The model replied: " + reply.strip()[:80]}
    return {"ok": False,
            "message": "No reply from the model. Check the model name, key/token, and URL."}
