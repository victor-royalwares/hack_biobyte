"""
Naija Fork FastAPI application.

Setup:
    python -m pip install -r requirements.txt
    copy .env.example .env  (optional; fallback mode needs no API key)
    python app.py

API docs are available at /docs.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from models import (
    ApprovedAlternative,
    ApproveTransformationRequest,
    ApproveTransformationResponse,
    CustomerMenuResponse,
    MenuDishPublic,
    OnboardingRequest,
    OnboardingResponse,
    OrderRequest,
    OrderResponse,
    AnalyticsResponse,
    SelectDishRequest,
    SelectDishResponse,
    SmartAlternativeNudge,
    StoredTransformation,
    TransformDishRequest,
    TransformDishResponse,
)
from database import (
    app_state,
    build_restaurant_from_preset,
    initialize_state,
    resolve_nearest_market,
)
from optimizer import optimize_dish
from llm_service import get_culinary_translation


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    initialize_state()
    yield


app = FastAPI(
    title="Naija Fork",
    description="Constraint-aware plant-based Nigerian menu transformation API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/v1/manager/onboarding", response_model=OnboardingResponse)
async def onboarding(payload: OnboardingRequest) -> OnboardingResponse:
    import uuid

    restaurant_id = str(uuid.uuid4())
    restaurant = app_state.restaurants.get(restaurant_id)
    # Construct directly so custom menu and coordinates/city are preserved.
    from models import Restaurant

    restaurant = Restaurant(
        id=restaurant_id,
        name=payload.name,
        city=payload.city,
        nearest_market=resolve_nearest_market(payload.city),
        pantry=payload.pantry,
        menu=payload.menu,
    )
    app_state.restaurants[restaurant_id] = restaurant
    return OnboardingResponse(
        restaurant_id=restaurant_id,
        name=restaurant.name,
        nearest_market=restaurant.nearest_market,
        message="Restaurant onboarded successfully.",
    )


@app.post("/api/v1/manager/load-preset/{preset_id}", response_model=OnboardingResponse)
async def load_preset(preset_id: str) -> OnboardingResponse:
    try:
        restaurant = build_restaurant_from_preset(preset_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    app_state.restaurants[restaurant.id] = restaurant
    return OnboardingResponse(
        restaurant_id=restaurant.id,
        name=restaurant.name,
        nearest_market=restaurant.nearest_market,
        message=f"Loaded preset {preset_id}.",
    )


@app.post(
    "/api/v1/manager/dishes/{dish_id}/transform",
    response_model=TransformDishResponse,
)
async def transform_dish(
    dish_id: str,
    payload: TransformDishRequest,
    restaurant_id: str,
) -> TransformDishResponse:
    restaurant = app_state.restaurants.get(restaurant_id)
    if restaurant is None:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    dish = app_state.get_dish(restaurant_id, dish_id)
    if dish is None:
        raise HTTPException(status_code=404, detail="Dish not found")

    tier_a, tier_b = optimize_dish(
        dish,
        restaurant,
        payload.constraints,
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

    transformation = StoredTransformation(
        id=str(__import__("uuid").uuid4()),
        restaurant_id=restaurant_id,
        dish_id=dish_id,
        dish_name=dish.name,
        status="pending_approval",
        constraints=payload.constraints,
        in_store_options=tier_a,
        local_market_options=tier_b,
    )
    app_state.transformations[transformation.id] = transformation

    return TransformDishResponse(
        transformation_id=transformation.id,
        dish_id=dish_id,
        dish_name=dish.name,
        status="pending_approval",
        in_store_options=tier_a,
        local_market_options=tier_b,
        message=(
            "No plant-based alternatives found." 
            if not tier_a and not tier_b
            else "Ranked plant-based transformations generated."
        ),
    )


@app.post(
    "/api/v1/manager/transformations/{transformation_id}/approve",
    response_model=ApproveTransformationResponse,
)
async def approve_transformation(
    transformation_id: str,
    payload: ApproveTransformationRequest,
) -> ApproveTransformationResponse:
    transformation = app_state.get_transformation(transformation_id)
    if transformation is None:
        raise HTTPException(status_code=404, detail="Transformation not found")

    all_options = (
        transformation.in_store_options + transformation.local_market_options
    )
    option = next(
        (candidate for candidate in all_options if candidate.id == payload.option_id),
        None,
    )
    if option is None:
        raise HTTPException(status_code=404, detail="Transformation option not found")

    restaurant = app_state.get_restaurant(transformation.restaurant_id)
    if restaurant is None:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    original_dish = app_state.get_dish(
        transformation.restaurant_id,
        transformation.dish_id,
    )
    if original_dish is None:
        raise HTTPException(status_code=404, detail="Original dish not found")

    raw_savings = option.financials.cost_savings_ngn
    customer_savings = raw_savings * (payload.restaurant_discount_pct / 100.0)
    discounted_price = max(0.0, original_dish.selling_price_ngn - customer_savings)
    restaurant_margin = max(0.0, raw_savings - customer_savings)

    transformation.status = "approved"
    transformation.approved_option_id = payload.option_id
    transformation.restaurant_discount_pct = payload.restaurant_discount_pct

    app_state.approved_alternatives[transformation.dish_id] = ApprovedAlternative(
        transformation_id=transformation_id,
        option_id=payload.option_id,
        dish_id=transformation.dish_id,
        restaurant_id=transformation.restaurant_id,
        option=option,
        original_dish_name=original_dish.name,
        original_price_ngn=original_dish.selling_price_ngn,
        discounted_alternative_price_ngn=round(discounted_price, 2),
        customer_savings_ngn=round(customer_savings, 2),
        restaurant_margin_gain_ngn=round(restaurant_margin, 2),
    )

    return ApproveTransformationResponse(
        transformation_id=transformation_id,
        approved_option_id=payload.option_id,
        status="approved",
        discounted_price_ngn=round(discounted_price, 2),
        customer_savings_ngn=round(customer_savings, 2),
        restaurant_margin_gain_ngn=round(restaurant_margin, 2),
        message="Transformation approved and published to the customer catalog.",
    )


@app.get(
    "/api/v1/customer/restaurants/{restaurant_id}/menu",
    response_model=CustomerMenuResponse,
)
async def customer_menu(restaurant_id: str) -> CustomerMenuResponse:
    restaurant = app_state.get_restaurant(restaurant_id)
    if restaurant is None:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    public_menu: list[MenuDishPublic] = []
    for dish in restaurant.menu:
        alternative = app_state.approved_alternatives.get(dish.id)
        badge = None
        if alternative is not None:
            badge = (
                f"Save ₦{alternative.customer_savings_ngn:,.0f} | "
                f"{alternative.option.nutrition.protein_new_g:.0f}g Protein"
            )
        public_menu.append(
            MenuDishPublic(
                id=dish.id,
                name=dish.name,
                description=dish.description,
                category=dish.category,
                selling_price_ngn=dish.selling_price_ngn,
                has_smart_swap=alternative is not None,
                smart_swap_badge=badge,
            )
        )

    return CustomerMenuResponse(
        restaurant_id=restaurant_id,
        restaurant_name=restaurant.name,
        menu=public_menu,
    )


@app.post(
    "/api/v1/customer/select-dish",
    response_model=SelectDishResponse,
)
async def select_dish(payload: SelectDishRequest) -> SelectDishResponse:
    restaurant = app_state.get_restaurant(payload.restaurant_id)
    if restaurant is None:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    dish = app_state.get_dish(payload.restaurant_id, payload.dish_id)
    if dish is None:
        raise HTTPException(status_code=404, detail="Dish not found")

    public_dish = MenuDishPublic(
        id=dish.id,
        name=dish.name,
        description=dish.description,
        category=dish.category,
        selling_price_ngn=dish.selling_price_ngn,
        has_smart_swap=False,
    )
    nudge = None
    alternative = app_state.approved_alternatives.get(dish.id)
    if alternative is not None:
        public_dish.has_smart_swap = True
        public_dish.smart_swap_badge = (
            f"Save ₦{alternative.customer_savings_ngn:,.0f} | "
            f"{alternative.option.nutrition.protein_new_g:.0f}g Protein"
        )
        option = alternative.option
        nutrition = option.nutrition
        taste_tags = sorted({
            tag
            for swap in option.swaps
            for tag in app_state.ingredients[
                swap.replacement_ingredient_id
            ].texture_tags
        })
        nudge = SmartAlternativeNudge(
            alternative_dish_name=option.dish_name,
            alternative_description=option.dish_description,
            original_price_ngn=dish.selling_price_ngn,
            discounted_alternative_price_ngn=alternative.discounted_alternative_price_ngn,
            customer_savings_ngn=alternative.customer_savings_ngn,
            protein_original_g=nutrition.protein_original_g,
            protein_new_g=nutrition.protein_new_g,
            saturated_fat_reduction_pct=nutrition.saturated_fat_reduction_pct,
            fiber_gain_g=nutrition.fiber_gain_g,
            health_badge=(
                f"{nutrition.saturated_fat_reduction_pct:.0f}% Less Sat Fat | "
                f"{nutrition.protein_new_g:.0f}g Protein | "
                f"+{nutrition.fiber_gain_g:.0f}g Fiber | Cholesterol-Free"
            ),
            taste_texture_tags=taste_tags[:6],
            menu_copy=option.menu_copy,
            approved_option_id=option.id,
        )

    return SelectDishResponse(
        dish=public_dish,
        original_price_ngn=dish.selling_price_ngn,
        smart_alternative_nudge=nudge,
    )


@app.post("/api/v1/customer/orders", response_model=OrderResponse)
async def create_order(payload: OrderRequest) -> OrderResponse:
    restaurant = app_state.get_restaurant(payload.restaurant_id)
    if restaurant is None:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    dish = app_state.get_dish(payload.restaurant_id, payload.dish_id)
    if dish is None:
        raise HTTPException(status_code=404, detail="Dish not found")

    from models import Order
    import uuid

    paid_price = dish.selling_price_ngn
    customer_savings = 0.0
    margin_gain = 0.0
    saturated_fat_avoided = 0.0
    carbon_reduced = 0.0

    if payload.choice == "approved_alternative":
        alternative = app_state.approved_alternatives.get(dish.id)
        if alternative is None:
            raise HTTPException(status_code=409, detail="No approved alternative exists")
        if (
            payload.approved_option_id is not None
            and payload.approved_option_id != alternative.option_id
        ):
            raise HTTPException(status_code=400, detail="Approved option ID mismatch")

        paid_price = alternative.discounted_alternative_price_ngn
        customer_savings = alternative.customer_savings_ngn
        margin_gain = alternative.restaurant_margin_gain_ngn
        saturated_fat_avoided = (
            alternative.option.nutrition.saturated_fat_original_g
            - alternative.option.nutrition.saturated_fat_new_g
        )
        # Simple transparent estimate: 2.5 kg CO2e avoided per 100 g animal product.
        for swap in alternative.option.swaps:
            if swap.original_ingredient_id in {
                "beef", "goat_meat", "chicken", "stockfish", "fish", "ponmo"
            }:
                carbon_reduced += (swap.original_quantity_g / 100.0) * 2.5

    order = Order(
        id=str(uuid.uuid4()),
        restaurant_id=payload.restaurant_id,
        dish_id=payload.dish_id,
        choice=payload.choice,
        original_price_ngn=dish.selling_price_ngn,
        paid_price_ngn=round(paid_price, 2),
        customer_savings_ngn=round(customer_savings, 2),
        restaurant_margin_gain_ngn=round(margin_gain, 2),
        saturated_fat_avoided_g=round(saturated_fat_avoided, 2),
        carbon_footprint_reduced_kg=round(carbon_reduced, 2),
    )
    app_state.orders.append(order)

    return OrderResponse(
        order_id=order.id,
        restaurant_id=payload.restaurant_id,
        dish_id=payload.dish_id,
        choice=payload.choice,
        paid_price_ngn=order.paid_price_ngn,
        customer_savings_ngn=order.customer_savings_ngn,
        message="Order recorded successfully.",
    )


@app.get(
    "/api/v1/manager/analytics/{restaurant_id}",
    response_model=AnalyticsResponse,
)
async def restaurant_analytics(restaurant_id: str) -> AnalyticsResponse:
    restaurant = app_state.get_restaurant(restaurant_id)
    if restaurant is None:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    orders = [
        order for order in app_state.orders
        if order.restaurant_id == restaurant_id
    ]
    alternative_orders = sum(
        1 for order in orders if order.choice == "approved_alternative"
    )
    total_orders = len(orders)
    popular_swaps = sorted({
        app_state.approved_alternatives[dish_id].option.dish_name
        for dish_id in app_state.approved_alternatives
        if app_state.approved_alternatives[dish_id].restaurant_id == restaurant_id
    })

    return AnalyticsResponse(
        restaurant_id=restaurant_id,
        restaurant_name=restaurant.name,
        total_orders=total_orders,
        alternative_orders=alternative_orders,
        conversion_rate_pct=round(
            (alternative_orders / total_orders * 100.0) if total_orders else 0.0,
            2,
        ),
        total_customer_savings_ngn=round(
            sum(order.customer_savings_ngn for order in orders),
            2,
        ),
        total_margin_gain_ngn=round(
            sum(order.restaurant_margin_gain_ngn for order in orders),
            2,
        ),
        total_saturated_fat_avoided_g=round(
            sum(order.saturated_fat_avoided_g for order in orders),
            2,
        ),
        total_carbon_footprint_reduced_kg=round(
            sum(order.carbon_footprint_reduced_kg for order in orders),
            2,
        ),
        popular_swaps=popular_swaps,
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "Naija Fork"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)