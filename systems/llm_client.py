"""Moonshot (Kimi) client. OpenAI-compatible wire format.

The key is read from key.txt at call time and never logged, echoed, or written
into any output file. Nothing in this module reaches the regulator API -- the
evaluation harness must stay offline for filings (INV-9); only the LLM endpoint
is contacted.
"""
import os, pathlib, json

_KEY_FILE = pathlib.Path(__file__).resolve().parents[1] / "key.txt"


def api_key() -> str:
    k = os.environ.get("MOONSHOT_API_KEY")
    if k:
        return k.strip()
    return _KEY_FILE.read_text(encoding="utf-8-sig").strip()


def client(base_url: str | None = None):
    from openai import OpenAI
    return OpenAI(api_key=api_key(),
                  base_url=base_url or os.environ.get(
                      "MOONSHOT_BASE_URL", "https://api.moonshot.ai/v1"))


def list_models(base_url: str | None = None):
    return [m.id for m in client(base_url).models.list().data]
