/**
 * Thẻ Đồng hồ trọng lượng real-time (POS Kiosk Touch-Ready) kết hợp
 * Thanh trạng thái trực quan + Quy trình 4 bước dạng Danh Sách Dọc có Ô Tích Tròn chuyển xanh.
 */
export function renderWeightGauge(container) {
  container.innerHTML = `
    <div class="card">
      <div class="card-head">
        <h3 class="card-title">Cân Trọng Lượng &amp; Tiến Trình Kiểm Định</h3>
        <span id="wg-online-badge" class="badge badge-success">
          <span class="dot dot-ok"></span> HX711 Online
        </span>
      </div>

      <div id="wg-state-bar" class="pos-state-bar is-idle">
        <span class="pos-state-dot"></span>
        <span id="wg-state-text">Chờ đặt hàng lên đĩa cân (tối thiểu 15g)</span>
      </div>

      <div class="scale-stepper-grid">
        <!-- Cột trái: Số cân lớn + Nút thao tác POS cảm ứng -->
        <div style="display:flex; flex-direction:column; gap:14px;">
          <div class="weight-panel">
            <div style="font-size:15px; font-weight:600; color:var(--text-muted); margin-bottom:6px;">
              Trọng lượng đĩa cân
            </div>
            <div>
              <span id="wg-grams" class="weight-hero tabular-nums">0.0</span>
              <span class="weight-unit">g</span>
            </div>
            <div id="wg-kg" class="tabular-nums" style="font-size:16px; font-weight:600; color:var(--text-secondary); margin-top:4px;">
              0.000 kg
            </div>
            <div style="margin-top:12px; display:flex; justify-content:center; gap:8px; flex-wrap:wrap;">
              <span id="wg-stable-badge" class="badge badge-neutral">Chờ đặt thực phẩm</span>
              <span id="wg-calib-badge" class="badge badge-success">Đã hiệu chuẩn</span>
            </div>
          </div>

          <div class="scale-actions-grid">
            <button id="btn-tare" class="btn btn-pos btn-outline" type="button">
              Trừ bì (Tare)
            </button>
            <button id="btn-rescan" class="btn btn-pos btn-primary" type="button">
              Quét lại
            </button>
            <button id="btn-manual-confirm" class="btn btn-pos btn-green" type="button">
              Chốt phiếu
            </button>
            <button id="btn-reset-session" class="btn btn-pos btn-outline" type="button">
              Reset phiên
            </button>
          </div>

          <button id="btn-reject-goods" class="btn btn-pos btn-danger" style="width:100%;" type="button">
            Từ chối hàng (Không đạt cảm quan)
          </button>

          <div id="wg-reject-panel" class="reject-panel" style="display:none;">
            <div style="font-size:15px; font-weight:700; color:#7F1D1D; margin-bottom:8px;">
              Chọn lý do từ chối nhập kho
            </div>
            <select id="reject-reason-select" class="select" style="width:100%; margin-bottom:8px;">
              <option value="Hàng dập nát / ôi thiu">Hàng dập nát / ôi thiu</option>
              <option value="Sai chủng loại / quy cách">Sai chủng loại / quy cách</option>
              <option value="Không đạt vệ sinh">Không đạt vệ sinh</option>
            </select>
            <input id="reject-note-input" class="input" style="width:100%; margin-bottom:10px;" placeholder="Ghi chú thêm (tùy chọn)..." />
            <div style="display:flex; gap:8px; flex-wrap:wrap;">
              <button id="btn-confirm-reject" class="btn btn-sm btn-danger" type="button">
                Ghi nhận từ chối (Không nhập kho)
              </button>
              <button id="btn-cancel-reject" class="btn btn-sm btn-outline" type="button">
                Hủy
              </button>
            </div>
          </div>

          <div id="wg-reset-order-prompt" style="display:none; background:var(--bg-muted); border:1px solid var(--border-strong); border-radius:8px; padding:12px 14px;">
            <div id="wg-reset-order-msg" style="font-size:15px; font-weight:600; color:var(--text-primary); margin-bottom:10px;">
              Phiếu hiện tại đã có nguyên liệu tích xanh. Reset lại tích xanh để demo lại?
            </div>
            <div style="display:flex; gap:10px; flex-wrap:wrap;">
              <button id="btn-reset-active-order" class="btn btn-sm btn-primary" type="button">
                Reset tích xanh phiếu này
              </button>
              <button id="btn-dismiss-reset-prompt" class="btn btn-sm btn-outline" type="button">
                Giữ nguyên phiếu
              </button>
            </div>
          </div>
        </div>

        <!-- Cột phải: Quy trình 4 bước dọc với ô tích tròn -->
        <div>
          <div style="font-size:15px; font-weight:700; color:var(--text-secondary); margin-bottom:10px;">
            Trạng thái tự động 4 bước
          </div>
          <ol class="v-stepper" id="v-stepper">
            <li class="v-step" data-step-num="1">
              <span class="v-step-circle"><span class="step-idx">1</span><span class="tick-mark"></span></span>
              <span class="v-step-text">1. Đặt thực phẩm lên đĩa cân</span>
            </li>
            <li class="v-step" data-step-num="2">
              <span class="v-step-circle"><span class="step-idx">2</span><span class="tick-mark"></span></span>
              <span class="v-step-text">2. Cân ổn định trọng lượng</span>
            </li>
            <li class="v-step" data-step-num="3">
              <span class="v-step-circle"><span class="step-idx">3</span><span class="tick-mark"></span></span>
              <span class="v-step-text">3. AI nhận diện &amp; kiểm định chất lượng</span>
            </li>
            <li class="v-step" data-step-num="4">
              <span class="v-step-circle"><span class="step-idx">4</span><span class="tick-mark"></span></span>
              <span class="v-step-text">4. Đối chiếu phiếu &amp; tích xanh hoàn thành</span>
            </li>
          </ol>
        </div>
      </div>
    </div>
  `;
}

export function updateWeightGauge(snapshot) {
  if (!snapshot) return;
  const g = Math.max(0, Number(snapshot.weight_gram || 0));
  const gramsEl = document.getElementById("wg-grams");
  const kgEl = document.getElementById("wg-kg");
  const stableEl = document.getElementById("wg-stable-badge");
  const onlineEl = document.getElementById("wg-online-badge");
  const calibEl = document.getElementById("wg-calib-badge");
  const confirmBtn = document.getElementById("btn-manual-confirm");
  const rejectBtn = document.getElementById("btn-reject-goods");
  const stateBar = document.getElementById("wg-state-bar");
  const stateText = document.getElementById("wg-state-text");

  if (gramsEl) gramsEl.textContent = g.toFixed(1);
  if (kgEl) kgEl.textContent = `${(g / 1000).toFixed(3)} kg`;

  if (stableEl) {
    if (g < 8.0) {
      stableEl.className = "badge badge-neutral";
      stableEl.textContent = "Đĩa cân trống";
    } else if (snapshot.is_stable) {
      stableEl.className = "badge badge-success";
      stableEl.textContent = "Trọng lượng ổn định";
    } else {
      stableEl.className = "badge badge-warning";
      stableEl.textContent = "Đang ổn định cân";
    }
  }

  if (onlineEl) {
    const ok = Boolean(snapshot.scale_online);
    onlineEl.className = ok ? "badge badge-success" : "badge badge-danger";
    onlineEl.innerHTML = `<span class="dot ${ok ? "dot-ok" : "dot-err"}"></span> ${
      ok ? (snapshot.mock_hardware ? "HX711 Mock" : "HX711 Online") : "Mất tín hiệu cân"
    }`;
  }

  if (calibEl) {
    const cal = Boolean(snapshot.scale_calibrated);
    calibEl.className = cal ? "badge badge-success" : "badge badge-warning";
    calibEl.textContent = cal ? "Đã hiệu chuẩn" : "Chưa hiệu chuẩn";
  }

  // Tính bước hoàn thành & thanh trạng thái trực quan
  const st = snapshot.state || "IDLE";
  const insp = snapshot.current_inspection;
  const committed = Boolean(insp?.committed);
  const qStatus = insp?.quality_status || insp?.quality?.status || "FRESH";

  if (stateBar && stateText) {
    if (st === "IDLE" && (!insp || g < 8.0)) {
      stateBar.className = "pos-state-bar is-idle";
      stateText.textContent = "Chờ đặt hàng lên đĩa cân (tối thiểu 15g)";
    } else if (st === "STABILIZING") {
      stateBar.className = "pos-state-bar is-stabilizing";
      stateText.textContent = `Đang ổn định cân... (${g.toFixed(1)}g)`;
    } else if (st === "INSPECTING") {
      stateBar.className = "pos-state-bar is-inspecting";
      stateText.textContent = "AI đang kiểm định chất lượng & định lượng...";
    } else if (qStatus === "REJECTED") {
      stateBar.className = "pos-state-bar is-rejected";
      stateText.textContent = `Từ chối nhập kho: ${insp?.food_name_vi || insp?.detected_class || "Hàng hư hỏng"}`;
    } else if (qStatus === "WARNING") {
      stateBar.className = "pos-state-bar is-warning";
      stateText.textContent = `Cảnh báo: ${insp?.food_name_vi || insp?.detected_class || "Cần kiểm tra lại"}`;
    } else {
      stateBar.className = "pos-state-bar is-fresh";
      stateText.textContent = `Đạt chuẩn: ${insp?.food_name_vi || insp?.detected_class || "Thực phẩm tươi"} (${g.toFixed(1)}g)`;
    }
  }

  let completedUpTo = 0;
  let activeStep = 1;

  if (st === "IDLE" && (!insp || g < 8.0)) {
    completedUpTo = 0;
    activeStep = 1;
  } else if (st === "STABILIZING") {
    completedUpTo = 1;
    activeStep = 2;
  } else if (st === "INSPECTING") {
    completedUpTo = 2;
    activeStep = 3;
  } else if (st === "CHECKOUT" || insp) {
    completedUpTo = committed ? 4 : 3;
    activeStep = committed ? 0 : 4;
  }

  document.querySelectorAll("#v-stepper .v-step").forEach((li) => {
    const n = Number(li.dataset.stepNum || 0);
    li.classList.toggle("is-done", n <= completedUpTo);
    li.classList.toggle("is-active", n === activeStep && n > completedUpTo);
  });

  if (confirmBtn) {
    const activeInsp = st === "IDLE" && g < 8.0 ? null : insp;
    if (activeInsp && committed) {
      confirmBtn.textContent = "Đã chốt phiếu lô này";
      confirmBtn.disabled = true;
    } else {
      confirmBtn.textContent = "Chốt phiếu";
      confirmBtn.disabled = g < 1.0 && !activeInsp;
    }
  }

  if (rejectBtn) {
    const activeInsp = st === "IDLE" && g < 8.0 ? null : insp;
    rejectBtn.disabled = (g < 1.0 && !activeInsp) || Boolean(committed && qStatus === "REJECTED");
  }
}
