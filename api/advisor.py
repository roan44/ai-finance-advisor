from typing import List, Optional, Dict, Any
from openai import OpenAI
from sqlalchemy.orm import Session


from ai import _client, OPENAI_MODEL


def ai_make_advice(description: str, amount: float, merchant: Optional[str] = None) -> str:
    """
    Generate financial advice for a single transaction.
    """
    prompt = f"""
    You are a financial advisor. Analyze this transaction:

    Description: {description}
    Merchant: {merchant or "Unknown"}
    Amount: {amount}

    Provide a short, practical insight if there is one.
    For example:
    - Suggest switching subscriptions if a cheaper option exists.
    - Show monthly/annual cost projections for recurring expenses.
    - Suggest alternatives (e.g. making coffee at home).
    - Show opportunity cost if the money were invested in the S&P500.

    If the transaction is a one-time purchase or not meaningful, return "No insight".
    """

    resp = _client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "You are a concise financial advisor."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
    )

    return resp.choices[0].message.content.strip()


def find_cheaper_alt(service: str, current_price: float) -> str:
    """
    Ask AI if there are cheaper alternatives to a given recurring service.
    """
    prompt = f"""
    The user is paying {current_price} EUR/month for {service}.
    Suggest cheaper alternatives available in Europe in 2025,
    if any, and include example monthly prices.
    If none exist, just say "No known cheaper alternatives."
    """

    resp = _client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "You are a financial advisor who compares services."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )

    return resp.choices[0].message.content.strip()

# ---- Grouping & math helpers ----

def normalize_key(desc: str, merchant_raw: Optional[str], merchant_enriched: Optional[str]) -> str:
    base = (merchant_enriched or merchant_raw or desc or "").strip().lower()
    return " ".join(base.split())

def estimate_monthly_from_window(total_in_window: float, days: int) -> float:
    if days <= 0:
        return total_in_window
    # scale to ~30-day month
    return total_in_window * (30.0 / float(days))

# ---- Subscriptions: benchmark lookup ----

def get_benchmark_alt(db: Session, provider_hint: str, region: str = "IE") -> Optional[Dict[str, Any]]:
    hint = (provider_hint or "").lower()
    rows = db.execute(
        "SELECT provider, plan, monthly_price, currency FROM provider_benchmarks WHERE region=%s",
        (region,)
    ).fetchall()
    if not rows:
        return None

    # guess current from hint
    current = None
    for pr, plan, price, curr in rows:
        if pr.lower() in hint:
            current = {"provider": pr, "plan": plan, "price": float(price), "currency": curr}
            break
    if not current:
        # soft guess for common brands
        if "netflix" in hint:
            current = {"provider":"Netflix","plan":"Standard","price":12.99,"currency":"EUR"}
        elif "vodafone" in hint:
            current = {"provider":"Vodafone","plan":"SIM-only","price":18.00,"currency":"EUR"}
        else:
            return None

    cheaper = None
    for pr, plan, price, curr in rows:
        price = float(price)
        if pr != current["provider"] and price < current["price"]:
            if not cheaper or price < cheaper["price"]:
                cheaper = {"provider": pr, "plan": plan, "price": price, "currency": curr}

    if not cheaper:
        return None
    return {"current": current, "alternative": cheaper}

# ---- Wants: homebrew cost + recipe ----

def get_homebrew_cost(db: Session, item: str, region: str = "IE") -> Optional[float]:
    r = db.execute(
        "SELECT estimated_unit_cost FROM homebrew_costs WHERE item=%s AND region=%s LIMIT 1",
        (item.lower(), region)
    ).fetchone()
    return float(r[0]) if r else None

def suggest_recipe_for(item_name: str, brand_hint: Optional[str] = None) -> Dict[str, Any]:
    """
    LLM creates a tiny, cheap-at-home recipe card. Deterministic tone; no brand defamation.
    """
    brand = f" (inspired by {brand_hint})" if brand_hint else ""
    prompt = f"""
Create a concise home recipe{brand} for: {item_name}.
Constraints:
- Keep total ingredient cost low and list simple equipment.
- Provide: title, ingredients (bulleted), method (3-6 short steps), est_cost_per_serving (€), time_minutes.
- Max 120 words.
Return pure JSON with keys: title, ingredients (array), method (array), est_cost_per_serving, time_minutes.
"""
    schema = {
      "name":"RecipeCard",
      "schema":{
        "type":"object",
        "additionalProperties": False,
        "properties":{
          "title":{"type":"string"},
          "ingredients":{"type":"array","items":{"type":"string"}},
          "method":{"type":"array","items":{"type":"string"}},
          "est_cost_per_serving":{"type":"number"},
          "time_minutes":{"type":"number"}
        },
        "required":["title","ingredients","method","est_cost_per_serving","time_minutes"]
      }
    }
    try:
        resp = _client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role":"system","content":"You write very concise, practical recipe cards as JSON only."},
                {"role":"user","content": prompt}
            ],
            temperature=0,
            response_format={"type":"json_schema","json_schema":schema}
        )
        return json.loads(resp.choices[0].message.content)
    except Exception:
        # safe fallback
        return {
          "title": f"DIY {item_name}",
          "ingredients": ["Ground coffee", "Hot water", "Milk (optional)"],
          "method": ["Brew coffee", "Add milk to taste", "Serve immediately"],
          "est_cost_per_serving": 0.7,
          "time_minutes": 5
        }
