"""Dịch vụ xuất báo cáo nhập kho & dinh dưỡng ra CSV (UTF-8 BOM) và Excel (.xlsx)."""

from __future__ import annotations

import csv
import io
from typing import Any


def export_logs_to_csv(logs: list[dict[str, Any]]) -> bytes:
    """Xuất danh sách phiếu kiểm định sang CSV có UTF-8 BOM để mở chuẩn tiếng Việt trên Excel."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Mã phiếu",
        "Thời gian (UTC)",
        "Ngày",
        "Mã thực phẩm",
        "Tên thực phẩm",
        "Nhóm thực phẩm",
        "Khối lượng cân (g)",
        "Phần ăn được (g)",
        "Chất lượng",
        "Độ tin cậy (%)",
        "Năng lượng (kcal)",
        "Protein (g)",
        "Lipid / Chất béo (g)",
        "Carbohydrate (g)",
        "Chất xơ (g)",
        "Canxi (mg)",
        "Sắt (mg)",
        "Vitamin C (mg)",
        "Người xác nhận",
        "Ghi chú",
    ])

    for row in logs:
        writer.writerow([
            row.get("batch_code", ""),
            row.get("timestamp", ""),
            row.get("local_date", ""),
            row.get("class_name", ""),
            row.get("food_name_vi", ""),
            row.get("food_group", ""),
            row.get("weight_gram", 0),
            row.get("edible_gram", 0),
            row.get("quality_status", ""),
            round(float(row.get("confidence", 0)) * 100, 1),
            row.get("energy_kcal", 0),
            row.get("protein_g", 0),
            row.get("fat_g", 0),
            row.get("carbohydrate_g", 0),
            row.get("fiber_g", 0),
            row.get("calcium_mg", 0),
            row.get("iron_mg", 0),
            row.get("vitamin_c_mg", 0),
            row.get("confirmed_by", ""),
            row.get("note", ""),
        ])

    return ("\ufeff" + output.getvalue()).encode("utf-8")


def export_logs_to_xlsx(logs: list[dict[str, Any]], summary: dict[str, Any] | None = None) -> bytes:
    """Xuất báo cáo Excel .xlsx định dạng chuyên nghiệp bằng xlsxwriter."""
    import xlsxwriter

    buf = io.BytesIO()
    workbook = xlsxwriter.Workbook(buf, {"in_memory": True})

    # Sheet 1: Chi tiết phiếu nhập kho
    ws = workbook.add_worksheet("Nhat_Ky_Nhap_Kho")
    header_fmt = workbook.add_format({
        "bold": True,
        "bg_color": "#0F766E",
        "font_color": "#FFFFFF",
        "border": 1,
        "align": "center",
        "valign": "vcenter",
    })
    cell_fmt = workbook.add_format({"border": 1, "valign": "vcenter"})
    num_fmt = workbook.add_format({"border": 1, "num_format": "#,##0.0", "valign": "vcenter"})

    headers = [
        "Mã phiếu", "Ngày", "Thời gian", "Tên thực phẩm", "Nhóm",
        "Khối lượng (g)", "Ăn được (g)", "Chất lượng", "Tin cậy (%)",
        "Kcal", "Protein (g)", "Lipid (g)", "Carb (g)", "Xơ (g)", "Ghi chú",
    ]
    for col_idx, h in enumerate(headers):
        ws.write(0, col_idx, h, header_fmt)
        ws.set_column(col_idx, col_idx, 16)
    ws.set_row(0, 26)

    for row_idx, item in enumerate(logs, start=1):
        ws.write(row_idx, 0, item.get("batch_code", ""), cell_fmt)
        ws.write(row_idx, 1, item.get("local_date", ""), cell_fmt)
        ws.write(row_idx, 2, item.get("timestamp", ""), cell_fmt)
        ws.write(row_idx, 3, item.get("food_name_vi", ""), cell_fmt)
        ws.write(row_idx, 4, item.get("food_group", ""), cell_fmt)
        ws.write_number(row_idx, 5, float(item.get("weight_gram", 0)), num_fmt)
        ws.write_number(row_idx, 6, float(item.get("edible_gram", 0)), num_fmt)
        ws.write(row_idx, 7, item.get("quality_status", ""), cell_fmt)
        ws.write_number(row_idx, 8, round(float(item.get("confidence", 0)) * 100, 1), num_fmt)
        ws.write_number(row_idx, 9, float(item.get("energy_kcal", 0)), num_fmt)
        ws.write_number(row_idx, 10, float(item.get("protein_g", 0)), num_fmt)
        ws.write_number(row_idx, 11, float(item.get("fat_g", 0)), num_fmt)
        ws.write_number(row_idx, 12, float(item.get("carbohydrate_g", 0)), num_fmt)
        ws.write_number(row_idx, 13, float(item.get("fiber_g", 0)), num_fmt)
        ws.write(row_idx, 14, item.get("note", ""), cell_fmt)

    # Sheet 2: Tổng hợp nếu có
    if summary:
        ws2 = workbook.add_worksheet("Tong_Hop")
        ws2.write(0, 0, "Chỉ tiêu thống kê", header_fmt)
        ws2.write(0, 1, "Giá trị", header_fmt)
        ws2.set_column(0, 0, 32)
        ws2.set_column(1, 1, 22)
        period = summary.get("period_summary", {})
        rows_sum = [
            ("Tổng số lô kiểm định", period.get("total_batches", 0)),
            ("Số lô đạt chuẩn (FRESH)", period.get("fresh_count", 0)),
            ("Số lô cần kiểm tra (WARNING)", period.get("warning_count", 0)),
            ("Số lô từ chối (REJECTED)", period.get("rejected_count", 0)),
            ("Tổng khối lượng cân (kg)", period.get("total_weight_kg", 0)),
            ("Khối lượng nhập kho hợp lệ (kg)", period.get("accepted_weight_kg", 0)),
            ("Tổng năng lượng nhập kho (kcal)", period.get("total_kcal", 0)),
            ("Tổng Protein (g)", period.get("total_protein_g", 0)),
            ("Tổng Lipid (g)", period.get("total_fat_g", 0)),
            ("Tổng Carbohydrate (g)", period.get("total_carb_g", 0)),
        ]
        for idx, (k, v) in enumerate(rows_sum, start=1):
            ws2.write(idx, 0, k, cell_fmt)
            ws2.write_number(idx, 1, float(v or 0), num_fmt)

    workbook.close()
    return buf.getvalue()
