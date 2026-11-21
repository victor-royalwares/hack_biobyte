"""
End-to-end console simulation for Route 1 -> approval -> Route 2.

Run from this directory:
    python demo_runner.py
"""

from __future__ import annotations

import asyncio

import models
from database import app_state, build_restaurant_from_preset, initialize_state
from llm_service import get_culinary_translation
from optimizer import optimize_dish


def print_options(label: str, options: list[models.TransformationOption]) -> None:
    print(f"\n{label}")
    if not options:
        print("  No compliant options found.")
        return
    for index, option in enumerate(options, 1):
        print(
            f"  {index}. {option.dish_name or option.tier} "
            f"| Score {option.composite_score:.3f}"
        )
        print(
            f"     Cost: {option.financials.original_ingredient_cost_ngn:.2f} -> "
            f"{option.financials.new_ingredient_cost_ngn:.2f} NGN "
            f"(save {option.financials.cost_savings_ngn:.2f}, "
            f"{option.financials.cost_savings_pct:.1f}%)"
        )
        print(
            f"     Protein: {option.nutrition.protein_original_g:.2f}g -> "
            f"{option.nutrition.protein_new_g:.2f}g | "
            f"Sat fat reduction: {option.nutrition.saturated_fat_reduction_pct:.1f}% | "
            f"Fiber gain: {option.nutrition.fiber_gain_g:.2f}g"
        )
        print("     Swaps:")
        for swap in option.swaps:
            print(
                f"       {swap.original_ingredient_name} "
                f"-> {swap.replacement_ingredient_name} "
                f"({swap.replacement_quantity_g:.0f}g)"
            )


async def main() -> None:
    initialize_state()
    restaurant = build_restaurant_from_preset("mama_put_express")
    app_state.restaurants[restaurant.id] = restaurant

    dish = next(
        dish for dish in restaurant.menu
        if dish.id == "beef_egusi_eba"
    )
    print("Naija Fork - End-to-End Demo")
    print("=" * 50)
    print(f"Restaurant: {restaurant.name}")
    print(f"Market: {restaurant.nearest_market}")
    print(f"Dish: {dish.name}")

    constraints = models.TransformationConstraints(
        min_familiarity_score=6,
        max_prep_complexity="medium",
        optimization_priority="balanced",
    )
    tier_a, tier_b = optimize_dish(
        dish,
        restaurant,
        constraints,
        app_state.ingredients,
    )

    for option in tier_a + tier_b:
        translation = await get_culinary_translation(
            dish,
            option,
            app_state.ingredients,
        )
        option.dish_name = translation.dish_name
        option.dish_description = translation.dish_description
        option.kitchen_prep_instructions = translation.kitchen_prep_instructions
        option.menu_copy = translation.menu_copy
        option.constraint_satisfaction_proof = translation.constraint_satisfaction_proof

    print_options("Tier A - In-Store Ready", tier_a)
    print_options("Tier B - Local Geo-Market", tier_b)

    top = tier_a[0] if tier_a else (tier_b[0] if tier_b else None)
    if top is None:
        raise RuntimeError("No compliant transformation was produced")

    import uuid

    transformation = models.StoredTransformation(
        id=str(uuid.uuid4()),
        restaurant_id=restaurant.id,
        dish_id=dish.id,
        dish_name=dish.name,
        constraints=constraints,
        in_store_options=tier_a,
        local_market_options=tier_b,
    )
    app_state.transformations[transformation.id] = transformation

    raw_savings = top.financials.cost_savings_ngn
    customer_savings = raw_savings * 0.50
    discounted_price = dish.selling_price_ngn - customer_savings
    restaurant_margin = raw_savings - customer_savings
    transformation.status = "approved"
    transformation.approved_option_id = top.id
    transformation.restaurant_discount_pct = 50.0

    app_state.approved_alternatives[dish.id] = models.ApprovedAlternative(
        transformation_id=transformation.id,
        option_id=top.id,
        dish_id=dish.id,
        restaurant_id=restaurant.id,
        option=top,
        original_dish_name=dish.name,
        original_price_ngn=dish.selling_price_ngn,
        discounted_alternative_price_ngn=round(discounted_price, 2),
        customer_savings_ngn=round(customer_savings, 2),
        restaurant_margin_gain_ngn=round(restaurant_margin, 2),
    )

    print("\nManager Approval")
    print(f"  Approved: {top.dish_name}")
    print(f"  Customer discount share: 50%")
    print(f"  Customer price: ₦{dish.selling_price_ngn:.0f} -> ₦{discounted_price:.0f}")
    print(f"  Customer savings: ₦{customer_savings:.2f}")

    alternative = app_state.approved_alternatives[dish.id]
    print("\nCustomer Smart-Swap Nudge")
    print(f"  {alternative.option.dish_name}")
    print(f"  {alternative.option.dish_description}")
    print(
        f"  Save ₦{alternative.customer_savings_ngn:.0f} | "
        f"{top.nutrition.protein_new_g:.1f}g Protein | "
        f"{top.nutrition.saturated_fat_reduction_pct:.1f}% less saturated fat"
    )

    order = models.Order(
        restaurant_id=restaurant.id,
        dish_id=dish.id,
        choice="approved_alternative",
        original_price_ngn=dish.selling_price_ngn,
        paid_price_ngn=discounted_price,
        customer_savings_ngn=customer_savings,
        restaurant_margin_gain_ngn=restaurant_margin,
        saturated_fat_avoided_g=(
            top.nutrition.saturated_fat_original_g
            - top.nutrition.saturated_fat_new_g
        ),
        carbon_footprint_reduced_kg=(
            sum(
                swap.original_quantity_g / 100.0 * 2.5
                for swap in top.swaps
                if swap.original_ingredient_id
                in {"beef", "goat_meat", "chicken", "stockfish", "fish", "ponmo"}
            )
        ),
    )
    app_state.orders.append(order)

    orders = [
        item for item in app_state.orders
        if item.restaurant_id == restaurant.id
    ]
    alternative_orders = sum(
        item.choice == "approved_alternative" for item in orders
    )
    print("\nUpdated Analytics")
    print(f"  Total orders: {len(orders)}")
    print(f"  Alternative orders: {alternative_orders}")
    print(
        f"  Conversion rate: "
        f"{(alternative_orders / len(orders) * 100.0):.1f}%"
    )
    print(
        f"  Customer savings: "
        f"₦{sum(item.customer_savings_ngn for item in orders):.2f}"
    )
    print(
        f"  Restaurant margin: "
        f"₦{sum(item.restaurant_margin_gain_ngn for item in orders):.2f}"
    )
    print(
        f"  Saturated fat avoided: "
        f"{sum(item.saturated_fat_avoided_g for item in orders):.2f}g"
    )


if __name__ == "__main__":
    asyncio.run(main())
