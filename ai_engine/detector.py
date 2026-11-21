"""Module suy luận AI YOLO26n NCNN tối ưu CPU cho Raspberry Pi 4 (ARM Cortex-A72 NEON).

Hỗ trợ tự động nhận diện và chuyển đổi linh hoạt giữa:
1. NCNN native (`ncnn.Net`) - siêu nhẹ, tốc độ cao nhất trên Pi 4.
2. Ultralytics YOLO NCNN (`YOLO(model_dir, task="detect")`) - tương thích đa nền tảng.
3. MockAIStrategy - giả lập mượt mà khi dev/test trên Windows hoặc chưa cài runtime AI.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from backend.core.config import settings
from backend.core.constants import CONFIDENCE_HIGH_THRESHOLD, ROTTEN_KEYWORDS, QualityStatus

logger = logging.getLogger("nutrition_station.ai.detector")

DEFAULT_64_CLASSES: list[str] = [
    "Apple", "Apricot", "Asparagus", "Avocado", "Banana", "Beef", "Beetroot",
    "Bell Pepper", "Berry", "Cabbage", "Cantaloupe", "Carrot", "Cashew Nut",
    "Cauliflower", "Cherry", "Cherry Tomato", "Chestnut", "Chicken", "Coconut",
    "Corn", "Crab", "Cucumber", "Date", "Dragon Fruit", "Egg", "Eggplant",
    "Fig", "Fish", "Garlic", "Ginger", "Grape", "Grapefruit", "Green Beans",
    "Guava", "Kiwi", "Lamb", "Leek", "Lemon", "Lime", "Lobster", "Lychee",
    "Mango", "Mangosteen", "Mushroom", "Nectarine", "Orange", "Passion Fruit",
    "Peach", "Pear", "Pineapple", "Plum", "Pomegranate", "Pork", "Potato",
    "Rambutan", "Red Onion", "Shrimp", "Star Fruit", "Sweet Potato", "Tomato",
    "Walnut", "Watermelon", "White Onion", "Zucchini",
]


def load_metadata_names(metadata_path: Path | None = None) -> dict[int, str]:
    """Đọc danh sách 64 nhãn thực phẩm từ metadata.yaml của YOLO26n."""
    target = metadata_path or settings.ncnn_metadata_path
    if not target.exists():
        return {i: name for i, name in enumerate(DEFAULT_64_CLASSES)}

    try:
        import yaml

        with open(target, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        raw_names = data.get("names", {})
        if isinstance(raw_names, dict) and raw_names:
            return {int(k): str(v) for k, v in raw_names.items()}
        if isinstance(raw_names, list) and raw_names:
            return {i: str(v) for i, v in enumerate(raw_names)}
    except Exception as exc:
        logger.warning(f"Lỗi đọc metadata.yaml bằng PyYAML ({exc}), dùng danh sách mặc định 64 lớp.")

    return {i: name for i, name in enumerate(DEFAULT_64_CLASSES)}


def evaluate_quality(label: str, confidence: float) -> str:
    """Đánh giá trạng thái chất lượng FRESH / WARNING / REJECTED."""
    if not label or label == "Unknown":
        return QualityStatus.WARNING.value
    lower = label.lower()
    if any(kw in lower for kw in ROTTEN_KEYWORDS):
        return QualityStatus.REJECTED.value
    if confidence < CONFIDENCE_HIGH_THRESHOLD:
        return QualityStatus.WARNING.value
    return QualityStatus.FRESH.value


def draw_detections(frame: np.ndarray, detections: list[dict[str, Any]]) -> np.ndarray:
    """Vẽ bounding box và độ tin cậy lên khung hình hiển thị trên Dashboard."""
    out = frame.copy()
    for det in detections:
        box = det["box"]
        label = det["label"]
        conf = float(det["confidence"])
        quality = evaluate_quality(label, conf)

        if quality == QualityStatus.REJECTED.value:
            color = (48, 59, 239)     # Đỏ BGR: Hư hỏng / Từ chối
        elif quality == QualityStatus.WARNING.value:
            color = (11, 158, 245)    # Cam BGR: Cần kiểm tra
        else:
            color = (50, 205, 50)     # Xanh lá tươi BGR: Đạt chuẩn

        x1, y1, x2, y2 = int(box["x1"]), int(box["y1"]), int(box["x2"]), int(box["y2"])
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 3)

        caption = f"{label} - {conf * 100:.0f}%"
        (tw, th), _ = cv2.getTextSize(caption, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        bg_y1 = max(0, y1 - th - 12)
        cv2.rectangle(out, (x1, bg_y1), (min(out.shape[1], x1 + tw + 12), y1), color, -1)
        cv2.putText(
            out,
            caption,
            (x1 + 6, max(th + 4, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
    return out


class BaseAIDetector(ABC):
    """Lớp trừu tượng chuẩn hóa đầu ra suy luận thực phẩm."""

    name: str = "base"
    backend: str = "base"

    @property
    def is_ready(self) -> bool:
        return True

    @abstractmethod
    def predict(self, frame: np.ndarray, weight_gram: float = 0.0) -> dict[str, Any]:
        raise NotImplementedError


class MockAIDetector(BaseAIDetector):
    """Bộ suy luận giả lập cho phép test mượt mà mọi loại thực phẩm trên Windows."""

    name = "mock"
    backend = "mock"

    def __init__(self) -> None:
        self.class_names = load_metadata_names()
        self.num_classes = len(self.class_names)
        self._forced_label: str | None = None
        self._forced_quality: str | None = None
        self._current_mock_label: str = "Apple"

    def force_next(self, label: str | None = None, quality: str | None = None) -> None:
        """Ép kết quả AI giả lập tiếp theo (dùng cho nút test trên giao diện Mock)."""
        self._forced_label = label.strip() if label else None
        self._forced_quality = quality.strip().upper() if quality else None
        if self._forced_label:
            self._current_mock_label = self._forced_label

    def predict(self, frame: np.ndarray, weight_gram: float = 0.0) -> dict[str, Any]:
        started = time.perf_counter()
        time.sleep(0.03)

        if self._forced_label:
            label = self._forced_label
            quality = self._forced_quality or evaluate_quality(label, 0.94)
            if quality == QualityStatus.REJECTED.value and not any(k in label.lower() for k in ROTTEN_KEYWORDS):
                label = f"Rotten_{label}"
            conf = 0.89 if quality == QualityStatus.REJECTED.value else 0.94
        else:
            sample_pool = ["Pork", "Beef", "Fish", "Tomato", "Carrot", "Cabbage", "Apple", "Banana", "Egg", "Chicken"]
            idx = int(round(max(0.0, weight_gram))) % len(sample_pool)
            label = sample_pool[idx] if weight_gram > 0 else self._current_mock_label
            if self._forced_quality == QualityStatus.REJECTED.value:
                label = f"Rotten_{label}"
                conf = 0.87
            else:
                conf = 0.93

        h, w = frame.shape[:2]
        detections = [
            {
                "label": label,
                "confidence": round(conf, 3),
                "box": {
                    "x1": int(w * 0.24),
                    "y1": int(h * 0.16),
                    "x2": int(w * 0.76),
                    "y2": int(h * 0.84),
                },
            }
        ]
        annotated = draw_detections(frame, detections)
        elapsed_ms = max(1, int((time.perf_counter() - started) * 1000))
        return _pack_prediction(detections, annotated, elapsed_ms, strategy="mock")


class NCNNYoloDetector(BaseAIDetector):
    """Wrapper chạy mô hình YOLO26n đã xuất NCNN (416x416, 64 classes)."""

    name = "ncnn"

    def __init__(self) -> None:
        self.backend = "none"
        self._net = None
        self._yolo = None
        self._cv_dnn_net = None
        self._fallback = MockAIDetector()

        self.class_names = load_metadata_names(settings.ncnn_metadata_path)
        self.num_classes = len(self.class_names)
        self.input_size = settings.ai_input_size
        self.conf_threshold = settings.ai_confidence_threshold
        self.iou_threshold = settings.ai_nms_iou_threshold
        # Giới hạn tối đa 2 luồng CPU cho AI để chừa 2 nhân trống cho xung GPIO HX711 (tránh trễ SCK > 60µs)
        self.num_threads = 2
        self.last_error: str | None = None

        self._load_backend()

    def _load_backend(self) -> None:
        """Ưu tiên nạp C++ ncnn; thử ultralytics hoặc cv2.dnn ONNX; cảnh báo rõ nếu thiếu trên Pi 4."""
        param_path = settings.ncnn_param_path
        bin_path = settings.ncnn_bin_path
        onnx_candidates = [
            settings.model_dir / "best.onnx",
            settings.model_dir / "model.onnx",
        ]
        onnx_path = next((p for p in onnx_candidates if p.exists()), None)

        if not (param_path.exists() and bin_path.exists()):
            self.last_error = f"Không tìm thấy {param_path.name} / {bin_path.name} tại {settings.model_dir}"
            logger.warning(f"[AI] {self.last_error}")

        # 1. Thử thư viện ncnn thuần (tối ưu ARM NEON trên Raspberry Pi 4)
        if param_path.exists() and bin_path.exists():
            try:
                import ncnn  # type: ignore

                net = ncnn.Net()
                net.opt.use_vulkan_compute = False
                net.opt.num_threads = 2
                if net.load_param(str(param_path)) == 0 and net.load_model(str(bin_path)) == 0:
                    self._net = net
                    self.backend = "ncnn"
                    self.last_error = None
                    logger.info(
                        f"[AI] Đã nạp YOLO26n NCNN native ({self.num_classes} lớp, num_threads=2 - chừa 2 nhân CPU cho HX711)."
                    )
                    return
                self.last_error = "ncnn.Net.load_param/load_model trả về mã lỗi khác 0"
            except ImportError:
                pass
            except Exception as exc:
                self.last_error = f"Lỗi nạp ncnn native: {exc}"
                logger.warning(f"[AI] {self.last_error}")

        # 2. Thử Ultralytics YOLO (hỗ trợ cả ncnn nếu có hoặc file .onnx/.pt)
        try:
            import importlib.util
            from ultralytics import YOLO  # type: ignore

            if importlib.util.find_spec("ncnn") is not None and param_path.exists():
                self._yolo = YOLO(str(settings.model_dir), task="detect")
                self.backend = "ultralytics-ncnn"
                self.last_error = None
                logger.info(f"[AI] Đã nạp YOLO26n qua Ultralytics NCNN: {settings.model_dir}")
                return
            if onnx_path is not None:
                self._yolo = YOLO(str(onnx_path), task="detect")
                self.backend = "ultralytics-onnx"
                self.last_error = None
                logger.info(f"[AI] Đã nạp mô hình dự phòng qua Ultralytics ONNX: {onnx_path.name}")
                return
        except Exception as exc:
            self.last_error = f"Lỗi nạp ultralytics: {exc}"
            logger.warning(f"[AI] {self.last_error}")

        # 3. Thử OpenCV cv2.dnn nếu có file ONNX
        if onnx_path is not None:
            try:
                self._cv_dnn_net = cv2.dnn.readNetFromONNX(str(onnx_path))
                self.backend = "opencv-dnn"
                self.last_error = None
                logger.info(f"[AI] Đã nạp mô hình dự phòng qua cv2.dnn: {onnx_path.name}")
                return
            except Exception as exc:
                self.last_error = f"Lỗi nạp cv2.dnn ONNX: {exc}"
                logger.warning(f"[AI] {self.last_error}")

        self.last_error = "Chưa cài thư viện ncnn trên Pi 4"
        if settings.mock_hardware:
            logger.info("[AI] Chế độ MOCK_HARDWARE=True -> dùng MockAIDetector.")
        else:
            logger.error(f"[AI] {self.last_error} (cần chạy: pip install ncnn)")

    @property
    def is_ready(self) -> bool:
        return self.backend in {"ncnn", "ultralytics-ncnn", "ultralytics-onnx", "opencv-dnn"}

    def force_next(self, label: str | None = None, quality: str | None = None) -> None:
        self._fallback.force_next(label=label, quality=quality)

    def predict(self, frame: np.ndarray, weight_gram: float = 0.0) -> dict[str, Any]:
        """Thực hiện suy luận và trả về bounding boxes, nhãn, độ tin cậy, FPS."""
        if frame is None or frame.size == 0:
            return _pack_prediction([], np.zeros((480, 640, 3), dtype=np.uint8), 0, strategy="empty")

        # Nếu người dùng đang chủ động test ép nhãn trên giao diện Mock
        if self._fallback._forced_label is not None or self._fallback._forced_quality is not None:
            return self._fallback.predict(frame, weight_gram)

        if not self.is_ready:
            if settings.mock_hardware:
                res = self._fallback.predict(frame, weight_gram)
                res["strategy"] = "ncnn-fallback-mock"
                return res
            # Trên phần cứng thật nhưng thiếu thư viện ncnn -> trả về cảnh báo rõ ràng lên UI
            warn_msg = self.last_error or "Chưa cài thư viện ncnn trên Pi 4"
            annotated = frame.copy()
            cv2.rectangle(annotated, (12, 12), (annotated.shape[1] - 12, 54), (48, 59, 239), -1)
            cv2.putText(
                annotated,
                "Chua cai thu vien ncnn tren Pi 4",
                (24, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            res = _pack_prediction([], annotated, 0, strategy="missing-ncnn")
            res["warning"] = warn_msg
            return res

        started = time.perf_counter()
        try:
            if self.backend == "ncnn":
                detections = self._infer_ncnn_native(frame)
            elif self.backend == "opencv-dnn":
                detections = self._infer_cv_dnn(frame)
            else:
                detections = self._infer_ultralytics(frame)
        except Exception as exc:
            logger.exception(f"[AI] Lỗi suy luận NCNN: {exc}")
            detections = []

        annotated = draw_detections(frame, detections)
        elapsed_ms = max(1, int((time.perf_counter() - started) * 1000))
        return _pack_prediction(detections, annotated, elapsed_ms, strategy=self.backend)

    def _infer_cv_dnn(self, frame: np.ndarray) -> list[dict[str, Any]]:
        """Suy luận dự phòng qua cv2.dnn khi có file ONNX."""
        h_orig, w_orig = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(
            frame,
            scalefactor=1.0 / 255.0,
            size=(self.input_size, self.input_size),
            swapRB=True,
            crop=False,
        )
        self._cv_dnn_net.setInput(blob)
        out = self._cv_dnn_net.forward()
        return self._postprocess_yolo(out, (h_orig, w_orig))

    @staticmethod
    def _letterbox(frame: np.ndarray, target_size: int) -> tuple[np.ndarray, float, float, float]:
        """Resize giữ nguyên tỷ lệ kèm viền xám (114, 114, 114) chuẩn Ultralytics YOLO."""
        h_orig, w_orig = frame.shape[:2]
        ratio = min(target_size / float(h_orig), target_size / float(w_orig))
        new_w = int(round(w_orig * ratio))
        new_h = int(round(h_orig * ratio))
        dw = (target_size - new_w) / 2.0
        dh = (target_size - new_h) / 2.0

        if (w_orig, h_orig) != (new_w, new_h):
            resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        else:
            resized = frame

        top = int(round(dh - 0.1))
        bottom = int(round(dh + 0.1))
        left = int(round(dw - 0.1))
        right = int(round(dw + 0.1))
        padded = cv2.copyMakeBorder(
            resized, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114)
        )
        if padded.shape[0] != target_size or padded.shape[1] != target_size:
            padded = cv2.resize(padded, (target_size, target_size), interpolation=cv2.INTER_LINEAR)
        return np.ascontiguousarray(padded, dtype=np.uint8), ratio, float(left), float(top)

    def _infer_ncnn_native(self, frame: np.ndarray) -> list[dict[str, Any]]:
        """Tiền xử lý letterbox 416x416 -> suy luận NCNN (in0 -> out0) -> giải mã & NMS."""
        import ncnn  # type: ignore

        h_orig, w_orig = frame.shape[:2]
        padded, ratio, pad_x, pad_y = self._letterbox(frame, self.input_size)

        mat_in = ncnn.Mat.from_pixels(
            padded,
            ncnn.Mat.PixelType.PIXEL_BGR2RGB,
            self.input_size,
            self.input_size,
        )
        norm_vals = [1.0 / 255.0, 1.0 / 255.0, 1.0 / 255.0]
        mat_in.substract_mean_normalize([], norm_vals)

        ex = self._net.create_extractor()
        if hasattr(ex, "set_num_threads"):
            ex.set_num_threads(2)
        ex.input("in0", mat_in)
        ret, mat_out = ex.extract("out0")
        if ret != 0:
            return []

        raw_out = np.array(mat_out)
        return self._postprocess_yolo(raw_out, (h_orig, w_orig), letterbox=(ratio, pad_x, pad_y))

    def _postprocess_yolo(
        self,
        output: np.ndarray,
        frame_shape: tuple[int, int],
        letterbox: tuple[float, float, float] | None = None,
    ) -> list[dict[str, Any]]:
        """Giải mã tensor đầu ra (68, 3549) của YOLO26n về tọa độ khung hình gốc & lọc NMS."""
        out = np.squeeze(output)
        if out.ndim != 2:
            return []
        # Ultralytics YOLO NCNN trả về (4 + num_classes, 3549) -> chuyển về (3549, 68)
        if out.shape[0] in (4 + self.num_classes, 68) or out.shape[0] < out.shape[1]:
            out = out.T

        if out.shape[1] < 5:
            return []

        h_orig, w_orig = frame_shape[:2]
        # Tự động xử lý nếu tọa độ bbox bị chuẩn hóa [0..1]
        coords_max = float(np.max(out[:, :4])) if out.size else 0.0
        coord_mul = float(self.input_size) if 0.0 < coords_max <= 2.0 else 1.0

        scores_matrix = out[:, 4:]
        best_cls_ids = np.argmax(scores_matrix, axis=1)
        best_confs = scores_matrix[np.arange(out.shape[0]), best_cls_ids]
        valid_mask = best_confs >= self.conf_threshold

        boxes: list[list[int]] = []
        confidences: list[float] = []
        class_ids: list[int] = []

        for row, cls_id, conf in zip(out[valid_mask], best_cls_ids[valid_mask], best_confs[valid_mask]):
            cx = float(row[0]) * coord_mul
            cy = float(row[1]) * coord_mul
            bw = float(row[2]) * coord_mul
            bh = float(row[3]) * coord_mul

            if letterbox is not None:
                ratio, pad_x, pad_y = letterbox
                x1_f = (cx - bw / 2.0 - pad_x) / ratio
                y1_f = (cy - bh / 2.0 - pad_y) / ratio
                x2_f = (cx + bw / 2.0 - pad_x) / ratio
                y2_f = (cy + bh / 2.0 - pad_y) / ratio
            else:
                sx = w_orig / float(self.input_size)
                sy = h_orig / float(self.input_size)
                x1_f = (cx - bw / 2.0) * sx
                y1_f = (cy - bh / 2.0) * sy
                x2_f = (cx + bw / 2.0) * sx
                y2_f = (cy + bh / 2.0) * sy

            x1 = max(0, min(w_orig - 1, int(round(x1_f))))
            y1 = max(0, min(h_orig - 1, int(round(y1_f))))
            x2 = max(0, min(w_orig, int(round(x2_f))))
            y2 = max(0, min(h_orig, int(round(y2_f))))
            box_w = x2 - x1
            box_h = y2 - y1
            if box_w <= 2 or box_h <= 2:
                continue

            boxes.append([x1, y1, box_w, box_h])
            confidences.append(float(conf))
            class_ids.append(int(cls_id))

        if not boxes:
            return []

        indices = cv2.dnn.NMSBoxes(boxes, confidences, self.conf_threshold, self.iou_threshold)
        if len(indices) == 0:
            return []

        detections: list[dict[str, Any]] = []
        for idx in indices:
            i = int(idx[0]) if isinstance(idx, (list, tuple, np.ndarray)) else int(idx)
            x1, y1, box_w, box_h = boxes[i]
            cls_id = class_ids[i]
            detections.append(
                {
                    "class_id": cls_id,
                    "label": self.class_names.get(cls_id, f"class_{cls_id}"),
                    "confidence": round(confidences[i], 3),
                    "box": {"x1": x1, "y1": y1, "x2": x1 + box_w, "y2": y1 + box_h},
                }
            )

        detections.sort(key=lambda d: d["confidence"], reverse=True)
        return detections[:8]

    def _infer_ultralytics(self, frame: np.ndarray) -> list[dict[str, Any]]:
        results = self._yolo(
            frame,
            imgsz=self.input_size,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            verbose=False,
        )
        if not results:
            return []
        res = results[0]
        if res.boxes is None or len(res.boxes) == 0:
            return []

        detections: list[dict[str, Any]] = []
        for box in res.boxes:
            cls_id = int(box.cls[0].item())
            conf = float(box.conf[0].item())
            xyxy = box.xyxy[0].cpu().numpy().astype(int)
            detections.append(
                {
                    "class_id": cls_id,
                    "label": self.class_names.get(cls_id, f"class_{cls_id}"),
                    "confidence": round(conf, 3),
                    "box": {
                        "x1": int(xyxy[0]),
                        "y1": int(xyxy[1]),
                        "x2": int(xyxy[2]),
                        "y2": int(xyxy[3]),
                    },
                }
            )
        detections.sort(key=lambda d: d["confidence"], reverse=True)
        return detections[:8]


def _pack_prediction(
    detections: list[dict[str, Any]],
    annotated: np.ndarray,
    inference_time_ms: int,
    strategy: str,
) -> dict[str, Any]:
    """Đóng gói kết quả suy luận chuẩn hóa cho Pipeline & WebSocket."""
    rotten_hits = [
        d for d in detections
        if evaluate_quality(d["label"], d["confidence"]) == QualityStatus.REJECTED.value
    ]
    if rotten_hits:
        best = max(rotten_hits, key=lambda d: d["confidence"])
    elif detections:
        best = max(detections, key=lambda d: d["confidence"])
    else:
        best = {"label": "Unknown", "confidence": 0.0}

    label = str(best["label"])
    confidence = float(best["confidence"])
    quality_status = evaluate_quality(label, confidence)
    fps = round(1000.0 / inference_time_ms, 1) if inference_time_ms > 0 else 0.0

    return {
        "detected_class": label,
        "quality_status": quality_status,
        "confidence": round(confidence, 3),
        "confidence_percent": round(confidence * 100.0, 1),
        "bbox": best.get("box"),
        "inference_time_ms": inference_time_ms,
        "fps": fps,
        "detections": detections,
        "annotated_frame": annotated,
        "strategy": strategy,
    }


def build_detector(strategy: str | None = None) -> BaseAIDetector:
    """Factory khởi tạo AI Detector theo cấu hình AI_STRATEGY."""
    key = (strategy or settings.ai_strategy).lower()
    if key == "mock":
        return MockAIDetector()
    return NCNNYoloDetector()
