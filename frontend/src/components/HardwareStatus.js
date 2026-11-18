/**
 * Component sơ đồ kết nối phần cứng Raspberry Pi 4 (Camera, HX711, LCD I2C, NCNN AI).
 */
function nodeClass(status) {
  if (!status) return "";
  if (status.includes("MOCK")) return "mock";
  if (status === "PASS") return "ok";
  return "fail";
}

function badgeClass(status) {
  if (!status) return "badge-info";
  if (status.includes("MOCK")) return "badge-warning";
  if (status === "PASS") return "badge-success";
  return "badge-danger";
}

export function renderHardwareStatus(container, hwData) {
  if (!hwData) {
    container.innerHTML = `<div class="card">Đang tải thông số phần cứng...</div>`;
    return;
  }

  const cam = hwData.camera || {};
  const hx = hwData.hx711 || {};
  const lcd = hwData.lcd || {};
  const ai = hwData.ai || {};

  const camD = cam.details || {};
  const hxD = hx.details || {};
  const lcdD = lcd.details || {};
  const aiF = ai.files || {};

  container.innerHTML = `
    <div class="card">
      <div class="card-head">
        <h3 class="card-title">Sơ Đồ Kết Nối &amp; Kiểm Định Phần Cứng Raspberry Pi 4</h3>
        <div style="display:flex; gap:8px; align-items:center;">
          <span class="badge ${badgeClass(hwData.overall)}">TỔNG THỂ: ${hwData.overall}</span>
          <button id="btn-refresh-hw" class="btn btn-sm btn-primary" type="button">Kiểm tra lại</button>
        </div>
      </div>

      <div class="topo-diagram">
        <div style="display:flex; flex-direction:column; gap:12px;">
          <div class="hw-node ${nodeClass(hx.status)}">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
              <strong>Loadcell 5kg + HX711</strong>
              <span class="badge ${badgeClass(hx.status)}">${hx.status}</span>
            </div>
            <div style="font-size:12.5px; color:var(--text-secondary);">
              <div>Chân GPIO BCM: <strong>DT=GPIO${hxD.dt_pin ?? 5}</strong>, <strong>SCK=GPIO${hxD.sck_pin ?? 6}</strong> (3.3V)</div>
              <div>Trọng lượng hiện tại: <strong class="tabular-nums">${Number(hx.last_grams || 0).toFixed(1)} g</strong></div>
              <div>Hệ số <code>scale_ratio</code>: <strong>${hxD.scale_ratio ?? "—"}</strong></div>
              <div style="margin-top:4px; color:var(--text-muted);">${hx.message || ""}</div>
            </div>
          </div>

          <div class="hw-node ${nodeClass(cam.status)}">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
              <strong>USB Camera (UVC)</strong>
              <span class="badge ${badgeClass(cam.status)}">${cam.status}</span>
            </div>
            <div style="font-size:12.5px; color:var(--text-secondary);">
              <div>Thiết bị: <strong>${camD.device || "/dev/video0"}</strong> (Index ${camD.index ?? 0})</div>
              <div>Chuẩn luồng: <strong>${camD.resolution || "640x480"} @ ${camD.fps || 30}fps (${camD.fourcc || "MJPG"})</strong></div>
              <div style="margin-top:4px; color:var(--text-muted);">${cam.message || ""}</div>
            </div>
          </div>
        </div>

        <div class="pi-core-box">
          <div style="font-weight:800; font-size:15px;">RASPBERRY PI 4</div>
          <div style="font-size:12px; color:#94A3B8; margin-bottom:10px;">ARM Cortex-A72 | Edge Node</div>
          <span class="badge ${hwData.mock_hardware ? "badge-warning" : "badge-success"}">
            ${hwData.mock_hardware ? "MOCK_HARDWARE=True" : "REAL HARDWARE"}
          </span>
          <div style="margin-top:12px; font-size:11.5px; color:#CBD5E1; text-align:left; line-height:1.7;">
            <div>GPIO 5/6: HX711 24-bit</div>
            <div>I2C-1 (GPIO 2/3): LCD 16x2</div>
            <div>USB 3.0: Webcam V4L2</div>
            <div>CPU NEON: YOLO26n NCNN</div>
          </div>
        </div>

        <div style="display:flex; flex-direction:column; gap:12px;">
          <div class="hw-node ${nodeClass(lcd.status)}">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
              <strong>LCD 16x2 I2C (PCF8574)</strong>
              <span class="badge ${badgeClass(lcd.status)}">${lcd.status}</span>
            </div>
            <div style="font-size:12.5px; color:var(--text-secondary); margin-bottom:6px;">
              Địa chỉ I2C: <strong>${lcdD.address || "0x27"}</strong> (Port ${lcdD.port ?? 1} | SDA=GPIO2, SCL=GPIO3)
            </div>
            <div class="lcd-preview">${(lcdD.line1 || "                ")}\n${(lcdD.line2 || "                ")}</div>
          </div>

          <div class="hw-node ${nodeClass(ai.status)}">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
              <strong>AI YOLO26n (NCNN)</strong>
              <span class="badge ${badgeClass(ai.status)}">${ai.status}</span>
            </div>
            <div style="font-size:12.5px; color:var(--text-secondary);">
              <div>Backend: <strong>${String(ai.backend || "mock").toUpperCase()}</strong> | Input: <strong>${ai.input_size || 416}x${ai.input_size || 416}</strong></div>
              <div>Số lớp mô hình: <strong>${ai.classes_count || 64} loại thực phẩm</strong></div>
              <div>Model files: param=${aiF.param_exists ? "OK" : "MISSING"}, bin=${aiF.bin_exists ? "OK" : "MISSING"}, yaml=${aiF.metadata_exists ? "OK" : "MISSING"}</div>
              <div style="margin-top:4px; color:var(--text-muted);">${ai.message || ""}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
}
