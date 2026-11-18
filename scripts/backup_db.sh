#!/bin/bash
# ==============================================================================
# Script sao lưu cơ sở dữ liệu SQLite tự động
# ==============================================================================
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_FILE="$PROJECT_DIR/backend/data/nutrition_station.db"
BACKUP_DIR="$PROJECT_DIR/backups"
STAMP="$(date +%Y%m%d_%H%M%S)"

mkdir -p "$BACKUP_DIR"

if [ ! -f "$DB_FILE" ]; then
    echo "[BACKUP] Chưa tìm thấy file DB tại $DB_FILE"
    exit 1
fi

OUT_FILE="$BACKUP_DIR/nutrition_station_${STAMP}.db"
sqlite3 "$DB_FILE" ".backup '$OUT_FILE'"
echo "[BACKUP] Đã sao lưu thành công: $OUT_FILE"

# Giữ lại 30 bản backup gần nhất
ls -1t "$BACKUP_DIR"/nutrition_station_*.db 2>/dev/null | tail -n +31 | xargs -r rm -f
