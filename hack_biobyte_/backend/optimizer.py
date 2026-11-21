"""
optimizer.py — Deterministic multi-criteria scoring & constraint-filtering engine.

CRITICAL DESIGN RULE:
  All Naira (₦) figures, protein grams, fat percentages, and fiber values produced
  here are computed entirely in Python. The LLM layer (llm_service.py) is NEVER
  allowed to modify or invent any of these numbers.

Tier A (In-Store Ready):
  Every replacement ingredient exists in the restaurant's current pantry
  with sufficient quantity — zero new procurement required.

Tier B (Local Geo-Market Sourcing):
  Every replacement ingredient is available at the restaurant's nearest
  wholesale market; a brief procurement run is needed.
"""

from __future__ import annotations

import itertools
from typing import Optional

from models import (
    DishIngredient,
    FinancialDelta,
    Ingredient,
    IngredientSwap,
    MenuDish,
    NutritionDelta,
    OptimizationPriority,
    PrepComplexity,
    Restaurant,
    TransformationConstraints,
    TransformationOption,
)


# ─── Scoring Weight Profiles ───────────────────────────────────────────────────

WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    "balanced": {
        "cost": 0.30, "protein": 0.25, "texture": 0.20,
        "familiarity": 0.15, "umami": 0.10,
    },
    "lowest_cost": {
        "cost": 0.60, "protein": 0.15, "texture": 0.10,
        "familiarity": 0.10, "umami": 0.05,
    },
    "closest_texture": {
        "cost": 0.20, "protein": 0.15, "texture": 0.50,
        "familiarity": 0.10, "umami": 0.05,
    },
    "highest_protein": {
        "cost": 0.20, "protein": 0.50, "texture": 0.15,
        "familiarity": 0.10, "umami": 0.05,
    },
}

# Replacement quantity ratio by the original ingredient's category.
# Fermented umami concentrates (Iru, Ogiri) are more potent than crayfish
# by weight, so we use 75 % of the original quantity.
REPLACEMENT_RATIOS: dict[str, float] = {
    "umami": 0.75,
    "protein": 1.00,
    "default": 1.00,
}

# Maximum candidates considered per animal ingredient (keeps combinations bounded)
MAX_CANDIDATES_PER_INGREDIENT = 5

# Maximum options returned per tier in the final response
MAX_OPTIONS_PER_TIER = 3


# ─── Helper Math Functions ─────────────────────────────────────────────────────

def _prep_rank(c: PrepComplexity) -> int:
    return {"low": 1, "medium": 2, "high": 3}[c]


def _jaccard(tags_a: list[str], tags_b: list[str]) -> float:
    """Jaccard similarity between two texture tag sets."""
    set_a, set_b = set(tags_a), set(tags_b)
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    return len(set_a & set_b) / len(union) if union else 0.0


def _cost(ing: Ingredient, qty_g: float) -> float:
    return (qty_g / 100.0) * ing.cost_per_100g_ngn


def _protein(ing: Ingredient, qty_g: float) -> float:
    return (qty_g / 100.0) * ing.protein_g_per_100g


def _sat_fat(ing: Ingredient, qty_g: float) -> float:
    return (qty_g / 100.0) * ing.saturated_fat_g_per_100g


def _fiber(ing: Ingredient, qty_g: float) -> float:
    return (qty_g / 100.0) * ing.fiber_g_per_100g


def _calories(ing: Ingredient, qty_g: float) -> float:
    return (qty_g / 100.0) * ing.calories_per_100g


# ─── Candidate Finder ─────────────────────────────────────────────────────────

def find_plant_based_candidates(
    target: Ingredient,
    all_ingredients: dict[str, Ingredient],
    constraints: TransformationConstraints,
) -> list[Ingredient]:
    """
    Return plant-based candidate replacements for `target` (a non-plant-based ingredient).
    Filtered by: same category (or cross-category exception for high-umami mushrooms),
    min_familiarity_score, and max_prep_complexity.
    Sorted by familiarity (desc) then cost (asc). Top MAX_CANDIDATES_PER_INGREDIENT returned.
    """
    max_prep = _prep_rank(constraints.max_prep_complexity)
    candidates: list[Ingredient] = []

    for ing in all_ingredients.values():
        if not ing.is_plant_based:
            continue
        # Category match — with one cross-category exception:
        # oyster/dried oyster mushrooms (category=protein) qualify as umami subs
        # because their umami_score >= 8 makes them functionally equivalent to crayfish.
        if ing.category != target.category:
            is_umami_mushroom = (
                target.category == "umami"
                and ing.id in {"oyster_mushrooms", "dried_oyster_mushroom"}
            )
            if not is_umami_mushroom:
                continue
        # Familiarity hard constraint
        if ing.familiarity_score < constraints.min_familiarity_score:
            continue
        # Prep complexity hard constraint
        if _prep_rank(ing.prep_complexity) > max_prep:
            continue

        candidates.append(ing)

    # Sort: familiarity desc, then cost asc (cheapest is best when equal familiarity)
    candidates.sort(key=lambda x: (-x.familiarity_score, x.cost_per_100g_ngn))
    return candidates[:MAX_CANDIDATES_PER_INGREDIENT]


# ─── Dish Metric Calculator ────────────────────────────────────────────────────

def _dish_metrics(
    dish_ingredients: list[DishIngredient],
    all_ingredients: dict[str, Ingredient],
    swap_map: dict[str, tuple[Ingredient, float]],  # original_id → (replacement, qty_g)
) -> tuple[float, float, float, float, float]:
    """
    Compute (total_cost, protein, sat_fat, fiber, calories) for a dish.
    `swap_map` applies replacements; non-swapped ingredients are computed as-is.
    Missing ingredient IDs are silently skipped (robustness).
    """
    cost = protein = sat_fat = fiber = cals = 0.0

    for di in dish_ingredients:
        if di.ingredient_id in swap_map:
            repl_ing, repl_qty = swap_map[di.ingredient_id]
            cost    += _cost(repl_ing, repl_qty)
            protein += _protein(repl_ing, repl_qty)
            sat_fat += _sat_fat(repl_ing, repl_qty)
            fiber   += _fiber(repl_ing, repl_qty)
            cals    += _calories(repl_ing, repl_qty)
        else:
            ing = all_ingredients.get(di.ingredient_id)
            if ing is None:
                continue
            cost    += _cost(ing, di.quantity_g)
            protein += _protein(ing, di.quantity_g)
            sat_fat += _sat_fat(ing, di.quantity_g)
            fiber   += _fiber(ing, di.quantity_g)
            cals    += _calories(ing, di.quantity_g)

    return cost, protein, sat_fat, fiber, cals


# ─── Composite Scorer ─────────────────────────────────────────────────────────

def _score(
    orig_cost: float,
    new_cost: float,
    orig_protein: float,
    new_protein: float,
    animal_ings: list[tuple[Ingredient, float]],   # (original, qty_g)
    swap_map: dict[str, tuple[Ingredient, float]],  # original_id → (replacement, qty_g)
    priority: OptimizationPriority,
) -> float:
    """
    Compute a composite [0, 1] score for a swap combination using the
    weight profile matching `priority`.
    """
    weights = WEIGHT_PROFILES[priority]

    # ── Cost score (higher savings → higher score) ──────────────────────────
    cost_score = (
        min(1.0, max(0.0, (orig_cost - new_cost) / orig_cost))
        if orig_cost > 0 else 0.5
    )

    # ── Protein score (capped at 1.0 — having MORE protein is not penalised) ─
    protein_score = (
        min(1.0, new_protein / orig_protein)
        if orig_protein > 0 else 1.0
    )

    # ── Per-swap texture, familiarity, umami ───────────────────────────────
    texture_scores: list[float] = []
    familiarity_scores: list[float] = []
    umami_scores: list[float] = []

    for orig_ing, _orig_qty in animal_ings:
        if orig_ing.id not in swap_map:
            continue
        repl_ing, _repl_qty = swap_map[orig_ing.id]

        texture_scores.append(_jaccard(orig_ing.texture_tags, repl_ing.texture_tags))
        familiarity_scores.append(repl_ing.familiarity_score / 10.0)

        # Umami: for umami-category originals, check how well the replacement preserves it.
        # For protein-category originals, reward any additional umami the replacement brings.
        if orig_ing.category == "umami":
            umami_scores.append(
                min(1.0, repl_ing.umami_score / orig_ing.umami_score)
                if orig_ing.umami_score > 0 else 1.0
            )
        else:
            # Reward richer umami from the protein replacement (normalized)
            umami_scores.append(repl_ing.umami_score / 10.0)

    texture_score    = sum(texture_scores)    / len(texture_scores)    if texture_scores    else 0.0
    familiarity_score = sum(familiarity_scores) / len(familiarity_scores) if familiarity_scores else 0.5
    umami_score      = sum(umami_scores)      / len(umami_scores)      if umami_scores      else 1.0

    return (
        weights["cost"]        * cost_score
        + weights["protein"]   * protein_score
        + weights["texture"]   * texture_score
        + weights["familiarity"] * familiarity_score
        + weights["umami"]     * umami_score
    )


# ─── Main Optimization Entry Point ────────────────────────────────────────────

def optimize_dish(
    dish: MenuDish,
    restaurant: Restaurant,
    constraints: TransformationConstraints,
    all_ingredients: dict[str, Ingredient],
) -> tuple[list[TransformationOption], list[TransformationOption]]:
    """
    Replace every non-plant-based ingredient in `dish` with the optimal
    plant-based combination(s), then classify and rank results.

    Returns:
        (tier_a_options, tier_b_options)
        — each list sorted by composite_score descending, capped at MAX_OPTIONS_PER_TIER.
    """

    # ── 1. Identify all animal-derived dish ingredients ─────────────────────
    animal_ings: list[tuple[Ingredient, float]] = []   # (Ingredient, quantity_g)
    for di in dish.ingredients:
        ing = all_ingredients.get(di.ingredient_id)
        if ing and not ing.is_plant_based:
            animal_ings.append((ing, di.quantity_g))

    if not animal_ings:
        return [], []   # Nothing to replace

    # ── 2. Original dish totals (baseline for delta calculations) ────────────
    orig_cost, orig_protein, orig_sat_fat, orig_fiber, orig_cals = _dish_metrics(
        dish.ingredients, all_ingredients, {}
    )

    # ── 3. Candidates per animal ingredient ─────────────────────────────────
    candidate_lists: list[list[Ingredient]] = []
    for orig_ing, _qty in animal_ings:
        cands = find_plant_based_candidates(orig_ing, all_ingredients, constraints)
        if not cands:
            # Cannot replace this ingredient under current constraints → abort
            return [], []
        candidate_lists.append(cands)

    # ── 4. Evaluate every combination ───────────────────────────────────────
    tier_a: list[TransformationOption] = []
    tier_b: list[TransformationOption] = []

    for combo in itertools.product(*candidate_lists):
        # Build swap_map and IngredientSwap list
        swap_map: dict[str, tuple[Ingredient, float]] = {}
        swaps: list[IngredientSwap] = []

        for (orig_ing, orig_qty), repl_ing in zip(animal_ings, combo):
            ratio    = REPLACEMENT_RATIOS.get(orig_ing.category, 1.0)
            repl_qty = orig_qty * ratio

            orig_cost_item = _cost(orig_ing, orig_qty)
            repl_cost_item = _cost(repl_ing, repl_qty)
            texture_sim    = _jaccard(orig_ing.texture_tags, repl_ing.texture_tags)

            swap_map[orig_ing.id] = (repl_ing, repl_qty)

            swaps.append(IngredientSwap(
                original_ingredient_id=orig_ing.id,
                original_ingredient_name=orig_ing.name,
                original_quantity_g=orig_qty,
                original_cost_ngn=round(orig_cost_item, 2),
                replacement_ingredient_id=repl_ing.id,
                replacement_ingredient_name=repl_ing.name,
                replacement_local_name=repl_ing.local_name,
                replacement_quantity_g=round(repl_qty, 2),
                replacement_cost_ngn=round(repl_cost_item, 2),
                cost_delta_ngn=round(repl_cost_item - orig_cost_item, 2),
                protein_delta_g=round(
                    _protein(repl_ing, repl_qty) - _protein(orig_ing, orig_qty), 2
                ),
                texture_similarity_score=round(texture_sim, 4),
            ))

        # ── New dish totals ──────────────────────────────────────────────
        new_cost, new_protein, new_sat_fat, new_fiber, new_cals = _dish_metrics(
            dish.ingredients, all_ingredients, swap_map
        )

        # ── Hard constraint filters ──────────────────────────────────────
        if constraints.max_cost_ngn is not None and new_cost > constraints.max_cost_ngn:
            continue
        if constraints.min_protein_g is not None and new_protein < constraints.min_protein_g:
            continue

        # ── Financials (all Python math, never LLM) ──────────────────────
        cost_savings     = orig_cost - new_cost
        cost_savings_pct = (cost_savings / orig_cost * 100.0) if orig_cost > 0 else 0.0

        financials = FinancialDelta(
            original_ingredient_cost_ngn=round(orig_cost, 2),
            new_ingredient_cost_ngn=round(new_cost, 2),
            cost_savings_ngn=round(cost_savings, 2),
            cost_savings_pct=round(cost_savings_pct, 2),
            projected_margin_gain_ngn=round(cost_savings, 2),
        )

        # ── Nutrition (all Python math, never LLM) ───────────────────────
        prot_ret  = (new_protein / orig_protein * 100.0) if orig_protein > 0 else 100.0
        sat_red   = ((orig_sat_fat - new_sat_fat) / orig_sat_fat * 100.0) if orig_sat_fat > 0 else 0.0

        nutrition = NutritionDelta(
            protein_original_g=round(orig_protein, 2),
            protein_new_g=round(new_protein, 2),
            protein_retention_pct=round(prot_ret, 2),
            saturated_fat_original_g=round(orig_sat_fat, 2),
            saturated_fat_new_g=round(new_sat_fat, 2),
            saturated_fat_reduction_pct=round(sat_red, 2),
            fiber_original_g=round(orig_fiber, 2),
            fiber_new_g=round(new_fiber, 2),
            fiber_gain_g=round(new_fiber - orig_fiber, 2),
            calories_original=round(orig_cals, 2),
            calories_new=round(new_cals, 2),
        )

        # ── Composite score ──────────────────────────────────────────────
        composite = _score(
            orig_cost, new_cost, orig_protein, new_protein,
            animal_ings, swap_map,
            constraints.optimization_priority,
        )

        # ── Tier classification ──────────────────────────────────────────
        all_in_pantry = True
        all_at_market = True
        procurement_list: list[str] = []

        for orig_id, (repl_ing, repl_qty) in swap_map.items():
            in_pantry = (
                repl_ing.id in restaurant.pantry
                and restaurant.pantry[repl_ing.id] >= repl_qty
            )
            at_market = restaurant.nearest_market in repl_ing.available_markets

            if not in_pantry:
                all_in_pantry = False
                procurement_list.append(f"{repl_ing.name} ({repl_qty:.0f} g)")
            if not at_market:
                all_at_market = False

        # Drop combinations where at least one replacement can't be sourced
        if not all_in_pantry and not all_at_market:
            continue

        tier = "A_in_store" if all_in_pantry else "B_local_market"

        option = TransformationOption(
            tier=tier,
            swaps=swaps,
            financials=financials,
            nutrition=nutrition,
            composite_score=round(composite, 4),
            requires_market_procurement=not all_in_pantry,
            procurement_list=procurement_list,
        )

        if all_in_pantry:
            tier_a.append(option)
        else:
            tier_b.append(option)

    # ── 5. Sort by composite score (desc) and limit per tier ─────────────────
    tier_a.sort(key=lambda o: o.composite_score, reverse=True)
    tier_b.sort(key=lambda o: o.composite_score, reverse=True)

    return tier_a[:MAX_OPTIONS_PER_TIER], tier_b[:MAX_OPTIONS_PER_TIER]
