/**
 * Khung Camera AI tỷ lệ chuẩn 4:3 (không cắt xén) + Thẻ 4 thông số nhận diện Real-time ngay bên dưới.
 */
export function renderLiveCameraCard(container, foodsList = []) {
  const optionsHtml = foodsList
    .map((f) => `<option value="${f.class_name}">${f.vietnamese_name} (${f.class_name})</option>`)
    .join("");

  container.innerHTML = `
    <div class="card">
      <div class="card-head">
        <h3 class="card-title">Camera Kiểm Định Thực Phẩm AI</h3>
        <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
          <span id="cam-ai-badge" class="badge badge-info">Sẵn sàng</span>
          <button id="btn-inspect-now" class="btn btn-sm btn-primary" type="button">
            Nhận diện ngay
          </button>
        </div>
      </div>

      <div class="camera-box">
        <img id="live-video-img" src="/video_feed" alt="Luồng Camera Kiểm Định" />
      </div>

      <div class="camera-meta-bar">
        <span id="cam-detect-summary">Đặt thực phẩm lên đĩa cân (tối thiểu 15g) để hệ thống tự nhận diện.</span>
        <span id="cam-fps-badge" class="badge badge-neutral">640x480 | Latency: — ms</span>
      </div>

      <!-- 4 Thẻ Dữ Liệu Nhận Diện Real-time -->
      <div class="detect-grid-4">
        <div class="stat-tile">
          <div class="stat-tile-label">Tên nguyên liệu nhận diện</div>
          <div class="stat-tile-value" id="det-food-name">Chờ nhận diện</div>
          <div class="stat-tile-sub" id="det-food-en">—</div>
        </div>

        <div class="stat-tile">
          <div class="stat-tile-label">Khối lượng thực tế</div>
          <div class="stat-tile-value tabular-nums" id="det-weight-g">0.0 g</div>
          <div class="stat-tile-sub" id="det-quality-text">Trạng thái: Chờ hàng</div>
        </div>

        <div class="stat-tile">
          <div class="stat-tile-label">Đơn giá &amp; Thành tiền</div>
          <div class="stat-tile-value tabular-nums" id="det-total-price" style="color:var(--brand);">0 đ</div>
          <div class="stat-tile-sub tabular-nums" id="det-unit-price">Đơn giá: 0 đ/kg</div>
        </div>

        <div class="stat-tile">
          <div class="stat-tile-label">Độ chính xác AI</div>
          <div class="stat-tile-value tabular-nums" id="det-confidence">0.0%</div>
          <div class="stat-tile-sub" id="det-macro-brief">0 kcal | P: 0g | L: 0g | C: 0g</div>
        </div>
      </div>

      <!-- Chọn lại thủ công nếu cần chỉnh xác nhận -->
      <div style="margin-top:16px; display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
        <label for="nt-food-select" style="font-size:15px; font-weight:600; color:var(--text-secondary);">
          Chọn lại nguyên liệu (nếu cần):
        </label>
        <select id="nt-food-select" class="select" style="flex:1; min-width:240px;">
          <option value="">-- Tự động theo AI YOLO26n --</option>
          ${optionsHtml}
        </select>
      </div>
    </div>
  `;
}

export function updateLiveCameraCard(snapshot) {
  if (!snapshot) return;
  const insp = snapshot.current_inspection;
  const weightG = Number(snapshot.weight_gram || 0);

  const aiBadge = document.getElementById("cam-ai-badge");
  const fpsBadge = document.getElementById("cam-fps-badge");
  const summaryEl = document.getElementById("cam-detect-summary");
  const selectEl = document.getElementById("nt-food-select");

  const setText = (id, text) => {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  };

  setText("det-weight-g", `${weightG.toFixed(1)} g`);

  const isIdleEmpty = !insp || (snapshot.state === "IDLE" && weightG < 8.0);
  if (isIdleEmpty) {
    if (aiBadge) {
      aiBadge.className = "badge badge-info";
      aiBadge.textContent = snapshot.state === "STABILIZING" ? "Đang ổn định cân" : "Sẵn sàng";
    }
    if (fpsBadge) fpsBadge.textContent = "640x480 | Sẵn sàng";
    if (summaryEl) {
      summaryEl.textContent = "Sẵn sàng đặt thực phẩm mới (tối thiểu 15g) để hệ thống tự động nhận diện.";
    }
    setText("det-food-name", "Chờ nhận diện");
    setText("det-food-en", "Sẵn sàng đặt thực phẩm mới");
    setText("det-quality-text", "Trạng thái: Chờ hàng");
    setText("det-total-price", "0 đ");
    setText("det-unit-price", "Đơn giá: 0 đ/kg");
    setText("det-confidence", "0.0%");
    setText("det-macro-brief", "0 kcal | P: 0g | L: 0g | C: 0g");
    if (selectEl && document.activeElement !== selectEl) selectEl.value = "";
    return;
  }

  if (insp.warning) {
    if (aiBadge) {
      aiBadge.className = "badge badge-danger";
      aiBadge.textContent = insp.warning;
    }
    if (summaryEl) {
      summaryEl.innerHTML = `<span style="color:var(--danger); font-weight:700;">${insp.warning}</span>`;
    }
  } else {
    const qStatus = insp.quality_status || insp.quality?.status || "FRESH";
    if (aiBadge) {
      aiBadge.className =
        qStatus === "REJECTED" ? "badge badge-danger" : qStatus === "WARNING" ? "badge badge-warning" : "badge badge-success";
      aiBadge.textContent = `${insp.food_name_vi || insp.detected_class} (${Number(insp.confidence_percent || 0).toFixed(1)}%)`;
    }
    if (summaryEl) {
      summaryEl.innerHTML = `Mã lô: <strong>${insp.batch_code}</strong> | Engine: <strong>${String(insp.strategy || "ncnn").toUpperCase()}</strong>`;
    }
  }

  if (fpsBadge) {
    fpsBadge.textContent = `${insp.inference_time_ms || 0} ms | ${insp.fps || 0} FPS`;
  }

  setText("det-food-name", insp.food_name_vi || insp.detected_class || "Không xác định");
  setText("det-food-en", `${insp.food_name_en || insp.detected_class || "—"} | ${insp.nutrition?.food_group || "—"}`);

  const qualLabel =
    insp.quality_status === "REJECTED"
      ? "Hư hỏng - Từ chối"
      : insp.quality_status === "WARNING"
      ? "Cần kiểm tra cảm quan"
      : "Đạt chuẩn tươi sạch";
  setText("det-quality-text", `Chất lượng: ${qualLabel}`);

  const unitPrice = Number(insp.unit_price_per_kg || 0);
  const totalPrice = Number(insp.total_price_vnd || 0);
  setText("det-total-price", `${totalPrice.toLocaleString("vi-VN")} đ`);
  setText("det-unit-price", `Đơn giá: ${unitPrice.toLocaleString("vi-VN")} đ/kg`);

  setText("det-confidence", `${Number(insp.confidence_percent ?? (insp.confidence || 0) * 100).toFixed(1)}%`);
  setText(
    "det-macro-brief",
    `${Number(insp.calories || 0).toFixed(1)} kcal | P: ${Number(insp.protein || 0).toFixed(1)}g | L: ${Number(insp.lipid || 0).toFixed(1)}g | C: ${Number(insp.carb || 0).toFixed(1)}g`
  );

  if (selectEl && document.activeElement !== selectEl && insp.food_name_en) {
    selectEl.value = insp.food_name_en;
  }
}
