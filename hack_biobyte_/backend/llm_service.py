"""
llm_service.py — Grounded Culinary & Business LLM Translator.

STRICT GROUNDING RULES:
  1. The LLM receives deterministic optimizer output (₦ figures, protein grams, etc.)
     as READ-ONLY context. It may reference these values in prose but MUST NOT invent
     or alter any numbers.
  2. The LLM's job is exclusively textual: dish names, culinary descriptions,
     kitchen instructions, customer-facing menu copy, constraint proof.
  3. If no API key is configured — or if any LLM call fails — the system falls back
     to a rich deterministic template that produces professional, varied output
     without any external dependency.

Provider selection (via .env):
  LLM_PROVIDER=auto    → OpenAI if key present, else Gemini, else template
  LLM_PROVIDER=openai  → OpenAI only (falls back to template on error)
  LLM_PROVIDER=gemini  → Gemini only (falls back to template on error)
  LLM_PROVIDER=none    → Always use deterministic template
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from dotenv import load_dotenv
from pydantic import BaseModel

from models import Ingredient, MenuDish, TransformationOption

load_dotenv()

logger = logging.getLogger(__name__)

_OPENAI_KEY  = os.getenv("OPENAI_API_KEY", "")
_GEMINI_KEY  = os.getenv("GEMINI_API_KEY", "")
_LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").lower()


# ─── Output Schema (LLM-generated text only) ─────────────────────────────────

class CulinaryTranslation(BaseModel):
    """Strictly text fields — no numbers allowed from the LLM."""
    dish_name: str
    dish_description: str
    kitchen_prep_instructions: str
    menu_copy: str
    constraint_satisfaction_proof: str


# ─── Provider Resolution ──────────────────────────────────────────────────────

def _active_provider() -> str:
    if _LLM_PROVIDER == "none":
        return "none"
    if _LLM_PROVIDER == "openai":
        return "openai" if _OPENAI_KEY else "none"
    if _LLM_PROVIDER == "gemini":
        return "gemini" if _GEMINI_KEY else "none"
    # auto
    if _OPENAI_KEY:
        return "openai"
    if _GEMINI_KEY:
        return "gemini"
    return "none"


# ─── Prompt Builder ───────────────────────────────────────────────────────────

def _build_prompt(
    original_dish: MenuDish,
    option: TransformationOption,
    all_ingredients: dict[str, Ingredient],
) -> str:
    orig_lines = []
    for di in original_dish.ingredients:
        ing = all_ingredients.get(di.ingredient_id)
        if ing:
            orig_lines.append(f"  - {ing.name} ({di.quantity_g:.0f} g)")

    swap_lines = []
    for s in option.swaps:
        local = f" [{s.replacement_local_name}]" if s.replacement_local_name else ""
        swap_lines.append(
            f"  - REPLACE {s.original_ingredient_name} ({s.original_quantity_g:.0f} g)"
            f" → {s.replacement_ingredient_name}{local} ({s.replacement_quantity_g:.0f} g)"
        )

    umami_names = [
        (s.replacement_local_name or s.replacement_ingredient_name)
        for s in option.swaps
        if s.replacement_ingredient_id in {"iru", "ogiri", "mushroom_bouillon", "dried_oyster_mushroom"}
    ]
    umami_text = ", ".join(umami_names) if umami_names else "our signature fermented spice blend"

    fin = option.financials
    nut = option.nutrition

    return f"""You are a Nigerian culinary expert and restaurant marketing specialist for Naija Fork,
a constraint-aware menu transformation platform for Nigerian restaurants.

A restaurant is replacing animal-derived ingredients with 100 % plant-based Nigerian alternatives.

ORIGINAL DISH: {original_dish.name}
ORIGINAL INGREDIENTS:
{chr(10).join(orig_lines)}

APPROVED PLANT-BASED SWAPS (from our Python optimization engine):
{chr(10).join(swap_lines)}

Plant-based umami achieved via: {umami_text}

VERIFIED OUTCOMES — READ ONLY. DO NOT INVENT OR MODIFY THESE FIGURES:
  Ingredient cost savings  : ₦{fin.cost_savings_ngn:,.0f}  ({fin.cost_savings_pct:.1f} % reduction)
  Protein                  : {nut.protein_original_g:.1f} g → {nut.protein_new_g:.1f} g
  Saturated fat reduction  : {nut.saturated_fat_reduction_pct:.1f} %
  Fiber gain               : +{nut.fiber_gain_g:.1f} g
  Sourcing tier            : {"Pantry-ready (zero procurement)" if option.tier == "A_in_store" else "Available from nearest local market"}

RULES FOR YOUR RESPONSE:
1. NEVER use the words "vegan" or "vegetarian" — focus on flavour, texture, and satisfaction.
2. Celebrate the local Nigerian ingredient names (Iru, Ogiri, Wara, Olu, Fio-Fio, Eba, etc.).
3. The dish must sound APPETIZING to mainstream Nigerian diners — emphasise smokiness,
   deep umami, satisfying chew, and bold pepper heat.
4. Kitchen instructions must be practical for a standard Nigerian restaurant kitchen
   (heavy-bottomed pot, wooden spoon, gas burner). No specialist equipment.
5. Reference verified numbers ONLY in prose form — e.g. "significant cost savings",
   "matches or exceeds the protein of the original", "lower in saturated fat".
   Do NOT write specific Naira amounts or gram figures that contradict the verified outcomes.

Return ONLY a valid JSON object (no markdown fences) with these exact keys:
{{
  "dish_name": "Appetizing plant-based name (5 words max, NO vegan/vegetarian labels)",
  "dish_description": "2-sentence description — celebrate the flavour and local ingredients",
  "kitchen_prep_instructions": "Numbered step-by-step preparation (6-9 steps) for a restaurant kitchen",
  "menu_copy": "1-2 punchy sentences of customer-facing menu copy (flavour first, health benefit second)",
  "constraint_satisfaction_proof": "2-3 sentences explaining how this swap meets cost, nutrition, and culinary constraints"
}}"""


# ─── OpenAI Implementation ────────────────────────────────────────────────────

async def _call_openai(
    original_dish: MenuDish,
    option: TransformationOption,
    all_ingredients: dict[str, Ingredient],
) -> CulinaryTranslation:
    try:
        from openai import AsyncOpenAI  # lazy import — not required if unused

        client = AsyncOpenAI(api_key=_OPENAI_KEY)
        prompt = _build_prompt(original_dish, option, all_ingredients)

        response = await client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a Nigerian culinary expert. "
                        "Return ONLY valid JSON — no markdown, no extra text."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format=CulinaryTranslation,
        )
        result = response.choices[0].message.parsed
        if result is None:
            raise ValueError("OpenAI returned null parsed result")
        return result

    except Exception as exc:
        logger.warning("OpenAI call failed (%s). Using deterministic fallback.", exc)
        return _deterministic_fallback(original_dish, option, all_ingredients)


# ─── Gemini Implementation ────────────────────────────────────────────────────

async def _call_gemini(
    original_dish: MenuDish,
    option: TransformationOption,
    all_ingredients: dict[str, Ingredient],
) -> CulinaryTranslation:
    try:
        import google.generativeai as genai  # lazy import

        genai.configure(api_key=_GEMINI_KEY)
        model = genai.GenerativeModel(
            "gemini-1.5-flash",
            generation_config={"response_mime_type": "application/json"},
        )
        prompt = _build_prompt(original_dish, option, all_ingredients)

        # Gemini SDK is synchronous — run in thread to avoid blocking the event loop
        response = await asyncio.to_thread(model.generate_content, prompt)
        data = json.loads(response.text)
        return CulinaryTranslation(**data)

    except Exception as exc:
        logger.warning("Gemini call failed (%s). Using deterministic fallback.", exc)
        return _deterministic_fallback(original_dish, option, all_ingredients)


# ─── Deterministic Fallback ───────────────────────────────────────────────────

_PREP_TEMPLATES: dict[str, list[str]] = {
    "soya_chunks": [
        "1. Rehydrate Textured Soya Chunks in boiling water for 15 minutes. Drain and squeeze dry.",
        "2. Season generously with salt, ground pepper, and smoked paprika. Toss to coat.",
        "3. Sear seasoned chunks in a dry cast-iron pan over high heat for 3-4 minutes until "
           "the edges caramelise and char slightly. Set aside.",
    ],
    "oyster_mushrooms": [
        "1. Clean fresh Oyster Mushrooms (Olu Olu) and tear into large, meaty strips.",
        "2. Season with salt, smoked paprika, and a pinch of ground crayfish-free seasoning.",
        "3. Sear mushrooms in a very hot pan — no oil — for 3-5 minutes until golden and "
           "slightly chewy. Set aside.",
    ],
    "smoked_tofu_wara": [
        "1. Slice Smoked Wara (local tofu) into thick cubes. Pat dry with a cloth.",
        "2. Marinate in blended ata rodo and onion mix for 10 minutes.",
        "3. Pan-fry Wara cubes in a little palm oil until golden-brown on all sides, "
           "about 4 minutes per side. Set aside.",
    ],
    "black_eyed_peas": [
        "1. If using dry black-eyed peas (Ewa), soak overnight and boil until just tender — "
           "not mushy. Drain.",
        "2. Season with salt, ground pepper, and smoked paprika.",
        "3. Briefly stir-fry in a little palm oil with sliced onions until lightly browned. Set aside.",
    ],
    "pigeon_pea": [
        "1. Soak pigeon peas (Fio-Fio) for 4 hours. Boil until tender, about 45 minutes. Drain.",
        "2. Season with salt and ata rodo paste.",
        "3. Stir-fry briefly in palm oil with onion for depth of flavour. Set aside.",
    ],
    "default_protein": [
        "1. Prepare the plant-based protein according to its standard method "
           "(soak, boil, or sear as appropriate).",
        "2. Season generously with Nigerian spices — ata rodo, onion, salt, and smoked paprika.",
        "3. Cook until fully flavoured and slightly caramelised on the outside. Set aside.",
    ],
}

_UMAMI_BLOOM = (
    "4. UMAMI STEP (replaces crayfish): Bloom {umami} in a small measure of hot palm oil "
    "for 60-90 seconds until fragrant — this activates the deep fermented umami that gives "
    "the soup its backbone."
)

_SHARED_STEPS = [
    "5. In a heavy pot, fry your blended tomato-pepper-onion mix (ata rodo, fresh tomatoes, onion) "
       "in palm oil over medium-high heat. Stir constantly until the oil floats to the surface "
       "and the raw smell disappears — about 10-12 minutes.",
    "6. Add your protein (from Step 3) and the bloomed umami seasoning. Stir to coat.",
    "7. Add egusi (if using) or any additional thickener. Fry dry for 3-4 minutes.",
    "8. Pour in enough hot water or vegetable stock to reach your desired soup consistency. "
       "Cover and simmer on low heat for 10 minutes.",
    "9. Stir in washed leafy greens (Ugu or Uziza). Simmer uncovered for 5 minutes "
       "— do not overcook the greens.",
    "10. Taste and adjust seasoning. Serve immediately with freshly moulded Eba or your chosen swallow.",
]


def _deterministic_fallback(
    original_dish: MenuDish,
    option: TransformationOption,
    all_ingredients: dict[str, Ingredient],
) -> CulinaryTranslation:
    """
    Generate professional culinary content without any LLM.
    Output varies based on ingredient combination and tier.
    """
    # ── Identify key ingredients ─────────────────────────────────────────────
    protein_swaps = [
        s for s in option.swaps
        if s.replacement_ingredient_id not in {
            "iru", "ogiri", "mushroom_bouillon", "dried_oyster_mushroom"
        }
    ]
    umami_swaps = [
        s for s in option.swaps
        if s.replacement_ingredient_id in {
            "iru", "ogiri", "mushroom_bouillon", "dried_oyster_mushroom"
        }
    ]

    primary_protein_id = protein_swaps[0].replacement_ingredient_id if protein_swaps else "default_protein"
    primary_protein_name = (
        (protein_swaps[0].replacement_local_name or protein_swaps[0].replacement_ingredient_name)
        if protein_swaps else "Plant-Based Protein"
    )

    umami_display = " and ".join(
        s.replacement_local_name or s.replacement_ingredient_name
        for s in umami_swaps
    ) if umami_swaps else "our fermented spice blend"

    # ── Dish Name ────────────────────────────────────────────────────────────
    # Replace the animal word in the original name with the plant-based protein
    animal_words = ["Beef", "Goat", "Chicken", "Fish", "Asun", "Stockfish", "Ponmo"]
    new_dish_name = original_dish.name
    for word in animal_words:
        if word in new_dish_name:
            new_dish_name = new_dish_name.replace(word, primary_protein_name.split()[0], 1)
            break

    # ── Dish Description ─────────────────────────────────────────────────────
    tier_note = (
        "crafted entirely from your existing pantry stock"
        if option.tier == "A_in_store"
        else "sourced fresh from your local market"
    )
    dish_description = (
        f"A bold, satisfying take on our beloved {original_dish.name.split(' with ')[0]}, "
        f"{tier_note} — built on {primary_protein_name} and deepened with the earthy, "
        f"fermented funk of {umami_display}. "
        f"Every mouthful delivers the same smoky, peppery Nigerian flavour you know, "
        f"with a lighter, cleaner finish."
    )

    # ── Kitchen Prep Instructions ─────────────────────────────────────────────
    protein_steps = _PREP_TEMPLATES.get(primary_protein_id, _PREP_TEMPLATES["default_protein"])
    umami_step = _UMAMI_BLOOM.format(umami=umami_display) if umami_swaps else (
        "4. Add mushroom bouillon or extra smoked paprika for depth of savour."
    )
    all_steps = protein_steps + [umami_step] + _SHARED_STEPS
    kitchen_prep_instructions = "\n".join(all_steps)

    # ── Menu Copy ────────────────────────────────────────────────────────────
    menu_copy = (
        f"All the fire, chew, and depth of our classic {original_dish.name.split(' with ')[0]} "
        f"— now built on {primary_protein_name} and the age-old funk of {umami_display}. "
        f"{'Higher protein, ' if option.nutrition.protein_new_g >= option.nutrition.protein_original_g else 'Protein-conscious, '} "
        f"lower cost, and full of Nigerian flavour."
    )

    # ── Constraint Satisfaction Proof ────────────────────────────────────────
    source_detail = (
        "drawn entirely from your current pantry — zero procurement cost or delay"
        if option.tier == "A_in_store"
        else "all readily available at your nearest local wholesale market"
    )
    protein_proof = (
        f"Protein content is higher than the original."
        if option.nutrition.protein_new_g > option.nutrition.protein_original_g
        else (
            f"Protein content remains close to the original."
            if option.nutrition.protein_retention_pct >= 90.0
            else f"The plant-based combination provides a fibre-forward protein profile."
        )
    )
    constraint_satisfaction_proof = (
        f"This transformation eliminates every animal-derived ingredient and replaces them with "
        f"100 % plant-based Nigerian alternatives, {source_detail}. "
        f"The swap delivers significant ingredient cost savings per dish, directly improving "
        f"your profit margin at the same menu price. "
        f"{protein_proof} Saturated fat is substantially reduced. "
        f"Traditional umami depth (previously provided by crayfish) is fully replicated by "
        f"{umami_display}, a flavour foundation used across millions of Nigerian kitchens and "
        f"immediately familiar to your diners."
    )

    return CulinaryTranslation(
        dish_name=new_dish_name,
        dish_description=dish_description,
        kitchen_prep_instructions=kitchen_prep_instructions,
        menu_copy=menu_copy,
        constraint_satisfaction_proof=constraint_satisfaction_proof,
    )


# ─── Public API ───────────────────────────────────────────────────────────────

async def get_culinary_translation(
    original_dish: MenuDish,
    option: TransformationOption,
    all_ingredients: dict[str, Ingredient],
) -> CulinaryTranslation:
    """
    Enrich a TransformationOption with LLM-generated culinary text.
    Routes to OpenAI, Gemini, or deterministic fallback based on environment config.
    All numerical fields in `option` are locked — only text fields are produced here.
    """
    provider = _active_provider()
    logger.debug("LLM provider resolved: %s", provider)

    if provider == "openai":
        return await _call_openai(original_dish, option, all_ingredients)
    if provider == "gemini":
        return await _call_gemini(original_dish, option, all_ingredients)
    return _deterministic_fallback(original_dish, option, all_ingredients)
