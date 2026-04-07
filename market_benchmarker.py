"""
market_benchmarker.py
---------------------
Dynamic "Living Policy" Engine — checks whether an expense's amount is
reasonable relative to current real-world market rates.

Instead of only matching against a static policy limit, this module
enriches the audit context with:
  - The fair market rate for that city/category
  - Whether the submitted amount is above or below market

Falls back gracefully to a city-tier model if no live API key is set.
Amadeus API integration is optional (set AMADEUS_API_KEY + AMADEUS_API_SECRET).
"""

import os
from typing import Optional

# Optional Amadeus SDK (won't crash if not installed)
try:
    from amadeus import Client as AmadeusClient, ResponseError
    _AMADEUS_AVAILABLE = True
except ImportError:
    _AMADEUS_AVAILABLE = False


# ── CITY TIER MODEL (offline fallback) ───────────────────────────────────────
# Fair market estimates by city name keywords (case-insensitive substring match)
_CITY_TIERS = {
    # Tier 1 — Very High Cost
    "tier1": {
        "cities": [
            "new york", "nyc", "san francisco", "london", "tokyo", "zurich",
            "geneva", "singapore", "hong kong", "paris", "los angeles", "sydney",
            "dubai", "oslo", "copenhagen",
        ],
        "hotel_rate":    380,
        "meal_per_person": 90,
        "flight_per_mile": 0.22,
    },
    # Tier 2 — High Cost
    "tier2": {
        "cities": [
            "chicago", "boston", "seattle", "miami", "denver", "austin",
            "amsterdam", "berlin", "munich", "toronto", "vancouver", "seoul",
            "melbourne", "frankfurt", "stockholm", "barcelona", "madrid",
        ],
        "hotel_rate":    220,
        "meal_per_person": 60,
        "flight_per_mile": 0.16,
    },
    # Tier 3 — Moderate Cost
    "tier3": {
        "cities": [
            "dallas", "atlanta", "phoenix", "minneapolis", "detroit",
            "bangalore", "mumbai", "delhi", "mexico city", "sao paulo",
            "warsaw", "prague", "budapest", "lisbon", "athens",
        ],
        "hotel_rate":    140,
        "meal_per_person": 35,
        "flight_per_mile": 0.12,
    },
}

_DEFAULT_RATES = {"hotel_rate": 180, "meal_per_person": 45, "flight_per_mile": 0.14}


def _get_city_rates(city: str) -> dict:
    city_lower = city.lower()
    for tier, data in _CITY_TIERS.items():
        if any(c in city_lower for c in data["cities"]):
            return data
    return _DEFAULT_RATES


# ── AMADEUS LIVE LOOKUP (optional) ───────────────────────────────────────────

def _amadeus_hotel_rate(city: str, check_in: str) -> Optional[float]:
    """Try to get a live average hotel rate from Amadeus sandbox API."""
    api_key    = os.getenv("AMADEUS_API_KEY")
    api_secret = os.getenv("AMADEUS_API_SECRET")
    if not _AMADEUS_AVAILABLE or not api_key or not api_secret:
        return None
    try:
        amadeus = AmadeusClient(client_id=api_key, client_secret=api_secret)
        # City search → get IATA city code
        locations = amadeus.reference_data.locations.get(
            keyword=city, subType="CITY"
        ).data
        if not locations:
            return None
        city_code = locations[0]["iataCode"]
        # Hotel search for one night
        hotels = amadeus.shopping.hotel_offers.get(
            cityCode=city_code, checkInDate=check_in,
            checkOutDate=check_in, adults=1, currency="USD",
        ).data
        prices = [
            float(h["offers"][0]["price"]["total"])
            for h in hotels if h.get("offers")
        ]
        return round(sum(prices) / len(prices), 2) if prices else None
    except Exception:
        return None


# ── PUBLIC API ────────────────────────────────────────────────────────────────

def get_market_context(
    category: str,
    city: Optional[str],
    expense_date: Optional[str],
    amount: Optional[float],
) -> dict:
    """
    Return fair-market benchmarking context for an expense.

    Args:
        category:     "Hotels" | "Meals" | "Travel" | etc.
        city:         City name extracted from receipt (or None)
        expense_date: ISO date string (YYYY-MM-DD)
        amount:       Submitted amount in USD

    Returns:
        {
            "fair_market_rate": float,   # benchmark rate for this city/category
            "market_context":   str,     # human-readable comparison
            "over_market":      bool,    # True if submitted > 1.2x market rate
            "source":           str,     # "Amadeus Live" | "City-Tier Model"
        }
    """
    if not city or not amount:
        return {
            "fair_market_rate": None,
            "market_context":   "",
            "over_market":      False,
            "source":           "N/A",
        }

    cat = category.lower()
    rates = _get_city_rates(city)
    source = "City-Tier Model"
    fair_rate = None

    if "hotel" in cat or "lodg" in cat:
        # Try live Amadeus first
        live_rate = _amadeus_hotel_rate(city, expense_date or "2026-04-05")
        if live_rate:
            fair_rate = live_rate
            source = "Amadeus Live"
        else:
            fair_rate = rates.get("hotel_rate", 180)
        label = f"${fair_rate:.0f}/night"

    elif "meal" in cat or "food" in cat or "dining" in cat or "restaurant" in cat:
        fair_rate = rates.get("meal_per_person", 45)
        label = f"${fair_rate:.0f}/person"

    elif "travel" in cat or "flight" in cat or "transport" in cat:
        fair_rate = rates.get("meal_per_person", 45)  # per-trip proxy
        label = f"${fair_rate:.0f} avg"

    else:
        return {
            "fair_market_rate": None,
            "market_context":   "",
            "over_market":      False,
            "source":           source,
        }

    over_market = amount > fair_rate * 1.20
    under_market = amount < fair_rate * 0.60

    if over_market:
        pct = int((amount / fair_rate - 1) * 100)
        context = (
            f"📊 Market rate for {city}: {label} ({source}). "
            f"Submitted amount ${amount:.2f} is {pct}% above market — "
            f"verify this is not an inflated claim."
        )
    elif under_market:
        pct = int((1 - amount / fair_rate) * 100)
        context = (
            f"📊 Market rate for {city}: {label} ({source}). "
            f"Submitted amount ${amount:.2f} is {pct}% below market — likely reasonable."
        )
    else:
        context = (
            f"📊 Market rate for {city}: {label} ({source}). "
            f"Submitted amount ${amount:.2f} is within normal market range."
        )

    return {
        "fair_market_rate": fair_rate,
        "market_context":   context,
        "over_market":      over_market,
        "source":           source,
    }
