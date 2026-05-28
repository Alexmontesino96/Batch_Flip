"""Endpoints para batch jobs — todos protegidos con auth + ownership."""

import math
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import func, select
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

    # Map legacy fields to new dual fields
    fba_prep = req.fba_prep_cost or req.prep_cost_per_item
    fba_ship = req.fba_shipping_to_amazon or req.shipping_to_amazon

    job = Job(
        user_id=uuid.UUID(user["id"]),
        scan_mode=req.scan_mode,
        marketplace=req.marketplace,
        domain_id=MARKETPLACE_DOMAINS[req.marketplace],
        fulfillment_type=req.fulfillment_type,
        # Dual costs
        fba_prep_cost=fba_prep,
        fba_shipping_to_amazon=fba_ship,
        mfn_prep_cost=req.mfn_prep_cost,
        mfn_shipping_to_customer=req.mfn_shipping_to_customer,
        mfn_packaging_cost=req.mfn_packaging_cost,
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

    job.status = "processing"
    job.progress_phase = "resolving_ids"
    await db.commit()

    from app.worker.tasks import enqueue_job
    await enqueue_job(str(job_id))

    return {"message": "Job iniciado", "job_id": str(job_id), "scans_remaining": remaining - job.total_items}


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
    sort_by: str = "profit",
    profitable_only: bool = False,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user_with_db),
):
    """Obtener resultados paginados del job (requiere auth + ownership)."""
    await get_job_with_ownership(job_id, db, user["id"])

    query = select(JobItem).where(JobItem.job_id == job_id, JobItem.status == "matched")
    if profitable_only:
        query = query.where(JobItem.profit > 0)

    sort_map = {
        "profit": JobItem.profit.desc().nulls_last(),
        "roi": JobItem.roi_pct.desc().nulls_last(),
        "rank": JobItem.sales_rank.asc().nulls_last(),
        "velocity": JobItem.velocity_score.desc().nulls_last(),
        "row": JobItem.input_row.asc(),
    }
    query = query.order_by(sort_map.get(sort_by, sort_map["profit"]))

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
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user_with_db),
):
    """Exportar resultados a CSV (requiere auth + ownership)."""
    await get_job_with_ownership(job_id, db, user["id"])

    from app.services.export_service import export_job_csv
    csv_path = await export_job_csv(job_id, db)

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
