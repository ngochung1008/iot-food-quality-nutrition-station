#!/bin/bash
# ==============================================================================
# Tự động mở Chromium ở chế độ Kiosk toàn màn hình cho màn hình cảm ứng bếp ăn
# ==============================================================================

if command -v xset &> /dev/null; then
    xset s noblank
    xset s off
    xset -dpms
fi

TARGET_URL="http://localhost:8000"
echo "[KIOSK] Đang chờ Backend FastAPI tại $TARGET_URL..."

for i in {1..30}; do
    if curl -s "$TARGET_URL/health" | grep -q '"ok"'; then
        echo "[KIOSK] Backend sẵn sàng sau ${i}s."
        break
    fi
    sleep 1
done

sed -i 's/"exited_cleanly":false/"exited_cleanly":true/' ~/.config/chromium/Default/Preferences 2>/dev/null || true
sed -i 's/"exit_type":"Crashed"/"exit_type":"Normal"/' ~/.config/chromium/Default/Preferences 2>/dev/null || true

exec chromium-browser \
    --noerrdialogs \
    --disable-infobars \
    --kiosk \
    --incognito \
    --disable-pinch \
    --overscroll-history-navigation=0 \
    --disable-translate \
    --autoplay-policy=no-user-gesture-required \
    "$TARGET_URL"
