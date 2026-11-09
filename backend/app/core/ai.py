"""AI analyst using the OpenAI API.

Privacy: only AGGREGATED numbers are sent (totals, segments, branches, districts, products).
Customer phone numbers and names are never sent to OpenAI.
"""

import json
from datetime import date, datetime

import httpx

from . import analytics as an

OPENAI_URL = "https://api.openai.com/v1/chat/completions"

SYSTEM_PROMPT = """You are a senior retail & pharmacy business analyst working for the management
of a pharmacy chain in Egypt. You get a JSON snapshot of their sales data (already aggregated)
and answer the manager's questions.

Rules:
- Use ONLY the numbers in the data. If something is not in the data, say so and suggest what
  data would be needed. Never invent numbers.
- Be concrete and practical: name branches, districts, segments and products, give numbers,
  and end with 3-5 prioritised actions the manager can take this week.
- Currency is EGP. Format numbers with thousands separators.
- Answer in {language}. Use short paragraphs, bullet points and markdown tables when helpful.
- Explain terms briefly the first time (e.g. RFM segment, churn risk, lift).
"""

REPORT_PROMPT = """Write an executive report for the selected period with these sections:
1. Headline (3 bullet points)
2. Sales & customers performance (with change vs previous period if available)
3. Branch performance (best / weakest, growth)
4. Customer health: segments, churn risk, customers due to visit
5. Products & baskets (top products, bundle opportunities)
6. Areas (strong / weak districts)
7. Recommended actions (prioritised, with expected impact)"""


def _default(o):
    if isinstance(o, (date, datetime)):
        return o.isoformat()[:10]
    return str(o)


def build_context(f: an.Filters, settings: dict) -> dict:
    s = an.summary(f, settings)
    ins = an.insights(f, settings)
    area = an.area(f, 5)
    return {
        "filters": {"date_from": f.date_from, "date_to": f.date_to,
                    "branches": f.branches or f.allowed_branches or "all",
                    "sales_types": f.types or "all", "districts": f.districts or "all"},
        "reference_date": s["reference_date"],
        "definitions": {
            "status": f"active <= {settings['active_days']} days since last visit, "
                      f"needs attention <= {settings['attention_days']} days, else inactive",
            "high_value": f"total spend >= {settings['high_value_spend']} EGP",
            "visit": "one invoice",
            "churn_risk": "days since last visit compared with the customer's own average gap "
                          "between visits (high = more than 2x their usual gap)",
        },
        "kpis": s["kpis"], "previous_period_kpis": s["previous"],
        "new_customers": s["new_customers"], "customer_status": s["segments"],
        "top_by_sales": s["insights"], "monthly": s["monthly"][-24:],
        "branches": s["by_branch"], "sales_types": s["by_type"], "seasons": s["by_season"],
        "top_products": s["top_items"],
        "rfm_segments": ins["rfm"], "churn_risk": ins["churn"], "visit_timing": ins["due"],
        "pareto": ins["pareto"], "branch_growth": ins["branch_growth"],
        "new_vs_returning_by_month": ins["new_vs_returning"][-12:],
        "bought_together": ins["basket"][:15],
        "cohort_retention": ins["cohorts"][-6:],
        "districts_top": area["districts"][:20], "districts_weak": area["weak"],
        "alerts": [a["en"] for a in ins["alerts"]],
    }


class AIError(Exception):
    pass


def ask(question: str, history: list[dict], f: an.Filters, settings: dict, lang: str,
        report: bool = False) -> dict:
    key = settings.get("openai_api_key")
    if not key:
        raise AIError("The OpenAI API key is not set. An admin can add it in Settings.")
    ctx = build_context(f, settings)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(
            language="Arabic (Egyptian business Arabic)" if lang == "ar" else "English")},
        {"role": "system", "content": "DATA:\n" + json.dumps(ctx, default=_default,
                                                             ensure_ascii=False)},
    ]
    for m in history[-8:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": str(m["content"])[:4000]})
    messages.append({"role": "user", "content": REPORT_PROMPT if report else question})

    try:
        r = httpx.post(OPENAI_URL, timeout=120,
                       headers={"Authorization": f"Bearer {key}"},
                       json={"model": settings.get("openai_model") or "gpt-4.1-mini",
                             "messages": messages})
    except httpx.HTTPError as e:
        raise AIError(f"Could not reach OpenAI: {e}") from e
    if r.status_code != 200:
        try:
            msg = r.json()["error"]["message"]
        except Exception:  # noqa: BLE001
            msg = r.text[:300]
        raise AIError(f"OpenAI error ({r.status_code}): {msg}")
    data = r.json()
    return {"answer": data["choices"][0]["message"]["content"],
            "model": data.get("model"), "usage": data.get("usage")}
