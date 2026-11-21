/**
 * Trang Lịch Sử Nhập Kho, Biểu Đồ Dinh Dưỡng, Xuất CSV/Excel & Bảng 64 Nguyên Liệu Chuẩn.
 */
import { apiClient, downloadProtectedFile, getAuthSession } from "../services/apiClient.js";

export class HistoryReportsPage {
  constructor(toast) {
    this.toast = toast;
    this.chart = null;
    this.macroChart = null;
  }

  async mount(rootEl) {
    const { user } = getAuthSession();
    const canEdit = user && (user.role === "ADMIN" || user.role === "CHEF");
    const isAdmin = user && user.role === "ADMIN";

    rootEl.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:18px;">
        <div class="kpi-grid" id="hr-kpi-grid">
          <div class="card"><div class="macro-label">Đang tải thống kê...</div></div>
        </div>

        <div class="grid-2">
          <div class="card">
            <div class="card-head">
              <h3 class="card-title">Năng Lượng &amp; Sản Lượng Nhập Kho (14 Ngày)</h3>
            </div>
            <div style="height:260px; position:relative;">
              <canvas id="hr-nutrition-chart"></canvas>
            </div>
          </div>

          <div class="card">
            <div class="card-head">
              <h3 class="card-title">Cơ Cấu Đạm / Béo / Đường Bột (7 Ngày)</h3>
            </div>
            <div style="height:260px; position:relative;">
              <canvas id="hr-macro-chart"></canvas>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <h3 class="card-title">Nhật Ký Tiếp Nhận &amp; Kiểm Định Thực Phẩm</h3>
            <div style="display:flex; flex-wrap:wrap; gap:8px; align-items:center;">
              <input id="f-date-from" type="date" class="input" style="min-height:36px;" />
              <input id="f-date-to" type="date" class="input" style="min-height:36px;" />
              <select id="f-quality" class="select" style="min-height:36px;">
                <option value="">Tất cả chất lượng</option>
                <option value="FRESH">FRESH (Đạt chuẩn)</option>
                <option value="WARNING">WARNING (Cảnh báo)</option>
                <option value="REJECTED">REJECTED (Từ chối)</option>
              </select>
              <button id="btn-filter-logs" class="btn btn-sm btn-primary" type="button">Lọc dữ liệu</button>
              <button id="btn-export-csv" class="btn btn-sm btn-outline" type="button">Xuất CSV</button>
              <button id="btn-export-xlsx" class="btn btn-sm btn-green" type="button">Xuất Excel (.xlsx)</button>
            </div>
          </div>

          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Ảnh</th>
                  <th>Mã lô &amp; Thời gian</th>
                  <th>Thực phẩm</th>
                  <th>Khối lượng</th>
                  <th>Chất lượng</th>
                  <th>Kcal</th>
                  <th>Protein / Lipid / Carb</th>
                  <th>Người xác nhận</th>
                  ${isAdmin ? "<th>Thao tác</th>" : ""}
                </tr>
              </thead>
              <tbody id="hr-logs-tbody">
                <tr><td colspan="9" style="text-align:center;">Đang tải dữ liệu...</td></tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <h3 class="card-title">Bảng Thành Phần Dinh Dưỡng Chuẩn (64 Lớp YOLO26n - per 100g)</h3>
            <input id="f-food-search" class="input" style="min-height:36px; width:260px;" placeholder="Tìm kiếm thực phẩm..." />
          </div>
          <div class="table-wrap" style="max-height:360px; overflow-y:auto;">
            <table>
              <thead>
                <tr>
                  <th>Nhãn AI</th>
                  <th>Tên tiếng Việt</th>
                  <th>Nhóm</th>
                  <th>Ăn được (%)</th>
                  <th>Kcal</th>
                  <th>Protein (g)</th>
                  <th>Lipid (g)</th>
                  <th>Carb (g)</th>
                  ${canEdit ? "<th>Lưu</th>" : ""}
                </tr>
              </thead>
              <tbody id="hr-foods-tbody"></tbody>
            </table>
          </div>
        </div>
      </div>
    `;

    this._bindEvents();
    await Promise.all([this.loadAnalytics(), this.loadLogs(), this.loadFoods()]);
  }

  _buildQuery() {
    const df = document.getElementById("f-date-from")?.value || "";
    const dt = document.getElementById("f-date-to")?.value || "";
    const q = document.getElementById("f-quality")?.value || "";
    const p = new URLSearchParams();
    if (df) p.set("date_from", df);
    if (dt) p.set("date_to", dt);
    if (q) p.set("quality_status", q);
    return { df, dt, q, qs: p.toString() };
  }

  _bindEvents() {
    document.getElementById("btn-filter-logs")?.addEventListener("click", () => this.loadLogs());
    document.getElementById("f-food-search")?.addEventListener("input", (e) => this.loadFoods(e.target.value));
    document.getElementById("btn-export-csv")?.addEventListener("click", async () => {
      try {
        const { qs } = this._buildQuery();
        await downloadProtectedFile(`/api/reports/export.csv${qs ? `?${qs}` : ""}`, "bao_cao_nhap_kho_dinh_duong.csv");
      } catch (e) {
        this.toast(e.message, "error");
      }
    });
    document.getElementById("btn-export-xlsx")?.addEventListener("click", async () => {
      try {
        const { qs } = this._buildQuery();
        await downloadProtectedFile(`/api/reports/export.xlsx${qs ? `?${qs}` : ""}`, "bao_cao_nhap_kho_dinh_duong.xlsx");
      } catch (e) {
        this.toast(e.message, "error");
      }
    });
  }

  async loadAnalytics() {
    try {
      const data = await apiClient.getAnalytics(14);
      const today = data.summary?.today || {};
      const period = data.summary?.period_summary || {};
      const orders = data.summary?.orders || {};
      const grid = document.getElementById("hr-kpi-grid");
      if (grid) {
        grid.innerHTML = `
          <div class="card">
            <div class="macro-label">Lô Kiểm Định (Hôm nay)</div>
            <div class="macro-val tabular-nums">${today.total_batches || 0} lô</div>
            <div class="macro-sub">Đạt: ${today.fresh_count || 0} | Từ chối: ${today.rejected_count || 0}</div>
          </div>
          <div class="card">
            <div class="macro-label">Khối Lượng Nhập Hôm Nay</div>
            <div class="macro-val tabular-nums">${Number(today.accepted_weight_kg || 0).toFixed(2)} kg</div>
            <div class="macro-sub">Tổng cân: ${Number(today.total_weight_kg || 0).toFixed(2)} kg</div>
          </div>
          <div class="card">
            <div class="macro-label">Năng Lượng Nhập Hôm Nay</div>
            <div class="macro-val tabular-nums">${Math.round(today.total_kcal || 0).toLocaleString("vi-VN")} kcal</div>
            <div class="macro-sub">P: ${Number(today.total_protein_g || 0).toFixed(0)}g | C: ${Number(today.total_carb_g || 0).toFixed(0)}g</div>
          </div>
          <div class="card">
            <div class="macro-label">Phiếu Yêu Cầu Nguyên Liệu</div>
            <div class="macro-val tabular-nums">${orders.completed_orders || 0} / ${orders.total_orders || 0} hoàn thành</div>
            <div class="macro-sub">Đang xử lý: ${orders.active_orders || 0} phiếu</div>
          </div>
        `;
      }
      this._renderCharts(data.daily || [], period);
    } catch (e) {
      console.warn(e);
    }
  }

  _renderCharts(daily, period) {
    if (typeof window.Chart === "undefined") return;
    const ctx1 = document.getElementById("hr-nutrition-chart");
    if (ctx1) {
      if (this.chart) this.chart.destroy();
      this.chart = new window.Chart(ctx1, {
        type: "bar",
        data: {
          labels: daily.map((d) => d.date),
          datasets: [
            {
              label: "Năng lượng (kcal)",
              data: daily.map((d) => d.total_kcal),
              backgroundColor: "rgba(46, 125, 50, 0.85)",
              yAxisID: "y",
            },
            {
              label: "Khối lượng nhận (kg)",
              data: daily.map((d) => d.accepted_weight_kg),
              type: "line",
              borderColor: "#F57C00",
              backgroundColor: "#F57C00",
              yAxisID: "y1",
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            y: { beginAtZero: true, position: "left" },
            y1: { beginAtZero: true, position: "right", grid: { drawOnChartArea: false } },
          },
        },
      });
    }

    const ctx2 = document.getElementById("hr-macro-chart");
    if (ctx2) {
      if (this.macroChart) this.macroChart.destroy();
      this.macroChart = new window.Chart(ctx2, {
        type: "doughnut",
        data: {
          labels: ["Protein (g)", "Lipid / Chất béo (g)", "Carbohydrate (g)"],
          datasets: [
            {
              data: [
                Number(period.total_protein_g || 0),
                Number(period.total_fat_g || 0),
                Number(period.total_carb_g || 0),
              ],
              backgroundColor: ["#1565C0", "#F57C00", "#2E7D32"],
            },
          ],
        },
        options: { responsive: true, maintainAspectRatio: false },
      });
    }
  }

  async loadLogs() {
    const tbody = document.getElementById("hr-logs-tbody");
    if (!tbody) return;
    const { user } = getAuthSession();
    const isAdmin = user && user.role === "ADMIN";
    const { df, dt, q } = this._buildQuery();

    try {
      const logs = await apiClient.getLogs({ date_from: df, date_to: dt, quality_status: q, limit: 150 });
      if (!logs.length) {
        tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; color:var(--text-muted);">Không có bản ghi phù hợp.</td></tr>`;
        return;
      }
      tbody.innerHTML = logs
        .map((r) => {
          const bClass =
            r.quality_status === "REJECTED"
              ? "badge-danger"
              : r.quality_status === "WARNING"
              ? "badge-warning"
              : "badge-success";
          const imgHtml = r.image_url
            ? `<img src="${r.image_url}" class="thumb-img" alt="${r.class_name}" />`
            : `<span style="color:var(--text-muted);">—</span>`;
          return `
            <tr>
              <td>${imgHtml}</td>
              <td><strong>${r.batch_code}</strong><br><span style="font-size:14px; color:var(--text-muted);">${r.local_date} ${r.timestamp.slice(11, 19)}</span></td>
              <td><strong>${r.food_name_vi}</strong><br><span style="font-size:14px; color:var(--text-muted);">${r.food_group}</span></td>
              <td class="tabular-nums"><strong>${Number(r.weight_gram).toFixed(1)} g</strong><br><span style="font-size:14px; color:var(--text-muted);">Ăn được: ${Number(r.edible_gram).toFixed(1)} g</span></td>
              <td><span class="badge ${bClass}">${r.quality_status} (${Math.round(r.confidence * 100)}%)</span></td>
              <td class="tabular-nums"><strong>${Number(r.energy_kcal).toFixed(1)}</strong> kcal</td>
              <td class="tabular-nums">${r.protein_g}g / ${r.fat_g}g / ${r.carbohydrate_g}g</td>
              <td>${r.confirmed_by || "—"}</td>
              ${isAdmin ? `<td><button class="btn btn-sm btn-outline btn-del-log" data-id="${r.id}">Xóa</button></td>` : ""}
            </tr>
          `;
        })
        .join("");

      tbody.querySelectorAll(".btn-del-log").forEach((btn) => {
        btn.addEventListener("click", async () => {
          if (!confirm("Xóa phiếu nhập kho này?")) return;
          try {
            await apiClient.deleteLog(btn.dataset.id);
            this.toast("Đã xóa phiếu nhập kho", "info");
            await Promise.all([this.loadLogs(), this.loadAnalytics()]);
          } catch (e) {
            this.toast(e.message, "error");
          }
        });
      });
    } catch (e) {
      this.toast(`Lỗi tải lịch sử: ${e.message}`, "error");
    }
  }

  async loadFoods(search = "") {
    const tbody = document.getElementById("hr-foods-tbody");
    if (!tbody) return;
    const { user } = getAuthSession();
    const canEdit = user && (user.role === "ADMIN" || user.role === "CHEF");
    try {
      const foods = await apiClient.getFoods(search);
      tbody.innerHTML = foods
        .map(
          (f) => `
          <tr data-food-id="${f.id}">
            <td><strong>${f.class_name}</strong></td>
            <td>${f.vietnamese_name}</td>
            <td>${f.food_group}</td>
            <td><input class="input food-edit" data-k="edible_portion_percent" type="number" step="1" style="width:72px; min-height:32px;" value="${f.edible_portion_percent}" ${canEdit ? "" : "disabled"} /></td>
            <td><input class="input food-edit" data-k="energy_kcal" type="number" step="0.1" style="width:78px; min-height:32px;" value="${f.energy_kcal}" ${canEdit ? "" : "disabled"} /></td>
            <td><input class="input food-edit" data-k="protein_g" type="number" step="0.1" style="width:72px; min-height:32px;" value="${f.protein_g}" ${canEdit ? "" : "disabled"} /></td>
            <td><input class="input food-edit" data-k="fat_g" type="number" step="0.1" style="width:72px; min-height:32px;" value="${f.fat_g}" ${canEdit ? "" : "disabled"} /></td>
            <td><input class="input food-edit" data-k="carbohydrate_g" type="number" step="0.1" style="width:72px; min-height:32px;" value="${f.carbohydrate_g}" ${canEdit ? "" : "disabled"} /></td>
            ${canEdit ? `<td><button class="btn btn-sm btn-green btn-save-food" type="button">Lưu</button></td>` : ""}
          </tr>
        `
        )
        .join("");

      tbody.querySelectorAll(".btn-save-food").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const row = btn.closest("tr");
          const id = Number(row.dataset.foodId);
          const fields = {};
          row.querySelectorAll(".food-edit").forEach((inp) => {
            fields[inp.dataset.k] = Number(inp.value);
          });
          try {
            await apiClient.updateFood(id, fields);
            this.toast("Đã cập nhật thông số dinh dưỡng", "success");
          } catch (e) {
            this.toast(e.message, "error");
          }
        });
      });
    } catch (e) {
      console.warn(e);
    }
  }

  update() {}
}
