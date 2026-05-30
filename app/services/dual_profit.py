"""Dual profit calculation — computa FBA y MFN profit para un item.

Usado por fast_scan_processor y batch_processor.
Fetch de datos = 1 vez. Cálculo de profit = 2 veces. Guardar = ambos.
"""

import logging

from app.models.job import Job
from app.models.job_item import JobItem
from app.services.engines.profit_engine import compute_profit
from app.services.providers.base import FeesResult

logger = logging.getLogger(__name__)


def compute_dual_profit(
    item: JobItem,
    job: Job,
    sale_price: float | None,
    fba_fees: FeesResult | None,
    mfn_fees: FeesResult | None,
    keepa_referral_pct: float | None = None,
    keepa_fba_fee: float | None = None,
) -> None:
    """Calcula profit para FBA y MFN, persiste ambos en el item.

    - FBA: usa fba_fees de SP-API (o Keepa fallback)
    - MFN: usa mfn_fees de SP-API (sin FBA fulfillment fee)
    - best_scenario: el que tenga más profit (si ambos son positivos)
    - Los campos legacy (profit, roi_pct, etc.) = el escenario preferido del job
    """
    item.estimated_sale_price = sale_price
    cost = float(item.cost_price) if item.cost_price else 0.0

    if not sale_price or cost <= 0:
        return

    # ── FBA Scenario ──
    fba_ref_pct = None
    fba_fixed = None
    if fba_fees:
        fba_ref_pct = fba_fees.referral_fee / sale_price if fba_fees.referral_fee > 0 else None
        fba_fixed = fba_fees.fba_fee
        item.sp_api_total_fees = fba_fees.total_fees
        item.sp_api_referral_fee = fba_fees.referral_fee
        item.sp_api_fba_fee = fba_fees.fba_fee
    else:
        fba_ref_pct = keepa_referral_pct
        fba_fixed = keepa_fba_fee

    try:
        fba_pr = compute_profit(
            sale_price=sale_price, cost_price=cost, marketplace="amazon_fba",
            shipping_cost=float(job.fba_shipping_to_amazon),
            prep_cost=float(job.fba_prep_cost),
            fee_rate_override=fba_ref_pct, fee_fixed_override=fba_fixed,
        )
        item.fba_profit = round(fba_pr.profit, 2)
        item.fba_roi_pct = round(fba_pr.roi * 100, 4) if fba_pr.roi else 0
        item.fba_margin_pct = round(fba_pr.margin * 100, 4) if fba_pr.margin else 0
        item.fba_total_fees = round(fba_pr.marketplace_fees, 2)
    except Exception as e:
        logger.warning("Error FBA profit %s: %s", item.asin, e)
        fba_pr = None

    # ── MFN Scenario ──
    mfn_ref_pct = None
    if mfn_fees:
        mfn_ref_pct = mfn_fees.referral_fee / sale_price if mfn_fees.referral_fee > 0 else None

    try:
        mfn_pr = compute_profit(
            sale_price=sale_price, cost_price=cost, marketplace="amazon_fba",  # marketplace solo afecta default fees
            shipping_cost=float(job.mfn_shipping_to_customer),
            prep_cost=float(job.mfn_prep_cost),
            packaging_cost=float(job.mfn_packaging_cost),
            fee_rate_override=mfn_ref_pct or fba_ref_pct,  # MFN referral = mismo que FBA
            fee_fixed_override=0.0,  # MFN no tiene FBA fulfillment fee
        )
        item.mfn_profit = round(mfn_pr.profit, 2)
        item.mfn_roi_pct = round(mfn_pr.roi * 100, 4) if mfn_pr.roi else 0
        item.mfn_margin_pct = round(mfn_pr.margin * 100, 4) if mfn_pr.margin else 0
        item.mfn_total_fees = round(mfn_pr.marketplace_fees, 2)
    except Exception as e:
        logger.warning("Error MFN profit %s: %s", item.asin, e)
        mfn_pr = None

    # ── Best Scenario ──
    # best_scenario refleja cuál fulfillment da más profit, independiente de
    # can_sell/restrictions. La elegibilidad se consulta por separado vía
    # can_sell y restriction_reason. Así el seller ve "MFN da $365 de profit"
    # aunque necesite aprobación — y puede decidir si vale la pena solicitarla.
    fba_p = float(item.fba_profit) if item.fba_profit is not None else -999
    mfn_p = float(item.mfn_profit) if item.mfn_profit is not None else -999

    if item.fba_eligible is False:
        item.best_scenario = "mfn" if mfn_p > 0 else "neither"
    elif fba_p > 0 and mfn_p > 0:
        item.best_scenario = "fba" if fba_p >= mfn_p else "mfn"
    elif fba_p > 0:
        item.best_scenario = "fba"
    elif mfn_p > 0:
        item.best_scenario = "mfn"
    else:
        item.best_scenario = "neither"

    # ── Selected scenario (campos legacy) ──
    preferred = job.fulfillment_type  # "fba" o "mfn"
    selected_pr = fba_pr if preferred == "fba" else mfn_pr

    if selected_pr:
        item.profit = round(selected_pr.profit, 2)
        item.roi_pct = round(selected_pr.roi * 100, 4) if selected_pr.roi else 0
        item.margin_pct = round(selected_pr.margin * 100, 4) if selected_pr.margin else 0
        item.marketplace_fees = round(selected_pr.marketplace_fees, 2)
        item.shipping_cost = round(selected_pr.shipping_cost, 2)
        item.prep_cost = round(selected_pr.prep_cost, 2)
        item.return_reserve = round(selected_pr.return_reserve, 2)
