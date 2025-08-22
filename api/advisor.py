import json  
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
    Ask AI to find cheaper alternatives to any subscription service.
    Enhanced to handle all types of subscriptions with Irish market knowledge.
    """
    prompt = f"""
    You are a financial advisor helping Irish consumers find cheaper alternatives to subscription services.
    
    Current service: {service}
    Current monthly cost: €{current_price:.2f}
    
    Your task:
    1. Identify what type of service this is (streaming, telecom, internet, utilities, etc.)
    2. Research cheaper alternatives available in Ireland in 2025
    3. Provide specific recommendations with prices
    4. Include any switching considerations (contracts, setup fees, etc.)
    
    For different service types, consider:
    - Streaming: Netflix vs Prime Video, Disney+, Apple TV+, etc.
    - Mobile/Phone: Vodafone vs Three, Eir, 48, GoMo, etc.
    - Internet: Eir vs Virgin Media, Sky, Three Broadband, etc.
    - Utilities: Electric Ireland vs SSE Airtricity, Energia, etc.
    - Insurance: Compare car/home insurance providers
    - Software: Adobe vs Canva, Office vs Google Workspace, etc.
    
    If cheaper alternatives exist, format like:
    "Alternative: [Provider] [Plan] at €[price]/month (save €[amount]/month). 
    Benefits: [key benefits]
    Considerations: [any downsides or switching costs]"
    
    If no cheaper alternatives exist, respond with:
    "No known cheaper alternatives available in the Irish market. This appears to be competitively priced."
    
    Be specific about Irish providers and current 2025 pricing.
    """

    resp = _client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "You are a financial advisor specializing in Irish consumer services and subscriptions. You have detailed knowledge of Irish providers, pricing, and switching processes."},
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
    AI creates a homemade alternative recipe for any purchase, with cost savings analysis.
    """
    prompt = f"""
You are a financial advisor who helps people save money by making things at home instead of buying them.

Analyze this purchase: "{item_name}" from "{brand_hint or 'unknown merchant'}"

Your task:
1. Determine if this can reasonably be made/done at home for less cost
2. If YES: Create a practical homemade recipe/alternative with cost savings
3. If NO: Return a response indicating it's not suitable for homemade alternatives

For homemade alternatives, provide:
- title: Descriptive name for the homemade version
- ingredients: List of ingredients/supplies needed (mention where to buy in Ireland like Aldi, Tesco)
- method: 3-6 step process to make it
- est_cost_per_serving: Realistic cost in euros for homemade version
- time_minutes: Time needed to make it
- is_viable: true (since you're providing a recipe)

If not suitable for homemade (like services, digital purchases, etc.):
- title: "Not suitable for homemade alternative"
- ingredients: []
- method: ["This purchase cannot be easily replicated at home"]
- est_cost_per_serving: 0
- time_minutes: 0
- is_viable: false

Be realistic about costs and time. Focus on significant savings opportunities.

Return only valid JSON with keys: title, ingredients, method, est_cost_per_serving, time_minutes, is_viable
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
          "time_minutes":{"type":"number"},
          "is_viable":{"type":"boolean"}
        },
        "required":["title","ingredients","method","est_cost_per_serving","time_minutes","is_viable"]
      }
    }
    
    try:
        resp = _client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role":"system","content":"You are a practical financial advisor who suggests realistic homemade alternatives to save money. Be honest about what can and cannot be made at home."},
                {"role":"user","content": prompt}
            ],
            temperature=0.3,
            response_format={"type":"json_schema","json_schema":schema}
        )
        return json.loads(resp.choices[0].message.content)
    except Exception:
        # Safe fallback for any failures
        return {
            "title": "Homemade Alternative",
            "ingredients": ["Various ingredients from local supermarket"],
            "method": ["Research homemade version", "Gather ingredients", "Follow online recipe"],
            "est_cost_per_serving": 1.00,
            "time_minutes": 30,
            "is_viable": True
        }