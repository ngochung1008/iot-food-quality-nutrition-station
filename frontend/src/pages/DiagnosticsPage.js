/**
 * Trang Quản trị Phần Cứng & Hiệu Chuẩn Cân HX711 (Chỉ Admin).
 */
import { renderHardwareStatus } from "../components/HardwareStatus.js";
import { apiClient } from "../services/apiClient.js";

export class DiagnosticsPage {
  constructor(toast) {
    this.toast = toast;
    this.hwData = null;
  }

  async mount(rootEl) {
    rootEl.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:18px;">
        <div id="hw-diagram-slot"></div>

        <div class="grid-2">
          <div class="card">
            <div class="card-head">
              <h3 class="card-title">Hiệu Chuẩn Cân Loadcell HX711 (Web Calibration)</h3>
              <span class="badge badge-info">hardware/calibration.json</span>
            </div>

            <div style="display:flex; flex-direction:column; gap:12px;">
              <div style="padding:12px; background:var(--bg-muted); border-radius:var(--radius); border:1px solid var(--border-light);">
                <strong>Bước 1: Lấy điểm 0 (Tare)</strong>
                <p style="margin:6px 0 10px; font-size:15px; color:var(--text-secondary);">
                  Đảm bảo đĩa cân đang <strong>trống hoàn toàn</strong>, sau đó nhấn nút bên dưới để lấy 21 mẫu trung vị làm điểm 0.
                </p>
                <button id="btn-cal-tare" class="btn btn-outline" type="button">Bước 1: Thực hiện Tare (Lấy điểm 0)</button>
                <div id="cal-step1-msg" style="margin-top:8px; font-size:15px; font-weight:600; color:var(--brand);"></div>
              </div>

              <div style="padding:12px; background:var(--bg-muted); border-radius:var(--radius); border:1px solid var(--border-light);">
                <strong>Bước 2: Đặt vật mẫu chuẩn &amp; Tính hệ số scale_ratio</strong>
                <p style="margin:6px 0 10px; font-size:15px; color:var(--text-secondary);">
                  Đặt quả cân chuẩn đã biết khối lượng (ví dụ 500g) lên tâm đĩa cân rồi nhấn Đo &amp; Lưu.
                </p>
                <div style="display:flex; flex-wrap:wrap; gap:8px; align-items:center;">
                  <input id="cal-known-weight" type="number" class="input" style="width:140px;" value="500" min="10" step="1" />
                  <span style="font-weight:700; font-size:15px;">gram</span>
                  <button id="btn-cal-measure" class="btn btn-primary" type="button">Bước 2: Đo vật mẫu &amp; Lưu</button>
                  <button id="btn-cal-invert" class="btn btn-outline" type="button">Đảo dấu</button>
                </div>
                <div id="cal-step2-msg" style="margin-top:8px; font-size:15px; font-weight:600; color:var(--success);"></div>
              </div>
            </div>
          </div>

          <div class="card">
            <div class="card-head">
              <h3 class="card-title">Kiểm Thử Màn Hình LCD 16x2 I2C &amp; PIN Bảo Mật</h3>
              <span class="badge badge-info">PCF8574</span>
            </div>

            <div style="display:flex; flex-direction:column; gap:12px;">
              <div>
                <label style="display:block; font-size:14.5px; font-weight:700; margin-bottom:4px;">Gửi thông điệp kiểm tra ra LCD 16x2:</label>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px;">
                  <input id="lcd-test-l1" class="input" maxlength="16" value="TEST LCD PI4 OK" placeholder="Dòng 1 (16 ký tự)" />
                  <input id="lcd-test-l2" class="input" maxlength="16" value="FRESHKITCHEN AI" placeholder="Dòng 2 (16 ký tự)" />
                </div>
                <button id="btn-lcd-test" class="btn btn-green" style="margin-top:10px;" type="button">Gửi hiển thị LCD</button>
              </div>

              <hr style="border:none; border-top:1px solid var(--border-light); width:100%;" />

              <div>
                <label style="display:block; font-size:14.5px; font-weight:700; margin-bottom:4px;">
                  Mã PIN bổ sung (nếu server cấu hình <code>ADMIN_PIN</code>):
                </label>
                <div style="display:flex; gap:8px;">
                  <input id="admin-pin-input" type="password" class="input" placeholder="Nhập PIN (để trống nếu không dùng)" />
                  <button id="btn-save-pin" class="btn btn-outline" type="button">Lưu PIN</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;

    const savedPin = localStorage.getItem("station_admin_pin") || "";
    const pinEl = document.getElementById("admin-pin-input");
    if (pinEl) pinEl.value = savedPin;

    await this.refreshHardware();
    this._bindEvents();
  }

  async refreshHardware() {
    try {
      this.hwData = await apiClient.getHardwareStatus();
      renderHardwareStatus(document.getElementById("hw-diagram-slot"), this.hwData);
      document.getElementById("btn-refresh-hw")?.addEventListener("click", () => this.refreshHardware());
    } catch (e) {
      this.toast(`Không tải được trạng thái phần cứng: ${e.message}`, "error");
    }
  }

  _bindEvents() {
    document.getElementById("btn-cal-tare")?.addEventListener("click", async () => {
      try {
        const res = await apiClient.calibrateTare();
        document.getElementById("cal-step1-msg").textContent = `${res.message} (offset=${res.offset})`;
        this.toast("Bước 1 Tare hoàn tất", "success");
        await this.refreshHardware();
      } catch (e) {
        this.toast(`Lỗi Bước 1: ${e.message}`, "error");
      }
    });

    document.getElementById("btn-cal-measure")?.addEventListener("click", async () => {
      const w = Number(document.getElementById("cal-known-weight")?.value || 0);
      try {
        const res = await apiClient.calibrateMeasure(w, true);
        document.getElementById("cal-step2-msg").textContent = res.message;
        this.toast("Hiệu chuẩn cân thành công", "success");
        await this.refreshHardware();
      } catch (e) {
        this.toast(`Lỗi hiệu chuẩn: ${e.message}`, "error");
      }
    });

    document.getElementById("btn-cal-invert")?.addEventListener("click", async () => {
      try {
        const res = await apiClient.calibrateInvert();
        this.toast(`Đã đảo dấu scale_ratio = ${res.scale_ratio}`, "info");
        await this.refreshHardware();
      } catch (e) {
        this.toast(e.message, "error");
      }
    });

    document.getElementById("btn-lcd-test")?.addEventListener("click", async () => {
      const l1 = document.getElementById("lcd-test-l1")?.value || "";
      const l2 = document.getElementById("lcd-test-l2")?.value || "";
      try {
        await apiClient.testLcd(l1, l2);
        this.toast("Đã gửi dữ liệu ra LCD 16x2", "success");
        await this.refreshHardware();
      } catch (e) {
        this.toast(e.message, "error");
      }
    });

    document.getElementById("btn-save-pin")?.addEventListener("click", () => {
      const val = document.getElementById("admin-pin-input")?.value || "";
      if (val) localStorage.setItem("station_admin_pin", val);
      else localStorage.removeItem("station_admin_pin");
      this.toast("Đã lưu PIN trình duyệt", "success");
    });
  }

  update() {}
}
