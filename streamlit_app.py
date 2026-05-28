"""Streamlit UI para testear Batch Flip — Single Analysis + Batch Jobs."""

import asyncio
import io
import time

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Batch Flip", page_icon="📦", layout="wide")


# ── Helpers ──

def run_async(coro):
    """Ejecuta una coroutine desde Streamlit (sync context)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def format_currency(val):
    if val is None:
        return "—"
    return f"${val:,.2f}"


def format_pct(val):
    if val is None:
        return "—"
    return f"{val:.1f}%"


def format_number(val):
    if val is None:
        return "—"
    if isinstance(val, float):
        return f"{val:,.2f}"
    return f"{val:,}"


# ── Single Analysis ──

async def run_single_analysis(product_id, cost_price, marketplace, fulfillment_type, prep_cost, shipping_cost, check_restrictions):
    from app.config import settings
    from app.services.engines.profit_engine import compute_profit
    from app.services.engines.velocity_engine import compute_velocity_from_sales_per_day
    from app.services.file_parser import detect_id_type
    from app.services.providers.base import DOMAIN_MAP
    from app.services.providers.hybrid import HybridProvider
    from app.services.providers.keepa import KeepaProvider
    from app.services.providers.spapi import SPAPIProvider

    domain = DOMAIN_MAP.get(marketplace, 1)
    keepa = KeepaProvider()
    spapi = None
    if check_restrictions and settings.sp_api_refresh_token:
        spapi = SPAPIProvider(seller_id=settings.sp_api_seller_id, marketplace=marketplace)
    hybrid = HybridProvider(keepa=keepa, spapi=spapi, seller_id=settings.sp_api_seller_id if spapi else None, marketplace=marketplace)

    try:
        id_type = detect_id_type(product_id)
        asin = product_id if id_type == "asin" else None
        if not asin:
            asin = await hybrid.resolve_code_to_asin(product_id, domain=domain)
        if not asin:
            return None, "No se encontró ASIN"

        products = await hybrid.get_products_enriched([asin], domain=domain, check_restrictions=check_restrictions, fetch_fees=True)
        p = products.get(asin)
        if not p:
            return None, "No se encontraron datos"

        # Profit
        profit_result = None
        mkt = "amazon_mfn" if fulfillment_type == "mfn" else "amazon_fba"
        if p.buy_box_price and cost_price > 0:
            fee_fixed = p.fba_fulfillment_fee if mkt == "amazon_fba" else None
            profit_result = compute_profit(
                sale_price=p.buy_box_price, cost_price=cost_price, marketplace=mkt,
                shipping_cost=shipping_cost, prep_cost=prep_cost,
                fee_rate_override=p.referral_fee_pct, fee_fixed_override=fee_fixed,
            )

        # Velocity
        vel = None
        if p.sales_per_day and p.sales_per_day > 0:
            vel = compute_velocity_from_sales_per_day(p.sales_per_day)

        return {"product": p, "profit": profit_result, "velocity": vel}, None
    finally:
        await hybrid.close()


async def run_batch_analysis(asins_list, cost_map, marketplace, fulfillment_type, prep_cost, shipping_cost, check_restrictions):
    """Analiza múltiples ASINs en batch."""
    from app.config import settings
    from app.services.engines.profit_engine import compute_profit
    from app.services.engines.velocity_engine import compute_velocity_from_sales_per_day
    from app.services.providers.base import DOMAIN_MAP
    from app.services.providers.hybrid import HybridProvider
    from app.services.providers.keepa import KeepaProvider
    from app.services.providers.spapi import SPAPIProvider

    domain = DOMAIN_MAP.get(marketplace, 1)
    keepa = KeepaProvider()
    spapi = None
    if check_restrictions and settings.sp_api_refresh_token:
        spapi = SPAPIProvider(seller_id=settings.sp_api_seller_id, marketplace=marketplace)
    hybrid = HybridProvider(keepa=keepa, spapi=spapi, seller_id=settings.sp_api_seller_id if spapi else None, marketplace=marketplace)

    try:
        products = await hybrid.get_products_enriched(asins_list, domain=domain, check_restrictions=check_restrictions, fetch_fees=True)

        results = []
        mkt = "amazon_mfn" if fulfillment_type == "mfn" else "amazon_fba"

        for asin in asins_list:
            p = products.get(asin)
            if not p:
                results.append({"ASIN": asin, "Status": "Not Found"})
                continue

            cost = cost_map.get(asin, 0)
            profit_result = None
            if p.buy_box_price and cost > 0:
                fee_fixed = p.fba_fulfillment_fee if mkt == "amazon_fba" else None
                try:
                    profit_result = compute_profit(
                        sale_price=p.buy_box_price, cost_price=cost, marketplace=mkt,
                        shipping_cost=shipping_cost, prep_cost=prep_cost,
                        fee_rate_override=p.referral_fee_pct, fee_fixed_override=fee_fixed,
                    )
                except Exception:
                    pass

            vel = None
            if p.sales_per_day and p.sales_per_day > 0:
                vel = compute_velocity_from_sales_per_day(p.sales_per_day)

            status = "Restricted" if p.can_sell is False else ("Matched" if p.title else "No Data")

            results.append({
                "ASIN": asin,
                "Title": (p.title or "")[:50],
                "Brand": p.brand or "",
                "Can Sell": "No" if p.can_sell is False else ("Yes" if p.can_sell else "?"),
                "Restriction": p.restriction_reason or "",
                "Buy Box": p.buy_box_price,
                "Cost": cost if cost > 0 else None,
                "Profit": round(profit_result.profit, 2) if profit_result else None,
                "ROI %": round(profit_result.roi * 100, 1) if profit_result else None,
                "Fees": round(profit_result.marketplace_fees, 2) if profit_result else None,
                "Monthly Sold": p.monthly_sold,
                "Sales/Day": round(p.sales_per_day, 2) if p.sales_per_day else None,
                "Velocity": vel.score if vel else None,
                "BSR": p.sales_rank,
                "Sellers": p.seller_count,
                "Rating": p.rating,
                "Reviews": p.review_count,
                "Status": status,
            })

        return results
    finally:
        await hybrid.close()


# ── UI ──

st.title("📦 Batch Flip — Product Analyzer")
st.caption("Keepa + SP-API | Profit, Restrictions, Velocity")

tab1, tab2 = st.tabs(["🔍 Single Analysis", "📋 Batch Analysis"])

# ── TAB 1: Single Analysis ──
with tab1:
    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Input")
        product_id = st.text_input("Product ID (ASIN, UPC, EAN)", value="B01MTB55WH", help="Ej: B0D1XD1ZV3")
        cost_price = st.number_input("Cost Price ($)", min_value=0.01, value=15.0, step=0.50)
        marketplace = st.selectbox("Marketplace", ["us", "ca", "mx", "uk", "de", "fr", "es", "it", "br", "au"])
        fulfillment_type = st.selectbox("Fulfillment", ["fba", "mfn"])
        prep_cost = st.number_input("Prep Cost ($)", min_value=0.0, value=0.0, step=0.25)
        shipping_cost = st.number_input("Shipping Cost ($)", min_value=0.0, value=0.0, step=0.50)
        check_restrictions = st.checkbox("Check Listing Restrictions (SP-API)", value=True)

        analyze_btn = st.button("Analyze", type="primary", use_container_width=True)

    with col2:
        if analyze_btn:
            with st.spinner("Analyzing..."):
                start = time.time()
                result, error = run_async(run_single_analysis(
                    product_id, cost_price, marketplace, fulfillment_type, prep_cost, shipping_cost, check_restrictions,
                ))
                elapsed = time.time() - start

            if error:
                st.error(f"Error: {error}")
            elif result:
                p = result["product"]
                pr = result["profit"]
                vel = result["velocity"]

                st.caption(f"Analysis completed in {elapsed:.1f}s")

                # Header con imagen y título
                hcol1, hcol2 = st.columns([1, 4])
                with hcol1:
                    if p.image_url:
                        st.image(p.image_url, width=100)
                with hcol2:
                    st.markdown(f"### {p.title or 'Unknown Product'}")
                    st.markdown(f"**{p.brand or ''}** | {p.category or ''} | ASIN: `{p.asin}`")

                # Restriction banner
                if p.can_sell is False:
                    st.error(f"⛔ **Cannot Sell** — {p.restriction_reason}: {p.restriction_message}")
                elif p.can_sell is True:
                    st.success("✅ **Can Sell** — No restrictions found")
                else:
                    st.warning("❓ Restriction status unknown (SP-API not checked)")

                # Metrics
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Buy Box", format_currency(p.buy_box_price))
                m2.metric("Profit", format_currency(pr.profit if pr else None), delta=f"{pr.roi*100:.0f}% ROI" if pr and pr.roi else None)
                m3.metric("Monthly Sold", format_number(p.monthly_sold))
                m4.metric("Velocity", f"{vel.score}/100" if vel else "—", delta=vel.estimated_days_to_sell if vel else None)

                # Detail tabs
                d1, d2, d3, d4 = st.tabs(["💰 Profit", "📊 Velocity", "🏪 Competition", "⭐ Reviews"])

                with d1:
                    if pr:
                        fc1, fc2 = st.columns(2)
                        with fc1:
                            st.markdown("**Profit Breakdown**")
                            st.write(f"- Sale Price: {format_currency(pr.sale_price)}")
                            st.write(f"- Cost: {format_currency(cost_price)}")
                            st.write(f"- Marketplace Fees: {format_currency(pr.marketplace_fees)}")
                            st.write(f"- Shipping: {format_currency(pr.shipping_cost)}")
                            st.write(f"- Prep: {format_currency(pr.prep_cost)}")
                            st.write(f"- Return Reserve: {format_currency(pr.return_reserve)}")
                            st.write(f"- **Net Profit: {format_currency(pr.profit)}**")
                        with fc2:
                            st.markdown("**Fees Detail**")
                            st.write(f"- Referral Fee: {format_currency(p.sp_api_referral_fee)} ({format_pct(p.referral_fee_pct * 100 if p.referral_fee_pct else None)})")
                            st.write(f"- FBA Fee: {format_currency(p.sp_api_fba_fee or p.fba_fulfillment_fee)}")
                            st.write(f"- SP-API Total: {format_currency(p.sp_api_total_fees)}")
                            st.write(f"- ROI: **{format_pct(pr.roi * 100)}**")
                            st.write(f"- Margin: **{format_pct(pr.margin * 100)}**")
                    else:
                        st.info("No profit calculation available (missing Buy Box price or cost)")

                with d2:
                    vc1, vc2 = st.columns(2)
                    with vc1:
                        st.write(f"- Monthly Sold: **{format_number(p.monthly_sold)}**")
                        st.write(f"- Sales/Day: **{format_number(p.sales_per_day)}**")
                        st.write(f"- Rank Drops 30d: **{format_number(p.sales_rank_drops_30)}**")
                    with vc2:
                        st.write(f"- BSR: **#{format_number(p.sales_rank)}**")
                        st.write(f"- Velocity Score: **{vel.score}/100**" if vel else "- Velocity: —")
                        st.write(f"- Est. Days to Sell: **{vel.estimated_days_to_sell}**" if vel else "")

                with d3:
                    cc1, cc2 = st.columns(2)
                    with cc1:
                        st.write(f"- Total Sellers: **{p.seller_count}**")
                        st.write(f"- New Offers: **{p.offer_count_new or '?'}**")
                        st.write(f"- Used Offers: **{p.offer_count_used or '?'}**")
                    with cc2:
                        st.write(f"- Amazon Sells: **{'Yes' if p.amazon_is_seller else 'No'}**")
                        st.write(f"- Amazon Buy Box: **{'Yes' if p.buy_box_is_amazon else 'No'}**")
                        st.write(f"- OOS% 90d: **{p.out_of_stock_pct_90 or '?'}%**")

                with d4:
                    st.write(f"- Rating: **{p.rating}** / 5.0" if p.rating else "- Rating: —")
                    st.write(f"- Reviews: **{format_number(p.review_count)}**")
                    st.write(f"- Trade-in Value: **{format_currency(p.trade_in_value)}**")
                    st.write(f"- List Price: **{format_currency(p.list_price)}**")

# ── TAB 2: Batch Analysis ──
with tab2:
    st.subheader("Batch Analysis")

    bcol1, bcol2 = st.columns([1, 3])

    with bcol1:
        st.markdown("**Settings**")
        b_marketplace = st.selectbox("Marketplace", ["us", "ca", "mx", "uk", "de"], key="b_mkt")
        b_fulfillment = st.selectbox("Fulfillment", ["fba", "mfn"], key="b_ful")
        b_prep = st.number_input("Prep Cost ($)", min_value=0.0, value=0.0, step=0.25, key="b_prep")
        b_ship = st.number_input("Shipping ($)", min_value=0.0, value=0.0, step=0.50, key="b_ship")
        b_restrictions = st.checkbox("Check Restrictions", value=True, key="b_restr")

        st.markdown("---")
        st.markdown("**Upload CSV/XLSX**")
        st.caption("Columns: ASIN (or UPC), Cost")
        uploaded_file = st.file_uploader("Choose file", type=["csv", "xlsx", "xls"])

        st.markdown("---")
        st.markdown("**Or paste ASINs**")
        asins_text = st.text_area("One ASIN per line (optionally ASIN,Cost)", height=150, placeholder="B0D1XD1ZV3,150\nB01MTB55WH,15\nB07FZ8S74R,20")
        default_cost = st.number_input("Default Cost ($)", min_value=0.01, value=10.0, step=1.0, key="b_cost")

        batch_btn = st.button("Run Batch", type="primary", use_container_width=True)

    with bcol2:
        if batch_btn:
            asins_list = []
            cost_map = {}

            # Parse from uploaded file
            if uploaded_file:
                from app.services.file_parser import parse_file
                import tempfile, os
                ext = os.path.splitext(uploaded_file.name)[1]
                with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                    tmp.write(uploaded_file.read())
                    tmp_path = tmp.name
                parsed = parse_file(tmp_path)
                os.unlink(tmp_path)

                for row in parsed.rows:
                    from app.services.file_parser import detect_id_type
                    id_type = detect_id_type(row.product_id)
                    if id_type == "asin":
                        asins_list.append(row.product_id)
                        if row.cost_price:
                            cost_map[row.product_id] = row.cost_price
                st.info(f"Parsed {len(asins_list)} ASINs from {uploaded_file.name}")

            # Parse from text
            elif asins_text.strip():
                for line in asins_text.strip().split("\n"):
                    parts = line.strip().split(",")
                    asin = parts[0].strip()
                    if asin:
                        asins_list.append(asin)
                        if len(parts) > 1:
                            try:
                                cost_map[asin] = float(parts[1].strip())
                            except ValueError:
                                pass

            if not asins_list:
                st.warning("No ASINs to analyze")
            else:
                # Set default cost for missing
                for a in asins_list:
                    if a not in cost_map:
                        cost_map[a] = default_cost

                with st.spinner(f"Analyzing {len(asins_list)} products..."):
                    start = time.time()
                    results = run_async(run_batch_analysis(
                        asins_list, cost_map, b_marketplace, b_fulfillment, b_prep, b_ship, b_restrictions,
                    ))
                    elapsed = time.time() - start

                st.caption(f"Completed {len(results)} products in {elapsed:.1f}s ({len(results)/elapsed:.1f} products/sec)")

                # Summary metrics
                matched = [r for r in results if r["Status"] == "Matched"]
                restricted = [r for r in results if r["Status"] == "Restricted"]
                profitable = [r for r in matched if r.get("Profit") and r["Profit"] > 0]

                sm1, sm2, sm3, sm4, sm5 = st.columns(5)
                sm1.metric("Total", len(results))
                sm2.metric("Matched", len(matched))
                sm3.metric("Restricted", len(restricted))
                sm4.metric("Profitable", len(profitable))
                avg_roi = sum(r["ROI %"] for r in profitable if r.get("ROI %")) / len(profitable) if profitable else 0
                sm5.metric("Avg ROI", format_pct(avg_roi))

                # Results table
                df = pd.DataFrame(results)

                # Color coding
                def color_row(row):
                    if row.get("Status") == "Restricted":
                        return ["background-color: #ffcccc"] * len(row)
                    elif row.get("Profit") and row["Profit"] > 0:
                        return ["background-color: #ccffcc"] * len(row)
                    elif row.get("Profit") and row["Profit"] <= 0:
                        return ["background-color: #ffffcc"] * len(row)
                    return [""] * len(row)

                styled = df.style.apply(color_row, axis=1)
                st.dataframe(styled, use_container_width=True, height=400)

                # Download CSV
                csv_data = df.to_csv(index=False)
                st.download_button(
                    "Download CSV",
                    csv_data,
                    file_name="batch_flip_results.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
