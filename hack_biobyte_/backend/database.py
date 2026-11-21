"""
database.py — In-memory application state for Naija Fork.

Pre-seeded with:
  • 30 realistic Nigerian ingredients (6 animal-derived reference + 24 plant-based)
    with current 2025-2026 Naira market pricing.
  • 2 restaurant presets for instant demo initialization.
  • City → nearest wholesale market resolution table.

PRICING NOTE: All costs are ₦ per 100 g (approximate retail/wholesale 2025-2026).
"""

from __future__ import annotations

from typing import Optional

from models import (
    ApprovedAlternative,
    Ingredient,
    DishIngredient,
    MenuDish,
    Order,
    Restaurant,
    StoredTransformation,
)


# ─── City → Nearest Wholesale Market ─────────────────────────────────────────

CITY_MARKET_MAP: dict[str, str] = {
    # Lagos
    "lagos": "Lagos - Mile 12",
    "yaba": "Lagos - Mile 12",
    "ikeja": "Lagos - Mile 12",
    "victoria island": "Lagos - Mile 12",
    "lekki": "Lagos - Mile 12",
    "surulere": "Lagos - Mile 12",
    # Abuja
    "abuja": "Abuja - Wuse",
    "wuse": "Abuja - Wuse",
    "garki": "Abuja - Wuse",
    "maitama": "Abuja - Wuse",
    "gwarinpa": "Abuja - Wuse",
    # Port Harcourt
    "port harcourt": "Port Harcourt - Oil Mill",
    "ph": "Port Harcourt - Oil Mill",
    "rumuola": "Port Harcourt - Oil Mill",
    # Kano
    "kano": "Kano - Sabon Gari",
    "sabon gari": "Kano - Sabon Gari",
    # Others
    "ibadan": "Ibadan - Bodija",
    "enugu": "Enugu - Ogbete",
    "onitsha": "Onitsha - Main Market",
    "benin city": "Benin City - Oba Market",
    "calabar": "Calabar - Watt Market",
    "owerri": "Owerri - Eke-Ukwu",
    "warri": "Warri - Main Market",
    "jos": "Jos - Terminus Market",
}


def resolve_nearest_market(city: str) -> str:
    """Auto-resolve the nearest wholesale market given a city or district name."""
    normalized = city.lower().strip()
    for key, market in CITY_MARKET_MAP.items():
        if key in normalized or normalized in key:
            return market
    return f"{city.title()} - Local Market"   # graceful default


# ─── 30-Ingredient Nigerian Catalog ───────────────────────────────────────────
# Non-plant-based entries (is_plant_based=False) are REFERENCE ONLY.
# The optimizer uses them to understand what it is replacing; they are never
# recommended as outputs.

INGREDIENT_CATALOG: list[dict] = [

    # ══ ANIMAL-DERIVED (Reference / Replacement Targets) ═══════════════════

    {
        "id": "beef",
        "name": "Beef (Boneless)",
        "local_name": None,
        "category": "protein",
        "is_plant_based": False,
        "cost_per_100g_ngn": 650.0,
        "protein_g_per_100g": 26.0,
        "saturated_fat_g_per_100g": 8.5,
        "fiber_g_per_100g": 0.0,
        "calories_per_100g": 250.0,
        "texture_tags": ["chewy", "fibrous", "meaty", "dense", "tender"],
        "umami_score": 7,
        "familiarity_score": 10,
        "prep_complexity": "medium",
        "available_markets": [
            "Lagos - Mile 12", "Abuja - Wuse",
            "Port Harcourt - Oil Mill", "Kano - Sabon Gari", "Ibadan - Bodija",
        ],
    },
    {
        "id": "goat_meat",
        "name": "Goat Meat",
        "local_name": "Asun / Nkwobi",
        "category": "protein",
        "is_plant_based": False,
        "cost_per_100g_ngn": 700.0,
        "protein_g_per_100g": 27.0,
        "saturated_fat_g_per_100g": 7.0,
        "fiber_g_per_100g": 0.0,
        "calories_per_100g": 230.0,
        "texture_tags": ["chewy", "gamey", "meaty", "fibrous", "smoky"],
        "umami_score": 8,
        "familiarity_score": 10,
        "prep_complexity": "medium",
        "available_markets": [
            "Lagos - Mile 12", "Abuja - Wuse",
            "Port Harcourt - Oil Mill", "Kano - Sabon Gari",
        ],
    },
    {
        "id": "crayfish",
        "name": "Dried Crayfish",
        "local_name": "Nshiko / Ede Nkwu",
        "category": "umami",
        "is_plant_based": False,
        "cost_per_100g_ngn": 800.0,
        "protein_g_per_100g": 18.0,
        "saturated_fat_g_per_100g": 0.5,
        "fiber_g_per_100g": 0.0,
        "calories_per_100g": 100.0,
        "texture_tags": ["crunchy", "pungent", "briny", "intense", "saline"],
        "umami_score": 9,
        "familiarity_score": 10,
        "prep_complexity": "low",
        "available_markets": [
            "Lagos - Mile 12", "Abuja - Wuse", "Port Harcourt - Oil Mill",
            "Kano - Sabon Gari", "Ibadan - Bodija",
        ],
    },
    {
        "id": "ponmo",
        "name": "Ponmo (Cow Skin)",
        "local_name": "Ponmo",
        "category": "protein",
        "is_plant_based": False,
        "cost_per_100g_ngn": 300.0,
        "protein_g_per_100g": 12.0,
        "saturated_fat_g_per_100g": 3.0,
        "fiber_g_per_100g": 0.0,
        "calories_per_100g": 110.0,
        "texture_tags": ["gelatinous", "chewy", "slippery", "soft"],
        "umami_score": 5,
        "familiarity_score": 9,
        "prep_complexity": "high",
        "available_markets": ["Lagos - Mile 12", "Abuja - Wuse", "Port Harcourt - Oil Mill"],
    },
    {
        "id": "stockfish",
        "name": "Stockfish",
        "local_name": "Okporoko",
        "category": "protein",
        "is_plant_based": False,
        "cost_per_100g_ngn": 600.0,
        "protein_g_per_100g": 79.0,
        "saturated_fat_g_per_100g": 0.5,
        "fiber_g_per_100g": 0.0,
        "calories_per_100g": 330.0,
        "texture_tags": ["flaky", "dense", "firm", "chewy", "pungent"],
        "umami_score": 8,
        "familiarity_score": 9,
        "prep_complexity": "medium",
        "available_markets": ["Lagos - Mile 12", "Abuja - Wuse", "Port Harcourt - Oil Mill"],
    },
    {
        "id": "chicken",
        "name": "Chicken (Broiler)",
        "local_name": None,
        "category": "protein",
        "is_plant_based": False,
        "cost_per_100g_ngn": 450.0,
        "protein_g_per_100g": 25.0,
        "saturated_fat_g_per_100g": 4.0,
        "fiber_g_per_100g": 0.0,
        "calories_per_100g": 215.0,
        "texture_tags": ["tender", "moist", "fibrous", "mild", "juicy"],
        "umami_score": 6,
        "familiarity_score": 10,
        "prep_complexity": "medium",
        "available_markets": [
            "Lagos - Mile 12", "Abuja - Wuse", "Port Harcourt - Oil Mill",
            "Kano - Sabon Gari", "Ibadan - Bodija",
        ],
    },

    # ══ PLANT-BASED PROTEINS ═══════════════════════════════════════════════

    {
        "id": "soya_chunks",
        "name": "Textured Soya Chunks",
        "local_name": "Soya Meat",
        "category": "protein",
        "is_plant_based": True,
        "cost_per_100g_ngn": 140.0,
        "protein_g_per_100g": 52.0,
        "saturated_fat_g_per_100g": 0.5,
        "fiber_g_per_100g": 4.0,
        "calories_per_100g": 330.0,
        "texture_tags": ["chewy", "meaty", "fibrous", "dense", "absorbent"],
        "umami_score": 4,
        "familiarity_score": 7,
        "prep_complexity": "low",
        "available_markets": [
            "Lagos - Mile 12", "Abuja - Wuse", "Port Harcourt - Oil Mill",
            "Kano - Sabon Gari", "Ibadan - Bodija", "Enugu - Ogbete",
        ],
    },
    {
        "id": "oyster_mushrooms",
        "name": "Fresh Oyster Mushrooms",
        "local_name": "Olu Olu",
        "category": "protein",
        "is_plant_based": True,
        "cost_per_100g_ngn": 180.0,
        "protein_g_per_100g": 3.3,
        "saturated_fat_g_per_100g": 0.1,
        "fiber_g_per_100g": 2.3,
        "calories_per_100g": 33.0,
        "texture_tags": ["meaty", "tender", "chewy", "silky", "umami-rich"],
        "umami_score": 8,
        "familiarity_score": 6,
        "prep_complexity": "low",
        "available_markets": [
            "Lagos - Mile 12", "Abuja - Wuse",
            "Port Harcourt - Oil Mill", "Ibadan - Bodija",
        ],
    },
    {
        "id": "smoked_tofu_wara",
        "name": "Smoked Local Tofu",
        "local_name": "Wara Sisun",
        "category": "protein",
        "is_plant_based": True,
        "cost_per_100g_ngn": 200.0,
        "protein_g_per_100g": 15.0,
        "saturated_fat_g_per_100g": 1.0,
        "fiber_g_per_100g": 0.3,
        "calories_per_100g": 120.0,
        "texture_tags": ["firm", "smoky", "dense", "chewy", "creamy"],
        "umami_score": 5,
        "familiarity_score": 7,
        "prep_complexity": "low",
        "available_markets": [
            "Lagos - Mile 12", "Abuja - Wuse",
            "Kano - Sabon Gari", "Ibadan - Bodija",
        ],
    },
    {
        "id": "bambara_nut",
        "name": "Bambara Nut (Okpa Flour)",
        "local_name": "Okpa",
        "category": "protein",
        "is_plant_based": True,
        "cost_per_100g_ngn": 130.0,
        "protein_g_per_100g": 19.0,
        "saturated_fat_g_per_100g": 1.0,
        "fiber_g_per_100g": 5.0,
        "calories_per_100g": 370.0,
        "texture_tags": ["soft", "creamy", "earthy", "dense", "nutty"],
        "umami_score": 3,
        "familiarity_score": 8,
        "prep_complexity": "medium",
        "available_markets": [
            "Enugu - Ogbete", "Onitsha - Main Market",
            "Port Harcourt - Oil Mill", "Ibadan - Bodija",
        ],
    },
    {
        "id": "pigeon_pea",
        "name": "Pigeon Pea",
        "local_name": "Fio-Fio",
        "category": "protein",
        "is_plant_based": True,
        "cost_per_100g_ngn": 120.0,
        "protein_g_per_100g": 22.0,
        "saturated_fat_g_per_100g": 0.5,
        "fiber_g_per_100g": 15.0,
        "calories_per_100g": 343.0,
        "texture_tags": ["soft", "earthy", "nutty", "creamy", "fibrous"],
        "umami_score": 3,
        "familiarity_score": 7,
        "prep_complexity": "medium",
        "available_markets": [
            "Enugu - Ogbete", "Onitsha - Main Market",
            "Port Harcourt - Oil Mill", "Ibadan - Bodija", "Lagos - Mile 12",
        ],
    },
    {
        "id": "black_eyed_peas",
        "name": "Black-Eyed Peas",
        "local_name": "Ewa Oloyin",
        "category": "protein",
        "is_plant_based": True,
        "cost_per_100g_ngn": 160.0,
        "protein_g_per_100g": 24.0,
        "saturated_fat_g_per_100g": 0.3,
        "fiber_g_per_100g": 11.0,
        "calories_per_100g": 336.0,
        "texture_tags": ["soft", "creamy", "earthy", "firm", "dense"],
        "umami_score": 3,
        "familiarity_score": 9,
        "prep_complexity": "medium",
        "available_markets": [
            "Lagos - Mile 12", "Abuja - Wuse", "Port Harcourt - Oil Mill",
            "Kano - Sabon Gari", "Ibadan - Bodija",
        ],
    },
    {
        "id": "groundnuts",
        "name": "Groundnuts (Peanuts)",
        "local_name": "Epa / Gyada",
        "category": "protein",
        "is_plant_based": True,
        "cost_per_100g_ngn": 200.0,
        "protein_g_per_100g": 25.0,
        "saturated_fat_g_per_100g": 7.0,
        "fiber_g_per_100g": 8.5,
        "calories_per_100g": 567.0,
        "texture_tags": ["crunchy", "nutty", "rich", "oily", "dense"],
        "umami_score": 4,
        "familiarity_score": 9,
        "prep_complexity": "low",
        "available_markets": [
            "Lagos - Mile 12", "Abuja - Wuse", "Port Harcourt - Oil Mill",
            "Kano - Sabon Gari", "Ibadan - Bodija",
        ],
    },

    # ══ PLANT-BASED UMAMI SOURCES ══════════════════════════════════════════

    {
        "id": "iru",
        "name": "Fermented Locust Beans",
        "local_name": "Iru / Dawa-Dawa",
        "category": "umami",
        "is_plant_based": True,
        "cost_per_100g_ngn": 150.0,
        "protein_g_per_100g": 25.0,
        "saturated_fat_g_per_100g": 5.0,
        "fiber_g_per_100g": 10.0,
        "calories_per_100g": 400.0,
        "texture_tags": ["pungent", "intense", "fermented", "sticky", "earthy"],
        "umami_score": 9,
        "familiarity_score": 8,
        "prep_complexity": "low",
        "available_markets": [
            "Lagos - Mile 12", "Abuja - Wuse", "Port Harcourt - Oil Mill",
            "Kano - Sabon Gari", "Ibadan - Bodija",
        ],
    },
    {
        "id": "ogiri",
        "name": "Fermented Castor / Melon Seeds",
        "local_name": "Ogiri-Igbo",
        "category": "umami",
        "is_plant_based": True,
        "cost_per_100g_ngn": 160.0,
        "protein_g_per_100g": 20.0,
        "saturated_fat_g_per_100g": 4.0,
        "fiber_g_per_100g": 8.0,
        "calories_per_100g": 350.0,
        "texture_tags": ["pungent", "intense", "fermented", "paste-like", "rich"],
        "umami_score": 9,
        "familiarity_score": 7,
        "prep_complexity": "low",
        "available_markets": [
            "Lagos - Mile 12", "Abuja - Wuse",
            "Enugu - Ogbete", "Onitsha - Main Market", "Port Harcourt - Oil Mill",
        ],
    },
    {
        "id": "mushroom_bouillon",
        "name": "Mushroom Bouillon Powder",
        "local_name": None,
        "category": "umami",
        "is_plant_based": True,
        "cost_per_100g_ngn": 250.0,
        "protein_g_per_100g": 12.0,
        "saturated_fat_g_per_100g": 0.5,
        "fiber_g_per_100g": 0.0,
        "calories_per_100g": 220.0,
        "texture_tags": ["powder", "intense", "savory", "clean", "neutral"],
        "umami_score": 7,
        "familiarity_score": 6,
        "prep_complexity": "low",
        "available_markets": [
            "Lagos - Mile 12", "Abuja - Wuse",
            "Port Harcourt - Oil Mill", "Ibadan - Bodija",
        ],
    },
    {
        "id": "dried_oyster_mushroom",
        "name": "Dried Oyster Mushrooms",
        "local_name": "Olu gbigbe",
        "category": "umami",
        "is_plant_based": True,
        "cost_per_100g_ngn": 220.0,
        "protein_g_per_100g": 10.0,
        "saturated_fat_g_per_100g": 0.3,
        "fiber_g_per_100g": 7.0,
        "calories_per_100g": 265.0,
        "texture_tags": ["intense", "smoky", "chewy", "umami-rich", "earthy"],
        "umami_score": 8,
        "familiarity_score": 6,
        "prep_complexity": "low",
        "available_markets": [
            "Lagos - Mile 12", "Abuja - Wuse", "Port Harcourt - Oil Mill",
        ],
    },

    # ══ BASE & FAT INGREDIENTS ═════════════════════════════════════════════

    {
        "id": "egusi_seeds",
        "name": "Egusi (Melon Seeds)",
        "local_name": "Egusi",
        "category": "base",
        "is_plant_based": True,
        "cost_per_100g_ngn": 280.0,
        "protein_g_per_100g": 28.0,
        "saturated_fat_g_per_100g": 11.0,
        "fiber_g_per_100g": 2.5,
        "calories_per_100g": 557.0,
        "texture_tags": ["nutty", "rich", "creamy", "grainy", "dense"],
        "umami_score": 5,
        "familiarity_score": 10,
        "prep_complexity": "medium",
        "available_markets": [
            "Lagos - Mile 12", "Abuja - Wuse", "Port Harcourt - Oil Mill",
            "Kano - Sabon Gari", "Ibadan - Bodija",
        ],
    },
    {
        "id": "palm_oil",
        "name": "Red Palm Oil",
        "local_name": "Epo Pupa",
        "category": "fat",
        "is_plant_based": True,
        "cost_per_100g_ngn": 180.0,
        "protein_g_per_100g": 0.0,
        "saturated_fat_g_per_100g": 49.3,
        "fiber_g_per_100g": 0.0,
        "calories_per_100g": 884.0,
        "texture_tags": ["oily", "rich", "smooth", "coating"],
        "umami_score": 2,
        "familiarity_score": 10,
        "prep_complexity": "low",
        "available_markets": [
            "Lagos - Mile 12", "Abuja - Wuse", "Port Harcourt - Oil Mill",
            "Kano - Sabon Gari", "Ibadan - Bodija",
        ],
    },
    {
        "id": "coconut_oil",
        "name": "Virgin Coconut Oil",
        "local_name": None,
        "category": "fat",
        "is_plant_based": True,
        "cost_per_100g_ngn": 400.0,
        "protein_g_per_100g": 0.0,
        "saturated_fat_g_per_100g": 86.5,
        "fiber_g_per_100g": 0.0,
        "calories_per_100g": 892.0,
        "texture_tags": ["oily", "light", "smooth", "subtle", "tropical"],
        "umami_score": 1,
        "familiarity_score": 5,
        "prep_complexity": "low",
        "available_markets": ["Lagos - Mile 12", "Abuja - Wuse", "Port Harcourt - Oil Mill"],
    },

    # ══ VEGETABLES & LEAVES ════════════════════════════════════════════════

    {
        "id": "ugu_leaves",
        "name": "Fluted Pumpkin Leaves",
        "local_name": "Ugu",
        "category": "vegetable",
        "is_plant_based": True,
        "cost_per_100g_ngn": 80.0,
        "protein_g_per_100g": 4.0,
        "saturated_fat_g_per_100g": 0.1,
        "fiber_g_per_100g": 3.0,
        "calories_per_100g": 35.0,
        "texture_tags": ["leafy", "tender", "fresh", "slightly-bitter"],
        "umami_score": 2,
        "familiarity_score": 10,
        "prep_complexity": "low",
        "available_markets": [
            "Lagos - Mile 12", "Abuja - Wuse", "Port Harcourt - Oil Mill",
            "Kano - Sabon Gari", "Ibadan - Bodija",
        ],
    },
    {
        "id": "uziza_leaves",
        "name": "Uziza Leaves",
        "local_name": "Uziza",
        "category": "vegetable",
        "is_plant_based": True,
        "cost_per_100g_ngn": 120.0,
        "protein_g_per_100g": 3.5,
        "saturated_fat_g_per_100g": 0.1,
        "fiber_g_per_100g": 4.5,
        "calories_per_100g": 42.0,
        "texture_tags": ["leafy", "peppery", "aromatic", "fibrous"],
        "umami_score": 3,
        "familiarity_score": 8,
        "prep_complexity": "low",
        "available_markets": [
            "Lagos - Mile 12", "Port Harcourt - Oil Mill",
            "Enugu - Ogbete", "Onitsha - Main Market",
        ],
    },
    {
        "id": "oha_leaves",
        "name": "Oha (Ora) Leaves",
        "local_name": "Ora",
        "category": "vegetable",
        "is_plant_based": True,
        "cost_per_100g_ngn": 100.0,
        "protein_g_per_100g": 3.0,
        "saturated_fat_g_per_100g": 0.1,
        "fiber_g_per_100g": 3.5,
        "calories_per_100g": 38.0,
        "texture_tags": ["leafy", "tender", "mild", "silky"],
        "umami_score": 2,
        "familiarity_score": 8,
        "prep_complexity": "low",
        "available_markets": [
            "Enugu - Ogbete", "Onitsha - Main Market",
            "Port Harcourt - Oil Mill", "Lagos - Mile 12",
        ],
    },

    # ══ SPICES ════════════════════════════════════════════════════════════

    {
        "id": "ata_rodo",
        "name": "Scotch Bonnet Pepper",
        "local_name": "Ata Rodo",
        "category": "spice",
        "is_plant_based": True,
        "cost_per_100g_ngn": 100.0,
        "protein_g_per_100g": 1.8,
        "saturated_fat_g_per_100g": 0.0,
        "fiber_g_per_100g": 1.5,
        "calories_per_100g": 40.0,
        "texture_tags": ["fiery", "fruity", "aromatic", "juicy"],
        "umami_score": 2,
        "familiarity_score": 10,
        "prep_complexity": "low",
        "available_markets": [
            "Lagos - Mile 12", "Abuja - Wuse", "Port Harcourt - Oil Mill",
            "Kano - Sabon Gari", "Ibadan - Bodija",
        ],
    },
    {
        "id": "smoked_paprika",
        "name": "Smoked Paprika",
        "local_name": None,
        "category": "spice",
        "is_plant_based": True,
        "cost_per_100g_ngn": 350.0,
        "protein_g_per_100g": 14.0,
        "saturated_fat_g_per_100g": 1.5,
        "fiber_g_per_100g": 34.9,
        "calories_per_100g": 282.0,
        "texture_tags": ["smoky", "powder", "intense", "woody"],
        "umami_score": 4,
        "familiarity_score": 6,
        "prep_complexity": "low",
        "available_markets": [
            "Lagos - Mile 12", "Abuja - Wuse",
            "Port Harcourt - Oil Mill", "Ibadan - Bodija",
        ],
    },
    {
        "id": "onion",
        "name": "Red Onion",
        "local_name": "Alubosa",
        "category": "base",
        "is_plant_based": True,
        "cost_per_100g_ngn": 70.0,
        "protein_g_per_100g": 1.1,
        "saturated_fat_g_per_100g": 0.0,
        "fiber_g_per_100g": 1.7,
        "calories_per_100g": 40.0,
        "texture_tags": ["crunchy", "pungent", "sweet", "aromatic"],
        "umami_score": 3,
        "familiarity_score": 10,
        "prep_complexity": "low",
        "available_markets": [
            "Lagos - Mile 12", "Abuja - Wuse", "Port Harcourt - Oil Mill",
            "Kano - Sabon Gari", "Ibadan - Bodija",
        ],
    },
    {
        "id": "tomatoes",
        "name": "Fresh Tomatoes",
        "local_name": "Tomati",
        "category": "base",
        "is_plant_based": True,
        "cost_per_100g_ngn": 80.0,
        "protein_g_per_100g": 0.9,
        "saturated_fat_g_per_100g": 0.0,
        "fiber_g_per_100g": 1.2,
        "calories_per_100g": 18.0,
        "texture_tags": ["juicy", "acidic", "soft", "bright"],
        "umami_score": 4,
        "familiarity_score": 10,
        "prep_complexity": "low",
        "available_markets": [
            "Lagos - Mile 12", "Abuja - Wuse", "Port Harcourt - Oil Mill",
            "Kano - Sabon Gari", "Ibadan - Bodija",
        ],
    },

    # ══ SWALLOWS & STARCHES ════════════════════════════════════════════════

    {
        "id": "garri",
        "name": "Garri (Cassava Flake)",
        "local_name": "Eba",
        "category": "swallow",
        "is_plant_based": True,
        "cost_per_100g_ngn": 90.0,
        "protein_g_per_100g": 1.5,
        "saturated_fat_g_per_100g": 0.1,
        "fiber_g_per_100g": 1.8,
        "calories_per_100g": 357.0,
        "texture_tags": ["stretchy", "smooth", "doughy", "starchy"],
        "umami_score": 1,
        "familiarity_score": 10,
        "prep_complexity": "low",
        "available_markets": [
            "Lagos - Mile 12", "Abuja - Wuse", "Port Harcourt - Oil Mill",
            "Kano - Sabon Gari", "Ibadan - Bodija",
        ],
    },
    {
        "id": "unripe_plantain",
        "name": "Unripe Plantain",
        "local_name": "Ogede Omidun",
        "category": "base",
        "is_plant_based": True,
        "cost_per_100g_ngn": 90.0,
        "protein_g_per_100g": 1.3,
        "saturated_fat_g_per_100g": 0.1,
        "fiber_g_per_100g": 2.3,
        "calories_per_100g": 122.0,
        "texture_tags": ["starchy", "firm", "mild", "slightly-sweet"],
        "umami_score": 2,
        "familiarity_score": 9,
        "prep_complexity": "low",
        "available_markets": [
            "Lagos - Mile 12", "Abuja - Wuse",
            "Port Harcourt - Oil Mill", "Ibadan - Bodija",
        ],
    },
    {
        "id": "parboiled_rice",
        "name": "Parboiled Rice",
        "local_name": "Orisa",
        "category": "swallow",
        "is_plant_based": True,
        "cost_per_100g_ngn": 220.0,
        "protein_g_per_100g": 2.5,
        "saturated_fat_g_per_100g": 0.1,
        "fiber_g_per_100g": 0.5,
        "calories_per_100g": 370.0,
        "texture_tags": ["fluffy", "grainy", "starchy", "mild"],
        "umami_score": 1,
        "familiarity_score": 10,
        "prep_complexity": "low",
        "available_markets": [
            "Lagos - Mile 12", "Abuja - Wuse", "Port Harcourt - Oil Mill",
            "Kano - Sabon Gari", "Ibadan - Bodija",
        ],
    },
]


# ─── Restaurant Preset 1: Mama Put Express – Yaba, Lagos ─────────────────────

_PRESET_MAMA_PUT: dict = {
    "id": "mama_put_express",
    "name": "Mama Put Express – Yaba, Lagos",
    "city": "Yaba, Lagos",
    "nearest_market": "Lagos - Mile 12",
    "pantry": {
        "soya_chunks":        500.0,
        "oyster_mushrooms":   300.0,
        "iru":                200.0,
        "ogiri":              100.0,
        "egusi_seeds":       1000.0,
        "palm_oil":          2000.0,
        "ugu_leaves":         500.0,
        "ata_rodo":           300.0,
        "onion":              500.0,
        "garri":             2000.0,
        "tomatoes":           500.0,
        "smoked_paprika":     200.0,
        "mushroom_bouillon":  100.0,
    },
    "menu": [
        {
            "id": "beef_egusi_eba",
            "name": "Beef Egusi Soup with Eba",
            "description": (
                "Rich, hearty egusi soup cooked with tender beef and aromatic crayfish, "
                "served with freshly prepared eba."
            ),
            "category": "main",
            "ingredients": [
                {"ingredient_id": "beef",        "quantity_g": 200.0, "is_primary": True},
                {"ingredient_id": "crayfish",    "quantity_g":  20.0, "is_primary": False},
                {"ingredient_id": "egusi_seeds", "quantity_g": 100.0, "is_primary": False},
                {"ingredient_id": "palm_oil",    "quantity_g":  50.0, "is_primary": False},
                {"ingredient_id": "ugu_leaves",  "quantity_g":  80.0, "is_primary": False},
                {"ingredient_id": "ata_rodo",    "quantity_g":  30.0, "is_primary": False},
                {"ingredient_id": "onion",       "quantity_g":  50.0, "is_primary": False},
                {"ingredient_id": "garri",       "quantity_g": 150.0, "is_primary": False},
            ],
            "prep_time_minutes": 45,
            "selling_price_ngn": 3500.0,
        },
        {
            "id": "ofe_onugbu",
            "name": "Ofe Onugbu (Bitter Leaf Soup) with Pounded Yam",
            "description": (
                "Classic Igbo bitter leaf soup with stockfish and ponmo, "
                "paired with smooth pounded yam."
            ),
            "category": "main",
            "ingredients": [
                {"ingredient_id": "stockfish", "quantity_g": 100.0, "is_primary": True},
                {"ingredient_id": "ponmo",     "quantity_g": 100.0, "is_primary": False},
                {"ingredient_id": "crayfish",  "quantity_g":  20.0, "is_primary": False},
                {"ingredient_id": "palm_oil",  "quantity_g":  60.0, "is_primary": False},
                {"ingredient_id": "ata_rodo",  "quantity_g":  30.0, "is_primary": False},
                {"ingredient_id": "onion",     "quantity_g":  40.0, "is_primary": False},
            ],
            "prep_time_minutes": 60,
            "selling_price_ngn": 4000.0,
        },
    ],
}

# ─── Restaurant Preset 2: Savannah Grill – Wuse II, Abuja ────────────────────

_PRESET_SAVANNAH_GRILL: dict = {
    "id": "savannah_grill",
    "name": "Savannah Grill – Wuse II, Abuja",
    "city": "Wuse, Abuja",
    "nearest_market": "Abuja - Wuse",
    "pantry": {
        "soya_chunks":        300.0,
        "smoked_tofu_wara":   200.0,
        "iru":                150.0,
        "ata_rodo":           400.0,
        "onion":              600.0,
        "palm_oil":          1500.0,
        "smoked_paprika":     300.0,
        "tomatoes":           400.0,
        "parboiled_rice":    2000.0,
        "black_eyed_peas":    300.0,
        "mushroom_bouillon":  150.0,
        "egusi_seeds":        500.0,
        "ugu_leaves":         300.0,
    },
    "menu": [
        {
            "id": "asun_peppered_beef",
            "name": "Asun Peppered Beef Platter",
            "description": (
                "Smoky, spicy peppered goat meat with charred ata rodo and onions "
                "– a Naija party classic."
            ),
            "category": "main",
            "ingredients": [
                {"ingredient_id": "goat_meat",    "quantity_g": 300.0, "is_primary": True},
                {"ingredient_id": "ata_rodo",     "quantity_g":  50.0, "is_primary": False},
                {"ingredient_id": "onion",        "quantity_g":  60.0, "is_primary": False},
                {"ingredient_id": "palm_oil",     "quantity_g":  30.0, "is_primary": False},
                {"ingredient_id": "smoked_paprika","quantity_g": 10.0, "is_primary": False},
            ],
            "prep_time_minutes": 50,
            "selling_price_ngn": 5500.0,
        },
        {
            "id": "jollof_fried_beef",
            "name": "Jollof Rice with Fried Beef",
            "description": (
                "Classic party jollof rice with a generous portion of crispy fried beef."
            ),
            "category": "main",
            "ingredients": [
                {"ingredient_id": "beef",          "quantity_g": 200.0, "is_primary": True},
                {"ingredient_id": "parboiled_rice","quantity_g": 200.0, "is_primary": False},
                {"ingredient_id": "tomatoes",      "quantity_g": 100.0, "is_primary": False},
                {"ingredient_id": "onion",         "quantity_g":  70.0, "is_primary": False},
                {"ingredient_id": "palm_oil",      "quantity_g":  40.0, "is_primary": False},
                {"ingredient_id": "ata_rodo",      "quantity_g":  30.0, "is_primary": False},
            ],
            "prep_time_minutes": 40,
            "selling_price_ngn": 4500.0,
        },
    ],
}

RESTAURANT_PRESETS: dict[str, dict] = {
    "mama_put_express": _PRESET_MAMA_PUT,
    "savannah_grill": _PRESET_SAVANNAH_GRILL,
}


# ─── In-Memory Application State ─────────────────────────────────────────────

class AppState:
    """Central in-memory store for all application runtime data."""

    def __init__(self) -> None:
        self.ingredients: dict[str, Ingredient] = {}
        self.restaurants: dict[str, Restaurant] = {}
        self.transformations: dict[str, StoredTransformation] = {}
        self.approved_alternatives: dict[str, ApprovedAlternative] = {}   # dish_id → alt
        self.orders: list[Order] = []

    # ── Seed ─────────────────────────────────────────────────────────────────

    def seed_ingredients(self) -> None:
        """Load all ingredients. Idempotent — safe to call multiple times."""
        if self.ingredients:
            return
        for data in INGREDIENT_CATALOG:
            ing = Ingredient(**data)
            self.ingredients[ing.id] = ing

    # ── Lookups ───────────────────────────────────────────────────────────────

    def get_ingredient(self, ingredient_id: str) -> Optional[Ingredient]:
        return self.ingredients.get(ingredient_id)

    def get_restaurant(self, restaurant_id: str) -> Optional[Restaurant]:
        return self.restaurants.get(restaurant_id)

    def get_dish(self, restaurant_id: str, dish_id: str) -> Optional[MenuDish]:
        restaurant = self.get_restaurant(restaurant_id)
        if not restaurant:
            return None
        return next((d for d in restaurant.menu if d.id == dish_id), None)

    def get_transformation(self, transformation_id: str) -> Optional[StoredTransformation]:
        return self.transformations.get(transformation_id)

    def get_approved_alternative(self, dish_id: str) -> Optional[ApprovedAlternative]:
        return self.approved_alternatives.get(dish_id)


# Global singleton — imported by main.py, optimizer.py, llm_service.py
app_state = AppState()


# ─── Startup Helper ───────────────────────────────────────────────────────────

def initialize_state() -> None:
    """Called once at application startup (FastAPI lifespan)."""
    app_state.seed_ingredients()
    print(
        f"[NaijaFork] Ingredient catalog: {len(app_state.ingredients)} ingredients seeded.\n"
        f"[NaijaFork] Presets available: {list(RESTAURANT_PRESETS.keys())}"
    )


def build_restaurant_from_preset(preset_id: str) -> Restaurant:
    """Construct a Restaurant object from a named preset dictionary."""
    if preset_id not in RESTAURANT_PRESETS:
        raise ValueError(
            f"Preset '{preset_id}' not found. Available: {list(RESTAURANT_PRESETS.keys())}"
        )
    data = RESTAURANT_PRESETS[preset_id]
    menu_dishes = [
        MenuDish(
            id=d["id"],
            name=d["name"],
            description=d["description"],
            category=d.get("category", "main"),
            ingredients=[DishIngredient(**ing) for ing in d["ingredients"]],
            prep_time_minutes=d["prep_time_minutes"],
            selling_price_ngn=d["selling_price_ngn"],
        )
        for d in data["menu"]
    ]
    return Restaurant(
        id=data["id"],
        name=data["name"],
        city=data["city"],
        nearest_market=data["nearest_market"],
        pantry=data["pantry"],
        menu=menu_dishes,
    )
