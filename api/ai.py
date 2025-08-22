
import os, json, hashlib
from typing import Any, Dict, Optional

from openai import OpenAI, APIConnectionError, RateLimitError, BadRequestError, APITimeoutError
import redis  

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_PROJECT = os.getenv("OPENAI_PROJECT")  
OPENAI_ORG_ID = os.getenv("OPENAI_ORG_ID")    

_redis: Optional[redis.Redis] = None
try:
    _redis = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), socket_connect_timeout=0.2)
    _redis.ping()
except Exception:
    _redis = None

_client: Optional[OpenAI] = None
if OPENAI_API_KEY:
    _client = OpenAI(
        api_key=OPENAI_API_KEY,
        project=OPENAI_PROJECT,
        organization=OPENAI_ORG_ID,
    )

def _cache_key(description: str, amount: float) -> str:
    h = hashlib.sha1(f"{description}|{amount}".encode("utf-8")).hexdigest()
    return f"cat_v1:{h}"

def _get_cache(description: str, amount: float) -> Optional[Dict[str, Any]]:
    if not _redis:
        return None
    raw = _redis.get(_cache_key(description, amount))
    return json.loads(raw) if raw else None

def _set_cache(description: str, amount: float, value: Dict[str, Any]) -> None:
    if not _redis:
        return
    _redis.setex(_cache_key(description, amount), 60 * 60 * 12, json.dumps(value))  # 12h

SCHEMA = {
    "name": "CategorizationResult",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "merchant": {"type": ["string", "null"]},
            "category": {"type": ["string", "null"]},
            "subcategory": {"type": ["string", "null"]},
            "is_subscription": {"type": "boolean"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "notes": {"type": ["string", "null"]},
            "spending_class": {
                "type": ["string", "null"],
                "enum": ["need", "want", "savings", None],
            },
        },
        "required": ["merchant", "category", "is_subscription", "confidence", "notes"],
    },
}

SYSTEM = """You categorize personal finance transactions.
Return strictly the specified JSON schema. No extra keys, no prose.
- Infer merchant from the description when obvious, else null.
- Choose practical, human-friendly categories (e.g., Groceries, Dining, Transport, Utilities, Rent, Income, Entertainment, Health, Shopping, Travel, Fees, Transfers).
- Put brand/store-specific detail in subcategory if useful (e.g., "Supermarket" or "Coffee").
- is_subscription = true for recurring services/memberships or obvious monthly charges.
- confidence reflects certainty from 0 to 1.
- notes is optional brief reasoning if helpful.
- Classify spending_class as one of: "need", "want", or "savings".
Examples:
- Groceries, utilities, rent, fuel -> "need"
- Dining out, entertainment, shopping -> "want"
- Transfers to savings, investments, overpayments -> "savings"
"""

USER_TMPL = """Transaction:
- Description: {description}
- Amount: {amount}
- Currency: EUR

Respond using the JSON schema only.
"""

def _no_key_fallback() -> Dict[str, Any]:
    return {
        "merchant": None,
        "category": "Groceries",
        "subcategory": None,
        "is_subscription": False,
        "confidence": 0.5,
        "notes": "OPENAI_API_KEY missing; returned fallback.",
    }

def _error_payload(msg: str) -> Dict[str, Any]:
    return {
        "merchant": None,
        "category": None,
        "subcategory": None,
        "is_subscription": False,
        "confidence": 0.0,
        "notes": msg,
    }

def _fallback_chat_tools(description: str, amount: float) -> Dict[str, Any]:
    """
    Fallback for SDKs that don't support Responses+response_format.
    Uses Chat Completions with function calling (tools) to force strict JSON.
    """
    if not _client:
        return _no_key_fallback()

    tool_schema = {
        "type": "function",
        "function": {
            "name": "categorize",
            "description": "Return structured categorization for a finance transaction.",
            "parameters": SCHEMA["schema"],
        },
    }

    try:
        resp = _client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": USER_TMPL.format(description=description, amount=amount)},
            ],
            tools=[tool_schema],
            tool_choice={"type": "function", "function": {"name": "categorize"}},
        )
    except (APIConnectionError, APITimeoutError):
        return _error_payload("OpenAI connection/timeout error.")
    except RateLimitError:
        return _error_payload("Rate limited by OpenAI — check quota/billing.")
    except BadRequestError as e:
        return _error_payload(f"OpenAI BadRequest: {e}")
    except Exception as e:
        return _error_payload(f"OpenAI error: {e}")

    try:
        mc = resp.choices[0].message
    except Exception as e:
        return _error_payload(f"No choices/message in response: {e}")

    if not getattr(mc, "tool_calls", None):
        try:
            return json.loads(mc.content)
        except Exception:
            return _error_payload("Model did not return a tool call.")

    try:
        args = mc.tool_calls[0].function.arguments
        data = json.loads(args)
    except Exception as e:
        return _error_payload(f"Failed to parse tool call: {e}")

    data.setdefault("subcategory", None)
    if data.get("confidence") is None:
        data["confidence"] = 0.5
    return data

def categorize_with_openai(description: str, amount: float) -> Dict[str, Any]:
    # Cache
    cached = _get_cache(description, amount)
    if cached:
        return cached

    if not _client:
        return _no_key_fallback()

    try:
        # Primary path: Responses API with JSON Schema (newer SDKs)
        resp = _client.responses.create(
            model=OPENAI_MODEL,
            temperature=0,
            response_format={"type": "json_schema", "json_schema": SCHEMA},
            input=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": USER_TMPL.format(description=description, amount=amount)},
            ],
        )
        content = resp.output_text  # JSON string
        data = json.loads(content)
    except TypeError as e:
        if "response_format" in str(e):
            data = _fallback_chat_tools(description, amount)
        else:
            return _error_payload(f"TypeError: {e}")
    except (APIConnectionError, APITimeoutError):
        return _error_payload("OpenAI connection/timeout error.")
    except RateLimitError:
        return _error_payload("Rate limited by OpenAI — check quota/billing.")
    except BadRequestError as e:
        return _error_payload(f"OpenAI BadRequest: {e}")
    except Exception:
        # Generic fallback for other SDK differences
        data = _fallback_chat_tools(description, amount)

    data.setdefault("subcategory", None)
    if data.get("confidence") is None:
        data["confidence"] = 0.5

    _set_cache(description, amount, data)
    return data
