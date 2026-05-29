"""Export service — genera CSV con resultados del job incluyendo datos SP-API."""

import csv
import os
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.job_item import JobItem

EXPORT_COLUMNS = [
    # Input
    ("input_id", "Input ID"),
    ("input_id_type", "ID Type"),
    ("cost_price", "Cost"),

    # Amazon básico
    ("asin", "ASIN"),
    ("title", "Title"),
    ("brand", "Brand"),
    ("category", "Category"),

    # Restrictions
    ("can_sell", "Can Sell?"),
    ("fba_eligible", "FBA Eligible?"),
    ("restriction_reason", "Restriction"),

    # Pricing
    ("buy_box_price", "Buy Box Price"),
    ("list_price", "List Price"),
    ("estimated_sale_price", "Est. Sale Price"),

    # Physical attributes
    ("item_weight_grams", "Item Weight (g)"),
    ("package_weight_grams", "Package Weight (g)"),
    ("item_height", "Item Height (1/100in)"),
    ("item_length", "Item Length (1/100in)"),
    ("item_width", "Item Width (1/100in)"),

    # Profit — Selected scenario
    ("profit", "Profit (Selected)"),
    ("roi_pct", "ROI % (Selected)"),
    ("margin_pct", "Margin % (Selected)"),
    ("marketplace_fees", "Fees (Selected)"),

    # Profit — FBA
    ("fba_profit", "FBA Profit"),
    ("fba_roi_pct", "FBA ROI %"),
    ("fba_margin_pct", "FBA Margin %"),
    ("fba_total_fees", "FBA Total Fees"),

    # Profit — MFN
    ("mfn_profit", "MFN Profit"),
    ("mfn_roi_pct", "MFN ROI %"),
    ("mfn_margin_pct", "MFN Margin %"),
    ("mfn_total_fees", "MFN Total Fees"),

    # Best scenario
    ("best_scenario", "Best Scenario"),

    # Fees detail
    ("sp_api_referral_fee", "Referral Fee"),
    ("sp_api_fba_fee", "FBA Fee (SP-API)"),
    ("fba_fee", "FBA Fee (Keepa)"),
    ("referral_fee_pct", "Referral %"),

    # Velocity
    ("velocity_score", "Velocity Score"),
    ("sales_per_day", "Sales/Day"),
    ("estimated_days_to_sell", "Days to Sell"),
    ("monthly_sold", "Monthly Sold"),
    ("sales_rank_drops_30", "Rank Drops 30d"),

    # Competition
    ("sales_rank", "BSR"),
    ("seller_count", "Sellers"),
    ("offer_count_new", "New Offers"),
    ("offer_count_used", "Used Offers"),
    ("amazon_is_seller", "Amazon Sells?"),
    ("buy_box_is_amazon", "Amazon Buy Box?"),
    ("out_of_stock_pct_90", "OOS% 90d"),

    # Reviews
    ("rating", "Rating"),
    ("review_count", "Reviews"),

    # Other
    ("trade_in_value", "Trade-in Value"),
    ("multipack_qty", "Pack Qty"),
    ("is_hazmat", "Hazmat?"),
    ("image_url", "Image URL"),

    # Status
    ("status", "Status"),
]


async def export_job_csv(job_id: UUID, db: AsyncSession, items=None) -> str:
    """Exporta resultados de un job a CSV. Retorna path del archivo.

    Si se pasan `items` (lista de JobItem ya filtrada), se usan directamente.
    De lo contrario se consultan todos los items del job sin filtrar.
    """
    os.makedirs(settings.upload_dir, exist_ok=True)
    csv_path = os.path.join(settings.upload_dir, f"export_{job_id}.csv")

    if items is None:
        query = (
            select(JobItem)
            .where(JobItem.job_id == job_id)
            .order_by(JobItem.input_row)
        )
        result = await db.execute(query)
        items = result.scalars().all()

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        # Header
        writer.writerow([label for _, label in EXPORT_COLUMNS])

        # Rows
        for item in items:
            row = []
            for attr, _ in EXPORT_COLUMNS:
                val = getattr(item, attr, "")
                if val is None:
                    val = ""
                elif isinstance(val, bool):
                    val = "Yes" if val else "No"
                elif isinstance(val, float):
                    val = round(val, 2)
                row.append(val)
            writer.writerow(row)

    return csv_path
