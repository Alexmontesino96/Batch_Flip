from app.services.providers.base import (
    DataProvider,
    FeesResult,
    ProductData,
    PricingResult,
    RestrictionResult,
)
from app.services.providers.hybrid import HybridProvider
from app.services.providers.keepa import KeepaProvider
from app.services.providers.spapi import SPAPIProvider


def create_hybrid_provider(
    seller_id: str | None = None,
    marketplace: str = "us",
) -> HybridProvider:
    """Crea un HybridProvider con Keepa + SP-API (si configurado)."""
    keepa = KeepaProvider()
    spapi = SPAPIProvider(marketplace=marketplace, seller_id=seller_id)
    if not spapi.is_configured:
        spapi = None
    return HybridProvider(keepa=keepa, spapi=spapi, seller_id=seller_id, marketplace=marketplace)


__all__ = [
    "DataProvider", "ProductData", "FeesResult", "PricingResult", "RestrictionResult",
    "KeepaProvider", "SPAPIProvider", "HybridProvider", "create_hybrid_provider",
]
