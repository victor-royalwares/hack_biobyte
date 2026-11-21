"""
models.py — Pydantic v2 schemas for Naija Fork.

DESIGN PRINCIPLE: All financial figures (₦ costs, margins) and nutritional data
originate exclusively from the Python optimization engine. The LLM is never
permitted to generate or modify numerical fields — only the text fields:
  dish_name, dish_description, kitchen_prep_instructions, menu_copy,
  constraint_satisfaction_proof.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


# ─── Enum / Literal Type Aliases ──────────────────────────────────────────────

IngredientCategory = Literal["protein", "umami", "base", "fat", "spice", "swallow", "vegetable"]
PrepComplexity = Literal["low", "medium", "high"]
OptimizationPriority = Literal["balanced", "lowest_cost", "closest_texture", "highest_protein"]
Tier = Literal["A_in_store", "B_local_market"]
TransformationStatus = Literal["pending_approval", "approved", "rejected"]
OrderChoice = Literal["original", "approved_alternative"]


# ─── Core Ingredient Model ─────────────────────────────────────────────────────

class Ingredient(BaseModel):
    """
    Nigerian ingredient with Naira pricing, macros, culinary profile,
    and regional wholesale market availability.
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str
    name: str
    local_name: Optional[str] = None

    # Culinary role
    category: IngredientCategory
    is_plant_based: bool

    # Economics (NGN)
    cost_per_100g_ngn: float = Field(gt=0, description="Cost in Naira per 100 g")

    # Macros per 100 g
    protein_g_per_100g: float = Field(ge=0)
    saturated_fat_g_per_100g: float = Field(ge=0)
    fiber_g_per_100g: float = Field(ge=0)
    calories_per_100g: float = Field(ge=0)

    # Culinary profile
    texture_tags: list[str] = Field(default_factory=list)
    umami_score: int = Field(ge=1, le=10)
    familiarity_score: int = Field(
        ge=1, le=10,
        description="Acceptability to mainstream Nigerian diners (1=exotic, 10=universal)"
    )
    prep_complexity: PrepComplexity

    # Geo-market availability
    available_markets: list[str] = Field(default_factory=list)


# ─── Dish Structure ───────────────────────────────────────────────────────────

class DishIngredient(BaseModel):
    """An ingredient entry within a menu dish, specifying quantity in grams."""
    ingredient_id: str
    quantity_g: float = Field(gt=0)
    is_primary: bool = False  # Is this the dish's headline protein/star ingredient?


class MenuDish(BaseModel):
    """A dish on the restaurant's active menu."""
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str
    name: str
    description: str
    category: str = "main"
    ingredients: list[DishIngredient]
    prep_time_minutes: int = Field(ge=1)
    selling_price_ngn: float = Field(gt=0)


# ─── Restaurant ───────────────────────────────────────────────────────────────

class Restaurant(BaseModel):
    """Restaurant profile including geo-location, pantry stock, and menu."""
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str
    name: str
    city: str
    nearest_market: str  # Auto-resolved from city → wholesale market mapping
    pantry: dict[str, float] = Field(
        default_factory=dict,
        description="Maps ingredient_id → quantity currently in stock (grams)"
    )
    menu: list[MenuDish] = Field(default_factory=list)


# ─── Optimization Schemas ──────────────────────────────────────────────────────

class TransformationConstraints(BaseModel):
    """Manager-defined hard and soft constraints for the optimization engine."""
    max_cost_ngn: Optional[float] = Field(
        None, description="Max acceptable total ingredient cost for the transformed dish"
    )
    min_protein_g: Optional[float] = Field(
        None, description="Minimum protein content per serving in grams"
    )
    min_familiarity_score: int = Field(
        default=6, ge=1, le=10,
        description="Minimum familiarity score for any replacement ingredient"
    )
    max_prep_complexity: PrepComplexity = "medium"
    optimization_priority: OptimizationPriority = "balanced"


class IngredientSwap(BaseModel):
    """Full audit trail for a single ingredient substitution decision."""
    # Original
    original_ingredient_id: str
    original_ingredient_name: str
    original_quantity_g: float
    original_cost_ngn: float

    # Replacement
    replacement_ingredient_id: str
    replacement_ingredient_name: str
    replacement_local_name: Optional[str] = None
    replacement_quantity_g: float
    replacement_cost_ngn: float

    # Deltas (computed by optimizer, never LLM)
    cost_delta_ngn: float          # Negative = money saved
    protein_delta_g: float
    texture_similarity_score: float = Field(ge=0.0, le=1.0)


class FinancialDelta(BaseModel):
    """Full financial impact of a transformation option (Python-computed only)."""
    original_ingredient_cost_ngn: float
    new_ingredient_cost_ngn: float
    cost_savings_ngn: float
    cost_savings_pct: float
    projected_margin_gain_ngn: float  # Assuming the same menu selling price


class NutritionDelta(BaseModel):
    """Nutritional impact of a transformation option (Python-computed only)."""
    protein_original_g: float
    protein_new_g: float
    protein_retention_pct: float
    saturated_fat_original_g: float
    saturated_fat_new_g: float
    saturated_fat_reduction_pct: float
    fiber_original_g: float
    fiber_new_g: float
    fiber_gain_g: float
    calories_original: float
    calories_new: float


class TransformationOption(BaseModel):
    """
    One fully ranked plant-based swap combination.

    Financial & nutritional data: set by optimizer.py (deterministic Python math).
    Text fields (dish_name, etc.): set by llm_service.py (or deterministic fallback).
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tier: Tier
    swaps: list[IngredientSwap]
    financials: FinancialDelta
    nutrition: NutritionDelta
    composite_score: float = Field(ge=0.0, le=1.0)

    # LLM-generated culinary text (or deterministic fallback text)
    dish_name: str = ""
    dish_description: str = ""
    kitchen_prep_instructions: str = ""
    menu_copy: str = ""
    constraint_satisfaction_proof: str = ""

    # Procurement metadata
    requires_market_procurement: bool = False
    procurement_list: list[str] = Field(default_factory=list)


# ─── Internal State Records ────────────────────────────────────────────────────

class StoredTransformation(BaseModel):
    """Internal lifecycle record for a dish transformation request."""
    id: str
    restaurant_id: str
    dish_id: str
    dish_name: str
    status: TransformationStatus = "pending_approval"
    constraints: TransformationConstraints
    in_store_options: list[TransformationOption] = Field(default_factory=list)
    local_market_options: list[TransformationOption] = Field(default_factory=list)
    approved_option_id: Optional[str] = None
    restaurant_discount_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    approved_at: Optional[datetime] = None


class ApprovedAlternative(BaseModel):
    """Customer-catalog entry for a manager-approved plant-based alternative."""
    transformation_id: str
    option_id: str
    dish_id: str
    restaurant_id: str
    option: TransformationOption
    original_dish_name: str
    original_price_ngn: float
    discounted_alternative_price_ngn: float
    customer_savings_ngn: float
    restaurant_margin_gain_ngn: float


class Order(BaseModel):
    """Internal order record used for analytics tracking."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    restaurant_id: str
    dish_id: str
    choice: OrderChoice
    original_price_ngn: float
    paid_price_ngn: float
    customer_savings_ngn: float
    restaurant_margin_gain_ngn: float
    saturated_fat_avoided_g: float
    carbon_footprint_reduced_kg: float
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ─── API Request / Response Schemas ───────────────────────────────────────────

class OnboardingRequest(BaseModel):
    """Payload for registering a new restaurant."""
    name: str
    city: str
    pantry: dict[str, float] = Field(
        default_factory=dict,
        description="ingredient_id → quantity in grams currently in stock"
    )
    menu: list[MenuDish] = Field(default_factory=list)


class OnboardingResponse(BaseModel):
    restaurant_id: str
    name: str
    nearest_market: str
    message: str


class TransformDishRequest(BaseModel):
    """Manager request to find plant-based alternatives for a dish."""
    constraints: TransformationConstraints = Field(default_factory=TransformationConstraints)


class TransformDishResponse(BaseModel):
    transformation_id: str
    dish_id: str
    dish_name: str
    status: TransformationStatus
    in_store_options: list[TransformationOption]
    local_market_options: list[TransformationOption]
    message: str


class ApproveTransformationRequest(BaseModel):
    """Manager approval payload: choose an option and set the discount split."""
    option_id: str
    restaurant_discount_pct: float = Field(
        default=0.0, ge=0.0, le=100.0,
        description="% of raw ingredient cost savings passed to the customer as a lower menu price"
    )


class ApproveTransformationResponse(BaseModel):
    transformation_id: str
    approved_option_id: str
    status: TransformationStatus
    discounted_price_ngn: float
    customer_savings_ngn: float
    restaurant_margin_gain_ngn: float
    message: str


# ─── Customer-Facing Schemas ───────────────────────────────────────────────────

class MenuDishPublic(BaseModel):
    """Customer-visible dish entry with optional Smart Swap badge."""
    id: str
    name: str
    description: str
    category: str
    selling_price_ngn: float
    has_smart_swap: bool = False
    smart_swap_badge: Optional[str] = None  # e.g., "Save ₦400 · 28g Protein"


class CustomerMenuResponse(BaseModel):
    restaurant_id: str
    restaurant_name: str
    menu: list[MenuDishPublic]


class SelectDishRequest(BaseModel):
    restaurant_id: str
    dish_id: str


class SmartAlternativeNudge(BaseModel):
    """Full Smart Swap nudge shown when a customer selects a dish with an approved alternative."""
    alternative_dish_name: str
    alternative_description: str
    original_price_ngn: float
    discounted_alternative_price_ngn: float
    customer_savings_ngn: float
    # Side-by-side health comparison
    protein_original_g: float
    protein_new_g: float
    saturated_fat_reduction_pct: float
    fiber_gain_g: float
    health_badge: str   # e.g., "29% Less Sat Fat · High Protein · +6g Fiber · Cholesterol-Free"
    taste_texture_tags: list[str]
    menu_copy: str
    approved_option_id: str


class SelectDishResponse(BaseModel):
    dish: MenuDishPublic
    original_price_ngn: float
    smart_alternative_nudge: Optional[SmartAlternativeNudge] = None


class OrderRequest(BaseModel):
    restaurant_id: str
    dish_id: str
    choice: OrderChoice
    approved_option_id: Optional[str] = None  # Required when choice = "approved_alternative"


class OrderResponse(BaseModel):
    order_id: str
    restaurant_id: str
    dish_id: str
    choice: OrderChoice
    paid_price_ngn: float
    customer_savings_ngn: float
    message: str


class AnalyticsResponse(BaseModel):
    """Aggregated restaurant analytics exposed to the manager portal."""
    restaurant_id: str
    restaurant_name: str
    total_orders: int
    alternative_orders: int
    conversion_rate_pct: float
    total_customer_savings_ngn: float
    total_margin_gain_ngn: float
    total_saturated_fat_avoided_g: float
    total_carbon_footprint_reduced_kg: float
    popular_swaps: list[str] = Field(default_factory=list)
