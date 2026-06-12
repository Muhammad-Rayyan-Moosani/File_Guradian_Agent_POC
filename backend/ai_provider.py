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
import time
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from logging_setup import get_logger  # noqa: E402
import db  # noqa: E402

log = get_logger("AI")

# --- safety rate cap --------------------------------------------------------
# Never make more than this many AI calls per rolling 60 seconds. A burst of
# failing files (or a misconfiguration / loop) therefore can't drain an account
# — extra calls quietly fall back to the plain template. This protects every
# provider, and especially the Claude CLI option, which spends your signed-in
# subscription's 5-hour quota. Override with FG_AI_MAX_CALLS_PER_MIN (0 = off).
_recent_calls = []
_calls_lock = threading.Lock()


def max_calls_per_min():
    """
    Read the per-minute AI call cap from the environment (default 20).
    Parameters: none.
    Returns: int (0 or less means the cap is disabled).
    """
    raw = os.getenv("FG_AI_MAX_CALLS_PER_MIN")
    if raw is None or raw.strip() == "":
        return 20
    try:
        return int(raw)
    except ValueError:
        return 20


def under_rate_cap():
    """
    Record one AI call and report whether we are still within the per-minute cap.
    Parameters: none.
    Returns: bool — True if the call may proceed, False if the cap is hit.
    """
    cap = max_calls_per_min()
    if cap <= 0:
        return True

    now = time.time()
    cutoff = now - 60
    with _calls_lock:
        while _recent_calls and _recent_calls[0] < cutoff:
            _recent_calls.pop(0)
        if len(_recent_calls) >= cap:
            return False
        _recent_calls.append(now)
        return True

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
        "cli_path": row.get("ai_cli_path") or "",
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
    if provider == "claudecli":
        # No API key — it uses the signed-in `claude` CLI. We can't cheaply
        # verify the login here, so treat "selected" as configured; the Test
        # button (and the first real call) will surface any problem.
        return True
    return False


def is_enabled():
    """
    Tell whether AI is on and ready (used to decide template-vs-AI quickly).
    Parameters: none.
    Returns: bool.
    """
    return is_configured(get_ai_settings())


def generate(system_prompt, user_message, max_tokens=500, raise_errors=False):
    """
    Generate text from the configured provider.
    Returns the model's reply as a string, or None if AI is off / not configured
    / the call failed — callers treat None as "fall back to the template".
    Parameters: system_prompt (str), user_message (str), max_tokens (int),
        raise_errors (bool — if True, re-raise the real error instead of
        returning None; used by the Test button so the user sees what went wrong).
    Returns: str or None.
    """
    settings = get_ai_settings()
    if not is_configured(settings):
        return None

    # Safety cap: refuse to exceed the per-minute call limit so a flood of
    # files can never drain the account; fall back to the template instead.
    if not under_rate_cap():
        log.warning("AI rate cap reached (%d/min) — using the template for this "
                    "one to protect the account.", max_calls_per_min())
        if raise_errors:
            raise RuntimeError(
                "AI safety cap reached (FG_AI_MAX_CALLS_PER_MIN per minute). "
                "Wait a moment and try again.")
        return None

    provider = settings["provider"]
    try:
        if provider == "anthropic":
            return call_anthropic(settings, system_prompt, user_message, max_tokens)
        if provider == "claudecli":
            return call_claude_cli(settings, system_prompt, user_message)
        # openai, local, and vertex all speak the OpenAI-compatible protocol.
        return call_openai_compatible(settings, provider, system_prompt,
                                      user_message, max_tokens)
    except Exception:
        log.exception("AI call failed (provider=%s) — falling back to template", provider)
        if raise_errors:
            raise
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


def call_claude_cli(settings, system_prompt, user_message):
    """
    Generate by running the signed-in Claude CLI (no API key).
    Runs `claude -p <prompt> --system-prompt <system>` and returns its output.
    The machine must have the CLI installed, on the PATH, and logged in.
    Parameters: settings (dict), system_prompt (str), user_message (str).
    Returns: str.
    """
    import shutil
    import subprocess

    command = settings["cli_path"] or "claude"
    # Resolve the real executable so we find it whatever the extension is
    # (e.g. claude.cmd on Windows) and give a clear error if it isn't there.
    resolved = shutil.which(command)
    if not resolved:
        raise RuntimeError(
            "The '" + command + "' command was not found on this machine. Install "
            "the Claude CLI and make sure it is on the PATH of the computer running "
            "the app.")

    arguments = [resolved, "-p", user_message, "--system-prompt", system_prompt]
    if settings["model"]:
        arguments += ["--model", settings["model"]]

    # Hard timeout so a hung CLI (e.g. waiting for a prompt) can't tie up a
    # worker — on timeout this raises and the run falls back to the template.
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip() or "the CLI exited with an error"
        raise RuntimeError("Claude CLI error: " + detail[:300])

    output = (result.stdout or "").strip()
    if not output:
        raise RuntimeError(
            "The Claude CLI ran but returned nothing. Make sure it is logged in "
            "(run `claude` once on this machine to sign in).")
    return result.stdout


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
        "cliPath": settings["cli_path"],
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

    try:
        reply = generate("You are a connection test.",
                         "Reply with the single word: OK", max_tokens=20,
                         raise_errors=True)
    except Exception as error:
        return {"ok": False, "message": str(error)[:300]}

    if reply and reply.strip():
        return {"ok": True, "message": "Connected. The model replied: " + reply.strip()[:80]}
    return {"ok": False,
            "message": "No reply from the model. Check the model name, key/token, and URL."}
