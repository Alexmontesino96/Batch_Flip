"""Endpoints para batch jobs — todos protegidos con auth + ownership."""

import math
import os
import uuid
from typing import Literal
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_db, get_job_with_ownership, validate_seller_connection_ownership
from app.config import settings
from app.core.auth import get_current_user_with_db, upsert_user
from app.models.job import MARKETPLACE_DOMAINS, Job
from app.models.job_item import JobItem
from app.schemas.job import (
    CreateJobRequest,
    JobItemResponse,
    JobResponse,
    JobResultsResponse,
    JobStatsResponse,
    UploadResponse,
)
from app.services.file_parser import parse_file

router = APIRouter(prefix="/jobs", tags=["jobs"])

# Upload limits
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".tsv", ".tab"}


def _build_filtered_query(
    job_id: uuid.UUID,
    min_profit: float | None = None,
    max_profit: float | None = None,
    min_roi: float | None = None,
    min_fba_profit: float | None = None,
    min_mfn_profit: float | None = None,
    max_bsr: int | None = None,
    max_sellers: int | None = None,
    min_velocity: int | None = None,
    min_rating: float | None = None,
    min_monthly_sold: int | None = None,
    can_sell: bool | None = None,
    fba_eligible: bool | None = None,
    hide_amazon_seller: bool = False,
    hide_restricted: bool = False,
    status: str | None = None,
    best_scenario: str | None = None,
    search: str | None = None,
):
    """Construye un SELECT sobre JobItem aplicando los filtros comunes a results y export."""
    query = select(JobItem).where(JobItem.job_id == job_id)

    if status is not None:
        query = query.where(JobItem.status == status)
    if hide_restricted:
        query = query.where(JobItem.status != "restricted")

    if min_profit is not None:
        query = query.where(JobItem.profit >= min_profit)
    if max_profit is not None:
        query = query.where(JobItem.profit <= max_profit)
    if min_roi is not None:
        query = query.where(JobItem.roi_pct >= min_roi)
    if min_fba_profit is not None:
        query = query.where(JobItem.fba_profit >= min_fba_profit)
    if min_mfn_profit is not None:
        query = query.where(JobItem.mfn_profit >= min_mfn_profit)
    if max_bsr is not None:
        query = query.where(JobItem.sales_rank <= max_bsr)
    if max_sellers is not None:
        query = query.where(JobItem.seller_count <= max_sellers)
    if min_velocity is not None:
        query = query.where(JobItem.velocity_score >= min_velocity)
    if min_rating is not None:
        query = query.where(JobItem.rating >= min_rating)
    if min_monthly_sold is not None:
        query = query.where(JobItem.monthly_sold >= min_monthly_sold)

    if can_sell is not None:
        query = query.where(JobItem.can_sell == can_sell)
    if fba_eligible is not None:
        query = query.where(JobItem.fba_eligible == fba_eligible)
    if hide_amazon_seller:
        query = query.where(JobItem.amazon_is_seller.is_(False))

    if best_scenario is not None:
        query = query.where(JobItem.best_scenario == best_scenario)
    if search is not None:
        term = f"%{search}%"
        query = query.where(
            or_(
                JobItem.title.ilike(term),
                JobItem.brand.ilike(term),
                JobItem.asin.ilike(term),
            )
        )

    return query


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(
    req: CreateJobRequest,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user_with_db),
):
    """Crear un nuevo batch job (requiere autenticación)."""
    if req.marketplace not in MARKETPLACE_DOMAINS:
        raise HTTPException(400, f"Marketplace inválido. Opciones: {list(MARKETPLACE_DOMAINS.keys())}")

    # Validar ownership de seller_connection
    await validate_seller_connection_ownership(req.seller_connection_id, user["id"], db)

    # Si se provee cost_profile_id, cargar el perfil y copiar los costos
    if req.cost_profile_id is not None:
        from app.models.cost_profile import CostProfile
        profile = await db.get(CostProfile, req.cost_profile_id)
        if not profile:
            raise HTTPException(404, "Perfil de costos no encontrado")
        if str(profile.user_id) != user["id"]:
            raise HTTPException(403, "El perfil de costos no pertenece a este usuario")
        fba_prep = float(profile.fba_prep_cost)
        fba_ship = float(profile.fba_shipping_to_amazon)
        mfn_prep = float(profile.mfn_prep_cost)
        mfn_ship_customer = float(profile.mfn_shipping_to_customer)
        mfn_pack = float(profile.mfn_packaging_cost)
    else:
        # Map legacy fields to new dual fields
        fba_prep = req.fba_prep_cost or req.prep_cost_per_item
        fba_ship = req.fba_shipping_to_amazon or req.shipping_to_amazon
        mfn_prep = req.mfn_prep_cost
        mfn_ship_customer = req.mfn_shipping_to_customer
        mfn_pack = req.mfn_packaging_cost

    job = Job(
        user_id=uuid.UUID(user["id"]),
        scan_mode=req.scan_mode,
        marketplace=req.marketplace,
        domain_id=MARKETPLACE_DOMAINS[req.marketplace],
        fulfillment_type=req.fulfillment_type,
        # Dual costs
        fba_prep_cost=fba_prep,
        fba_shipping_to_amazon=fba_ship,
        mfn_prep_cost=mfn_prep,
        mfn_shipping_to_customer=mfn_ship_customer,
        mfn_packaging_cost=mfn_pack,
        # Legacy
        prep_cost_per_item=req.prep_cost_per_item,
        shipping_to_amazon=req.shipping_to_amazon,
        # SP-API
        seller_connection_id=req.seller_connection_id,
        check_restrictions=req.check_restrictions,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


@router.post("/{job_id}/upload", response_model=UploadResponse)
async def upload_file(
    job_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user_with_db),
):
    """Upload archivo CSV/XLSX para un job (requiere auth + ownership)."""
    job = await get_job_with_ownership(job_id, db, user["id"])

    if job.status not in ("pending", "uploading"):
        raise HTTPException(400, f"Job en estado '{job.status}', no se puede subir archivo")

    # Validar extensión
    ext = Path(file.filename or "file.csv").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Formato no permitido. Permitidos: {ALLOWED_EXTENSIONS}")

    # Validar tamaño (leer en chunks para no cargar todo en memoria)
    os.makedirs(settings.upload_dir, exist_ok=True)
    file_name = f"{job_id}{ext}"
    file_path = os.path.join(settings.upload_dir, file_name)

    total_size = 0
    with open(file_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):  # 1MB chunks
            total_size += len(chunk)
            if total_size > MAX_UPLOAD_SIZE:
                f.close()
                os.remove(file_path)
                raise HTTPException(413, f"Archivo demasiado grande. Máximo: {MAX_UPLOAD_SIZE // (1024*1024)} MB")
            f.write(chunk)

    # Parsear archivo
    try:
        parsed = parse_file(file_path)
    except Exception as e:
        os.remove(file_path)  # Limpiar archivo huérfano
        raise HTTPException(400, f"Error parseando archivo: {str(e)[:200]}")

    # Actualizar job
    job.status = "uploading"
    job.file_name = file.filename
    job.file_path = file_path
    job.file_size_bytes = total_size
    job.total_items = parsed.total_rows
    job.detected_id_column = parsed.id_column
    job.detected_cost_column = parsed.cost_column
    job.detected_id_type = parsed.detected_id_type

    items = [
        JobItem(
            job_id=job_id,
            input_row=row.row_number,
            input_id=row.product_id,
            input_id_type=row.id_type,
            cost_price=row.cost_price,
        )
        for row in parsed.rows
    ]
    db.add_all(items)
    await db.commit()
    await db.refresh(job)

    return UploadResponse(
        total_items=parsed.total_rows,
        detected_id_type=parsed.detected_id_type,
        detected_id_column=parsed.id_column,
        detected_cost_column=parsed.cost_column,
        warnings=parsed.warnings,
    )


@router.post("/{job_id}/start")
async def start_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user_with_db),
):
    """Iniciar procesamiento del job (requiere auth + ownership + rate limit)."""
    job = await get_job_with_ownership(job_id, db, user["id"])

    if job.total_items == 0:
        raise HTTPException(400, "Sube un archivo primero")
    if job.status not in ("uploading", "pending"):
        raise HTTPException(400, f"Job en estado '{job.status}', no se puede iniciar")

    # Rate limiting por plan
    from app.core.auth import upsert_user
    user_row = await upsert_user(db, user["id"], user["email"])
    remaining = user_row.scans_limit_month - user_row.scans_used_month
    if job.total_items > remaining:
        raise HTTPException(
            429,
            f"Límite mensual: {user_row.scans_limit_month} items (plan {user_row.plan}). "
            f"Usados: {user_row.scans_used_month}. Disponibles: {remaining}. Job necesita: {job.total_items}."
        )

    # Reservar scans
    user_row.scans_used_month += job.total_items

    # Encolar en PG queue — el polling worker lo tomará
    from datetime import datetime, timezone
    job.status = "queued"
    job.queued_at = datetime.now(timezone.utc)
    job.locked_by = None
    job.locked_at = None
    await db.commit()

    return {"message": "Job enqueued", "job_id": str(job_id), "scans_remaining": remaining - job.total_items}


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user_with_db),
):
    """Obtener status de un job (requiere auth + ownership)."""
    job = await get_job_with_ownership(job_id, db, user["id"])
    return job


@router.get("/{job_id}/results", response_model=JobResultsResponse)
async def get_results(
    job_id: uuid.UUID,
    page: int = 1,
    page_size: int = 50,
    sort_by: Literal[
        "profit", "fba_profit", "mfn_profit", "roi", "fba_roi", "mfn_roi",
        "rank", "velocity", "monthly_sold", "sellers", "rating", "reviews",
        "buy_box", "cost", "row",
    ] = "profit",
    sort_order: Literal["asc", "desc"] = "desc",
    # Numeric range filters
    min_profit: float | None = Query(default=None),
    max_profit: float | None = Query(default=None),
    min_roi: float | None = Query(default=None),
    min_fba_profit: float | None = Query(default=None),
    min_mfn_profit: float | None = Query(default=None),
    max_bsr: int | None = Query(default=None),
    max_sellers: int | None = Query(default=None),
    min_velocity: int | None = Query(default=None),
    min_rating: float | None = Query(default=None),
    min_monthly_sold: int | None = Query(default=None),
    # Boolean filters
    can_sell: bool | None = Query(default=None),
    fba_eligible: bool | None = Query(default=None),
    hide_amazon_seller: bool = Query(default=False),
    hide_restricted: bool = Query(default=False),
    # String filters
    status: str | None = Query(default=None),
    best_scenario: str | None = Query(default=None),
    search: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user_with_db),
):
    """Obtener resultados paginados del job (requiere auth + ownership)."""
    await get_job_with_ownership(job_id, db, user["id"])

    query = _build_filtered_query(
        job_id=job_id,
        min_profit=min_profit,
        max_profit=max_profit,
        min_roi=min_roi,
        min_fba_profit=min_fba_profit,
        min_mfn_profit=min_mfn_profit,
        max_bsr=max_bsr,
        max_sellers=max_sellers,
        min_velocity=min_velocity,
        min_rating=min_rating,
        min_monthly_sold=min_monthly_sold,
        can_sell=can_sell,
        fba_eligible=fba_eligible,
        hide_amazon_seller=hide_amazon_seller,
        hide_restricted=hide_restricted,
        status=status,
        best_scenario=best_scenario,
        search=search,
    )

    # Build sort expression
    sort_map = {
        "profit": JobItem.profit,
        "fba_profit": JobItem.fba_profit,
        "mfn_profit": JobItem.mfn_profit,
        "roi": JobItem.roi_pct,
        "fba_roi": JobItem.fba_roi_pct,
        "mfn_roi": JobItem.mfn_roi_pct,
        "rank": JobItem.sales_rank,
        "velocity": JobItem.velocity_score,
        "monthly_sold": JobItem.monthly_sold,
        "sellers": JobItem.seller_count,
        "rating": JobItem.rating,
        "reviews": JobItem.review_count,
        "buy_box": JobItem.buy_box_price,
        "cost": JobItem.cost_price,
        "row": JobItem.input_row,
    }
    sort_col = sort_map.get(sort_by, JobItem.profit)
    if sort_order == "asc":
        order_expr = sort_col.asc().nulls_last()
    else:
        order_expr = sort_col.desc().nulls_last()
    query = query.order_by(order_expr)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()

    return JobResultsResponse(
        items=[JobItemResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 0,
    )


@router.get("/{job_id}/results/stats", response_model=JobStatsResponse)
async def get_stats(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user_with_db),
):
    """Resumen estadístico del job (requiere auth + ownership)."""
    job = await get_job_with_ownership(job_id, db, user["id"])

    result = await db.execute(select(JobItem).where(JobItem.job_id == job_id))
    job_items = result.scalars().all()
    matched_items = [item for item in job_items if item.status == "matched"]
    restricted_items = [item for item in job_items if item.status == "restricted"]
    not_found_items = [item for item in job_items if item.status == "not_found"]
    error_items = [item for item in job_items if item.status == "error"]

    profitable = [i for i in matched_items if i.profit and i.profit > 0]
    rois = [float(i.roi_pct) for i in matched_items if i.roi_pct is not None]
    profits = [float(i.profit) for i in matched_items if i.profit is not None]

    best_roi_item = max(matched_items, key=lambda i: float(i.roi_pct or 0), default=None)
    best_profit_item = max(matched_items, key=lambda i: float(i.profit or 0), default=None)

    return JobStatsResponse(
        total_items=job.total_items,
        matched_items=len(matched_items),
        restricted_items=len(restricted_items),
        not_found_items=len(not_found_items),
        profitable_items=len(profitable),
        error_items=len(error_items),
        avg_roi=round(sum(rois) / len(rois), 2) if rois else None,
        avg_profit=round(sum(profits) / len(profits), 2) if profits else None,
        total_profit=round(sum(profits), 2) if profits else None,
        best_roi_asin=best_roi_item.asin if best_roi_item else None,
        best_profit_asin=best_profit_item.asin if best_profit_item else None,
    )


@router.get("/{job_id}/export")
async def export_job(
    job_id: uuid.UUID,
    # Numeric range filters
    min_profit: float | None = Query(default=None),
    max_profit: float | None = Query(default=None),
    min_roi: float | None = Query(default=None),
    min_fba_profit: float | None = Query(default=None),
    min_mfn_profit: float | None = Query(default=None),
    max_bsr: int | None = Query(default=None),
    max_sellers: int | None = Query(default=None),
    min_velocity: int | None = Query(default=None),
    min_rating: float | None = Query(default=None),
    min_monthly_sold: int | None = Query(default=None),
    # Boolean filters
    can_sell: bool | None = Query(default=None),
    fba_eligible: bool | None = Query(default=None),
    hide_amazon_seller: bool = Query(default=False),
    hide_restricted: bool = Query(default=False),
    # String filters
    status: str | None = Query(default=None),
    best_scenario: str | None = Query(default=None),
    search: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user_with_db),
):
    """Exportar resultados filtrados a CSV (requiere auth + ownership)."""
    await get_job_with_ownership(job_id, db, user["id"])

    query = _build_filtered_query(
        job_id=job_id,
        min_profit=min_profit,
        max_profit=max_profit,
        min_roi=min_roi,
        min_fba_profit=min_fba_profit,
        min_mfn_profit=min_mfn_profit,
        max_bsr=max_bsr,
        max_sellers=max_sellers,
        min_velocity=min_velocity,
        min_rating=min_rating,
        min_monthly_sold=min_monthly_sold,
        can_sell=can_sell,
        fba_eligible=fba_eligible,
        hide_amazon_seller=hide_amazon_seller,
        hide_restricted=hide_restricted,
        status=status,
        best_scenario=best_scenario,
        search=search,
    ).order_by(JobItem.input_row)

    result = await db.execute(query)
    items = result.scalars().all()

    from app.services.export_service import export_job_csv
    csv_path = await export_job_csv(job_id, db, items=items)

    from fastapi.responses import FileResponse
    return FileResponse(csv_path, media_type="text/csv", filename=f"batchflip_{job_id}.csv")


@router.delete("/{job_id}")
async def delete_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user_with_db),
):
    """Eliminar un job y sus resultados (requiere auth + ownership)."""
    job = await get_job_with_ownership(job_id, db, user["id"])

    if job.file_path and os.path.exists(job.file_path):
        os.remove(job.file_path)

    await db.delete(job)
    await db.commit()
    return {"message": "Job eliminado"}


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user_with_db),
):
    """Listar jobs del usuario autenticado."""
    query = (
        select(Job)
        .where(Job.user_id == uuid.UUID(user["id"]))
        .order_by(Job.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    return result.scalars().all()
