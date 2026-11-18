/**
 * Component đồng hồ trọng lượng real-time, trạng thái State Machine, nút Tare & Lưu phiếu lẻ.
 */
const MAX_SCALE_G = 5000;

export function renderWeightGauge(container) {
  container.innerHTML = `
    <div class="card">
      <div class="card-head">
        <h3 class="card-title">Trọng Lượng Thực Tế (Loadcell HX711)</h3>
        <span id="wg-online-badge" class="badge badge-success">
          <span class="dot dot-ok"></span> HX711 Online
        </span>
      </div>

      <div class="gauge-wrap">
        <div class="gauge-svg-box">
          <svg viewBox="0 0 180 110" width="168" height="102" aria-label="Đồng hồ cân">
            <path d="M 20 95 A 70 70 0 0 1 160 95" fill="none" stroke="#E2E8F0" stroke-width="14" stroke-linecap="round"/>
            <path id="wg-arc" d="M 20 95 A 70 70 0 0 1 160 95" fill="none" stroke="#2E7D32" stroke-width="14" stroke-linecap="round"
              stroke-dasharray="220" stroke-dashoffset="220"/>
            <text x="90" y="84" text-anchor="middle" font-size="12" font-weight="700" fill="#64748B">MAX 5.000g</text>
          </svg>
        </div>

        <div class="weight-readout">
          <div style="display:flex; align-items:baseline; gap:8px; flex-wrap:wrap;">
            <span id="wg-grams" class="weight-value tabular-nums">0.0</span>
            <span class="weight-unit">g</span>
            <span id="wg-kg" style="font-size:14px; font-weight:700; color:var(--text-muted);">(0.000 kg)</span>
          </div>
          <div style="margin-top:8px; display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
            <span id="wg-stable-badge" class="badge badge-neutral">Chờ ổn định</span>
            <span id="wg-calib-badge" class="badge badge-success">Đã hiệu chuẩn</span>
          </div>
        </div>
      </div>

      <div class="stepper" id="wg-stepper">
        <div class="step-item" data-step="IDLE">1. CHỜ HÀNG</div>
        <div class="step-item" data-step="STABILIZING">2. ỔN ĐỊNH</div>
        <div class="step-item" data-step="INSPECTING">3. KIỂM ĐỊNH AI</div>
        <div class="step-item" data-step="CHECKOUT">4. XÁC NHẬN</div>
      </div>

      <div style="display:grid; grid-template-columns: 1fr 1.25fr; gap:10px; margin-top:10px;">
        <button id="btn-tare" class="btn btn-outline" type="button">Tare / Trừ bì (0g)</button>
        <button id="btn-commit-receipt" class="btn btn-green" type="button">Lưu phiếu nhập lẻ</button>
      </div>
    </div>
  `;
}

export function updateWeightGauge(snapshot) {
  if (!snapshot) return;
  const g = Math.max(0, Number(snapshot.weight_gram || 0));
  const gramsEl = document.getElementById("wg-grams");
  const kgEl = document.getElementById("wg-kg");
  const arcEl = document.getElementById("wg-arc");
  const stableEl = document.getElementById("wg-stable-badge");
  const onlineEl = document.getElementById("wg-online-badge");
  const calibEl = document.getElementById("wg-calib-badge");
  const commitBtn = document.getElementById("btn-commit-receipt");

  if (gramsEl) gramsEl.textContent = g.toFixed(1);
  if (kgEl) kgEl.textContent = `(${(g / 1000).toFixed(3)} kg)`;

  if (arcEl) {
    const ratio = Math.min(1, g / MAX_SCALE_G);
    arcEl.setAttribute("stroke-dashoffset", String((220 - ratio * 220).toFixed(1)));
    arcEl.setAttribute("stroke", g >= 4500 ? "#C62828" : snapshot.is_stable ? "#2E7D32" : "#F57C00");
  }

  if (stableEl) {
    stableEl.className = snapshot.is_stable ? "badge badge-success" : "badge badge-warning";
    stableEl.textContent = snapshot.is_stable ? "Trọng lượng ổn định" : "Đang dao động / Chờ vật";
  }

  if (onlineEl) {
    const ok = Boolean(snapshot.scale_online);
    onlineEl.className = ok ? "badge badge-success" : "badge badge-danger";
    onlineEl.innerHTML = `<span class="dot ${ok ? "dot-ok" : "dot-err"}"></span> ${
      ok ? (snapshot.mock_hardware ? "HX711 Mock Online" : "HX711 Online") : "Mất tín hiệu cân"
    }`;
  }

  if (calibEl) {
    const cal = Boolean(snapshot.scale_calibrated);
    calibEl.className = cal ? "badge badge-success" : "badge badge-warning";
    calibEl.textContent = cal ? "Đã hiệu chuẩn" : "Chưa hiệu chuẩn";
  }

  document.querySelectorAll("#wg-stepper .step-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.step === snapshot.state);
  });

  if (commitBtn) {
    const committed = Boolean(snapshot.current_inspection?.committed);
    if (committed) {
      commitBtn.textContent = "Đã lưu phiếu lô này";
      commitBtn.disabled = true;
    } else {
      commitBtn.textContent = "Lưu phiếu nhập lẻ";
      commitBtn.disabled = g < 1.0 && !snapshot.current_inspection;
    }
  }
}
