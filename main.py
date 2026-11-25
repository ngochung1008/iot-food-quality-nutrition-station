#!/usr/bin/env python3
"""Root launcher khởi chạy toàn bộ Trạm Tiếp Nhận & Kiểm Định Thực Phẩm AI.

Chạy trực tiếp từ thư mục gốc:
    python main.py
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from backend.core.config import settings


def get_lan_ipv4_addresses() -> list[str]:
    """Tự động thu thập toàn bộ địa chỉ IPv4 mạng LAN của máy qua socket."""
    ips: list[str] = []
    seen: set[str] = set()

    def _add(ip: str) -> None:
        clean = ip.strip()
        if not clean or clean.startswith("127.") or clean == "0.0.0.0" or clean in seen:
            return
        seen.add(clean)
        ips.append(clean)

    # 1. Xác định IP tuyến mặc định ra mạng LAN/Internet
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.5)
            sock.connect(("8.8.8.8", 80))
            _add(sock.getsockname()[0])
    except Exception:
        pass

    # 2. Thu thập tất cả interface IPv4 gắn với hostname
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_STREAM):
            _add(info[4][0])
    except Exception:
        pass

    return ips


def print_startup_banner(lan_ips: list[str]) -> None:
    """In khung thông tin khởi động kèm URL Local, LAN và API Docs."""
    port = settings.port
    mode_label = "MOCK (Giả lập Windows/Dev)" if settings.mock_hardware else "PRODUCTION (Phần cứng Pi 4)"
    border = "=" * 74
    print(border)
    print("  FRESH KITCHEN AI — TRẠM TIẾP NHẬN & KIỂM ĐỊNH DINH DƯỠNG THỰC PHẨM")
    print(border)
    print(f"  Trạm vận hành : {settings.station_name} ({settings.station_id})")
    print(f"  Phần cứng     : MOCK_HARDWARE={settings.mock_hardware} -> {mode_label}")
    print(f"  Chiến lược AI : {settings.ai_strategy} | Ngưỡng ổn định: {settings.stability_hold_s}s")
    print("-" * 74)
    print(f"  Truy cập Local     : http://127.0.0.1:{port}")
    if lan_ips:
        for idx, ip in enumerate(lan_ips):
            prefix = "  Truy cập LAN       :" if idx == 0 else "                      "
            print(f"{prefix} http://{ip}:{port}")
    else:
        print(f"  Truy cập LAN       : http://<LAN-IP>:{port} (chưa phát hiện IP mạng LAN)")
    print(f"  Tài liệu API Docs  : http://127.0.0.1:{port}/docs")
    print(border)
    print("  Nhấn Ctrl+C để dừng trạm an toàn (tự động giải phóng Camera & GPIO).")
    print(border)


def main() -> None:
    import uvicorn

    lan_ips = get_lan_ipv4_addresses()
    print_startup_banner(lan_ips)
    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info",
        timeout_graceful_shutdown=1,
    )


if __name__ == "__main__":
    main()
