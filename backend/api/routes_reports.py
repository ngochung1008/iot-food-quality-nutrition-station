"""Endpoints lịch sử nhập kho, thống kê dinh dưỡng ngày/tuần và xuất báo cáo CSV/Excel."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from backend.core.security import require_admin

from backend.database.crud import (
    delete_intake_log,
    get_daily_analytics,
    get_summary_kpis,
    list_intake_logs,
)
from backend.services.export_service import export_logs_to_csv, export_logs_to_xlsx

router = APIRouter(prefix="/api", tags=["Reports & Audit Logs"])


@router.get("/logs")
def get_intake_logs(
    limit: int = Query(default=100, ge=1, le=1000),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    quality_status: str | None = Query(default=None),
):
    """Lấy danh sách lịch sử các phiên cân & kiểm định thực phẩm."""
    return list_intake_logs(
        limit=limit,
        date_from=date_from,
        date_to=date_to,
        quality_status=quality_status,
    )


@router.delete("/logs/{log_id}", dependencies=[Depends(require_admin)])
def remove_intake_log(log_id: str):
    """Xóa một phiếu nhập kho theo ID."""
    ok = delete_intake_log(log_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiếu nhập kho.")
    return {"ok": True, "deleted_id": log_id}


@router.get("/analytics")
def get_analytics(days: int = Query(default=14, ge=1, le=90)):
    """Trả về chuỗi thống kê theo ngày và KPI tổng hợp theo tuần/ngày."""
    return {
        "daily": get_daily_analytics(days=days),
        "summary": get_summary_kpis(days=min(days, 7)),
    }


@router.get("/reports/export.csv")
def export_csv(
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    quality_status: str | None = Query(default=None),
):
    """Xuất báo cáo lịch sử nhập kho & dinh dưỡng định dạng CSV (UTF-8 BOM)."""
    logs = list_intake_logs(limit=1000, date_from=date_from, date_to=date_to, quality_status=quality_status)
    payload = export_logs_to_csv(logs)
    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="bao_cao_nhap_kho_dinh_duong.csv"'},
    )


@router.get("/reports/export.xlsx")
def export_xlsx(
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    quality_status: str | None = Query(default=None),
):
    """Xuất báo cáo Excel .xlsx gồm chi tiết lô cân và bảng tổng hợp dinh dưỡng."""
    logs = list_intake_logs(limit=1000, date_from=date_from, date_to=date_to, quality_status=quality_status)
    summary = get_summary_kpis(days=7)
    payload = export_logs_to_xlsx(logs, summary=summary)
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="bao_cao_nhap_kho_dinh_duong.xlsx"'},
    )
