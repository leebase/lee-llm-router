"""Staffing catalog loader: typed, schema-validated catalog documents.

Shape-only boundary for the six staffing YAML documents (routes,
channels, terms, policy, classes, crews). No selection, ranking, or
pricing decision logic lives here. Class metadata never maps to a
preferred model or route (D206); it only joins evidence or gates an
unevidenced cheap trial.
"""

from __future__ import annotations

from lee_llm_router.staffing.catalog import (
    DOCUMENT_ORDER,
    BadgeMultipliers,
    CanonicalEncoding,
    Channel,
    ChannelsCatalog,
    CheapTrialRule,
    ClassesCatalog,
    Crew,
    CrewsCatalog,
    DenyPredicate,
    FeeEntry,
    NeverAutomaticRule,
    PolicyCatalog,
    ReviewIndependenceRule,
    RoleClassEntry,
    RoleFloorRecord,
    RoleScopedRule,
    Route,
    RoutesCatalog,
    SpendCap,
    StaffingCatalog,
    StaffingCatalogError,
    TermsCatalog,
    TermsEntry,
    ValueSets,
    canonical_class_key,
    load_staffing_catalog,
    load_staffing_document,
    validate_class_block,
)

__all__ = [
    "DOCUMENT_ORDER",
    "BadgeMultipliers",
    "CanonicalEncoding",
    "Channel",
    "ChannelsCatalog",
    "CheapTrialRule",
    "ClassesCatalog",
    "Crew",
    "CrewsCatalog",
    "DenyPredicate",
    "FeeEntry",
    "NeverAutomaticRule",
    "PolicyCatalog",
    "ReviewIndependenceRule",
    "RoleClassEntry",
    "RoleFloorRecord",
    "RoleScopedRule",
    "Route",
    "RoutesCatalog",
    "SpendCap",
    "StaffingCatalog",
    "StaffingCatalogError",
    "TermsCatalog",
    "TermsEntry",
    "ValueSets",
    "canonical_class_key",
    "load_staffing_catalog",
    "load_staffing_document",
    "validate_class_block",
]
