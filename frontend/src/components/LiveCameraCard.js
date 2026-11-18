/**
 * Component hiển thị luồng Camera kiểm định trực tiếp, bounding box AI và nút Nhận diện ngay.
 */
export function renderLiveCameraCard(container) {
  container.innerHTML = `
    <div class="card">
      <div class="card-head">
        <h3 class="card-title">Camera Kiểm Định Trực Tiếp</h3>
        <div style="display:flex; gap:8px; align-items:center;">
          <span id="cam-ai-badge" class="badge badge-info">AI: Sẵn sàng</span>
          <button id="btn-inspect-now" class="btn btn-sm btn-primary" type="button">
            Nhận diện ngay
          </button>
        </div>
      </div>

      <div class="video-frame">
        <img id="live-video-img" src="/video_feed" alt="Luồng Camera Kiểm Định" />
        <div class="video-overlay-top">
          <span class="video-pill" id="cam-stream-status">LIVE 640x480</span>
          <span class="video-pill" id="cam-fps-badge">Latency: — ms</span>
        </div>
      </div>

      <div style="margin-top:10px; display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; font-size:12.5px; color:var(--text-secondary);">
        <span id="cam-detect-summary">Đặt thực phẩm lên đĩa cân để tự động nhận diện loại và chất lượng.</span>
        <span id="cam-strategy-tag" class="badge badge-neutral">Engine: NCNN</span>
      </div>
    </div>
  `;
}

export function updateLiveCameraCard(snapshot) {
  const insp = snapshot?.current_inspection;
  const aiBadge = document.getElementById("cam-ai-badge");
  const fpsBadge = document.getElementById("cam-fps-badge");
  const summaryEl = document.getElementById("cam-detect-summary");
  const stratEl = document.getElementById("cam-strategy-tag");

  if (!aiBadge || !fpsBadge || !summaryEl) return;

  if (!insp) {
    aiBadge.className = "badge badge-info";
    aiBadge.textContent = snapshot?.state === "STABILIZING" ? "Đang ổn định cân" : "Chờ nguyên liệu";
    fpsBadge.textContent = "Latency: — ms";
    summaryEl.textContent = "Đặt thực phẩm từ 15g trở lên, hệ thống sẽ tự động chụp ảnh và phân tích.";
    return;
  }

  if (insp.warning) {
    aiBadge.className = "badge badge-danger";
    aiBadge.textContent = insp.warning;
    fpsBadge.textContent = "AI Offline";
    summaryEl.innerHTML = `<span style="color:var(--danger); font-weight:700;">${insp.warning}</span> (Mã lô: ${insp.batch_code})`;
    if (stratEl) stratEl.textContent = `Engine: ${String(insp.strategy || "missing-ncnn").toUpperCase()}`;
    return;
  }

  const confPct = Math.round((insp.confidence || 0) * 100);
  const qStatus = insp.quality?.status || "FRESH";
  aiBadge.className =
    qStatus === "REJECTED" ? "badge badge-danger" : qStatus === "WARNING" ? "badge badge-warning" : "badge badge-success";
  aiBadge.textContent = `${insp.nutrition?.vietnamese_name || insp.detected_class} (${confPct}%)`;

  fpsBadge.textContent = `${insp.inference_time_ms || 0} ms | ${insp.fps || 0} FPS`;
  summaryEl.innerHTML = `Mã lô: <strong>${insp.batch_code}</strong> | Nhãn nhận diện: <strong>${insp.detected_class}</strong>`;
  if (stratEl) {
    stratEl.textContent = `Engine: ${String(insp.strategy || "ncnn").toUpperCase()}`;
  }
}
