"""Entry point chính của Backend FastAPI + WebSocket + MJPEG Video Feed."""

from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend.api.routes_auth import router as auth_router
from backend.api.routes_foods import router as foods_router
from backend.api.routes_hardware import router as hardware_router
from backend.api.routes_kitchen import router as kitchen_router
from backend.api.routes_reports import router as reports_router
from backend.api.routes_station import router as station_router
from backend.core.config import settings
from backend.core.logger import logger
from backend.services.station_service import station_service

SHUTDOWN_EVENT = threading.Event()


def _install_uvicorn_exit_hook() -> None:
    """Đặt SHUTDOWN_EVENT và đóng kết nối streaming ngay tức thì khi nhấn Ctrl+C."""
    try:
        import uvicorn

        orig_handle_exit = uvicorn.Server.handle_exit
        if getattr(orig_handle_exit, "_fk_wrapped", False):
            return

        def _handle_exit_with_event(self, sig, frame):
            SHUTDOWN_EVENT.set()
            station_service.ws_hub.close_all()
            return orig_handle_exit(self, sig, frame)

        _handle_exit_with_event._fk_wrapped = True  # type: ignore[attr-defined]
        uvicorn.Server.handle_exit = _handle_exit_with_event  # type: ignore[method-assign]
    except Exception:
        pass


_install_uvicorn_exit_hook()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Khởi động và dọn dẹp sạch phần cứng + AI khi bật/tắt FastAPI server."""
    SHUTDOWN_EVENT.clear()
    station_service.ws_hub.set_loop(asyncio.get_running_loop())
    station_service.start()
    yield
    SHUTDOWN_EVENT.set()
    station_service.ws_hub.close_all()
    station_service.stop()


app = FastAPI(
    title="Trạm Kiểm Định Chất Lượng & Định Lượng Dinh Dưỡng Thực Phẩm AI",
    description="Hệ thống Edge AI (YOLO26n NCNN) + Loadcell HX711 + LCD I2C chạy trên Raspberry Pi 4",
    version="2.0.0",
    lifespan=lifespan,
)

# Cho phép Frontend tách biệt hoặc kết nối LAN trên bếp ăn truy cập
origins = [o.strip() for o in settings.cors_origins.split(",")] if settings.cors_origins != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đăng ký REST API routers
app.include_router(auth_router)
app.include_router(kitchen_router)
app.include_router(station_router)
app.include_router(hardware_router)
app.include_router(foods_router)
app.include_router(reports_router)

# Phục vụ ảnh chụp kiểm định và static assets của Frontend tách biệt
app.mount("/captures", StaticFiles(directory=str(settings.capture_dir)), name="captures")
if settings.frontend_public_dir.exists():
    app.mount("/public", StaticFiles(directory=str(settings.frontend_public_dir)), name="public")
if settings.frontend_dir.exists():
    for sub in ("assets", "components", "pages", "services"):
        sub_dir = settings.frontend_dir / sub
        if sub_dir.exists():
            app.mount(f"/{sub}", StaticFiles(directory=str(sub_dir)), name=f"frontend_{sub}")


@app.get("/main.js")
def serve_frontend_main():
    return FileResponse(settings.frontend_dir / "main.js", media_type="application/javascript")


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "mock_hardware": settings.mock_hardware,
        "station_id": settings.station_id,
    }


@app.get("/video_feed")
async def video_feed(request: Request):
    """Luồng video MJPEG trực tiếp kèm overlay bounding box từ CameraManager."""

    async def frame_generator():
        cam = station_service.camera
        if cam:
            cam.acquire_stream()
        try:
            while True:
                if SHUTDOWN_EVENT.is_set() or await request.is_disconnected():
                    break
                if cam:
                    chunk = cam.mjpeg_bytes()
                    if chunk:
                        yield (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n\r\n" + chunk + b"\r\n"
                        )
                await asyncio.sleep(0.04)
        except (asyncio.CancelledError, GeneratorExit):
            return
        finally:
            if cam:
                cam.release_stream()

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.websocket("/ws/station")
async def websocket_station(websocket: WebSocket):
    """Kênh WebSocket real-time đẩy trọng lượng, trạng thái State Machine & kết quả AI."""
    await websocket.accept()
    station_service.ws_hub.add(websocket)
    try:
        if station_service.state_machine:
            await websocket.send_json({
                "event": "snapshot",
                "data": station_service.state_machine.snapshot(),
            })
        while not SHUTDOWN_EVENT.is_set():
            # Giữ kết nối mở và nhận lệnh ping/keepalive từ client nếu có
            await websocket.receive_text()
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception as exc:
        logger.debug(f"[WS] Ngắt kết nối client: {exc}")
    finally:
        station_service.ws_hub.remove(websocket)


@app.get("/")
def serve_spa_root():
    """Phục vụ giao diện Web Dashboard thương mại."""
    return FileResponse(settings.frontend_dir / "index.html")


if __name__ == "__main__":
    import uvicorn

    # Không bật reload khi chạy phần cứng thật để tránh 2 tiến trình tranh chấp GPIO/Camera
    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info",
        timeout_graceful_shutdown=1,
    )
