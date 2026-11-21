/**
 * Trang của Đầu bếp trưởng (Chef) & Admin:
 * - Lập kế hoạch bữa ăn (Chọn món + Số lượng suất ăn) -> Tính tổng Calo/Macro -> Đẩy Phiếu Yêu Cầu Nguyên Liệu.
 * - Quản lý & tạo mới Món ăn chuẩn chỉ sử dụng 64 nguyên liệu từ YOLO26n dataset.
 */
import { apiClient } from "../services/apiClient.js";

export class ChefMenuPage {
  constructor(toast) {
    this.toast = toast;
    this.dishes = [];
    this.foods64 = [];
    this.orders = [];
    this.selectedDishIds = new Set();
    this.newDishIngredients = [{ class_name: "Fish", grams_per_serving: 150 }];
  }

  async mount(rootEl) {
    const today = new Date().toISOString().slice(0, 10);
    rootEl.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:18px;">
        <!-- Phần 1: Lập thực đơn bữa ăn & Sinh Phiếu Yêu Cầu Nguyên Liệu -->
        <div class="grid-2">
          <div class="card">
            <div class="card-head">
              <h3 class="card-title">Lập Kế Hoạch Thực Đơn &amp; Tính Toán Định Lượng</h3>
              <span class="badge badge-info">Quy chuẩn 64 nguyên liệu AI</span>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px; margin-bottom:12px;">
              <div>
                <label style="display:block; font-size:14px; font-weight:700; color:var(--text-muted); margin-bottom:4px;">Tên kế hoạch bữa ăn</label>
                <input id="plan-title" class="input" style="width:100%;" value="Thực đơn Bữa Trưa Tập Thể" />
              </div>
              <div>
                <label style="display:block; font-size:14px; font-weight:700; color:var(--text-muted); margin-bottom:4px;">Ngày phục vụ</label>
                <input id="plan-date" type="date" class="input" style="width:100%;" value="${today}" />
              </div>
              <div>
                <label style="display:block; font-size:14px; font-weight:700; color:var(--text-muted); margin-bottom:4px;">Ca ăn</label>
                <select id="plan-shift" class="select" style="width:100%;">
                  <option value="Bữa sáng">Bữa sáng</option>
                  <option value="Bữa trưa" selected>Bữa trưa</option>
                  <option value="Bữa tối">Bữa tối</option>
                  <option value="Bữa phụ">Bữa phụ</option>
                </select>
              </div>
              <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px;">
                <div>
                  <label style="display:block; font-size:14px; font-weight:700; color:var(--text-muted); margin-bottom:4px;">Số suất ăn</label>
                  <input id="plan-servings" type="number" min="1" max="10000" class="input" style="width:100%;" value="50" />
                </div>
                <div>
                  <label style="display:block; font-size:14px; font-weight:700; color:var(--text-muted); margin-bottom:4px;">Mục tiêu kcal/suất</label>
                  <input id="plan-target-kcal" type="number" min="100" max="5000" class="input" style="width:100%;" value="650" />
                </div>
                <div>
                  <label style="display:block; font-size:14px; font-weight:700; color:var(--text-muted); margin-bottom:4px;">Sai số (%)</label>
                  <input id="plan-tolerance" type="number" min="0" max="25" class="input" style="width:100%;" value="5" />
                </div>
              </div>
            </div>

            <div style="font-size:14.5px; font-weight:700; color:var(--text-secondary); margin-bottom:6px;">
              Chọn món ăn cho thực đơn:
            </div>
            <div id="chef-dish-picker" style="max-height:280px; overflow-y:auto; border:1px solid var(--border-light); border-radius:var(--radius); padding:8px; display:flex; flex-direction:column; gap:6px;">
              Đang tải danh sách món ăn...
            </div>
          </div>

          <!-- Bảng tổng hợp Calo & Checklist nguyên liệu chuẩn bị -->
          <div class="card">
            <div class="card-head">
              <h3 class="card-title">Dự Toán Calo &amp; Phiếu Yêu Cầu Nguyên Liệu</h3>
              <span id="plan-selected-count" class="badge badge-neutral">0 món đã chọn</span>
            </div>

            <div class="macro-grid" style="margin-top:0;">
              <div class="macro-card">
                <div class="macro-label">Tổng Năng Lượng</div>
                <div class="macro-val tabular-nums" id="plan-kcal">0</div>
                <div class="macro-sub" id="plan-kcal-per">0 kcal / suất</div>
              </div>
              <div class="macro-card">
                <div class="macro-label">Tổng Protein</div>
                <div class="macro-val tabular-nums" id="plan-prot">0 g</div>
                <div class="macro-sub" id="plan-prot-per">0 g / suất</div>
              </div>
              <div class="macro-card">
                <div class="macro-label">Tổng Lipid</div>
                <div class="macro-val tabular-nums" id="plan-fat">0 g</div>
                <div class="macro-sub" id="plan-fat-per">0 g / suất</div>
              </div>
              <div class="macro-card">
                <div class="macro-label">Tổng Carb</div>
                <div class="macro-val tabular-nums" id="plan-carb">0 g</div>
                <div class="macro-sub" id="plan-carb-per">0 g / suất</div>
              </div>
            </div>

            <div class="table-wrap" style="max-height:210px; overflow-y:auto; margin-bottom:12px;">
              <table>
                <thead>
                  <tr>
                    <th>Nguyên liệu (64 lớp AI)</th>
                    <th>Chuẩn cần nhập</th>
                    <th>Đơn giá dự kiến</th>
                    <th>Đạt chuẩn (≥95%)</th>
                  </tr>
                </thead>
                <tbody id="plan-ingredients-preview">
                  <tr><td colspan="3" style="text-align:center; color:var(--text-muted);">Chọn ít nhất 1 món ăn ở bên trái</td></tr>
                </tbody>
              </table>
            </div>

            <button id="btn-push-order" class="btn btn-primary" style="width:100%;" type="button">
              Tạo &amp; Đẩy Phiếu Nguyên Liệu Xuống Trạm Cân
            </button>
          </div>
        </div>

        <!-- Phần 2: Danh sách Phiếu Yêu Cầu Nguyên Liệu đã tạo -->
        <div class="card">
          <div class="card-head">
            <h3 class="card-title">Trạng Thái Các Phiếu Yêu Cầu Nguyên Liệu Tại Trạm Cân</h3>
            <button id="btn-refresh-orders" class="btn btn-sm btn-outline" type="button">Làm mới</button>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Mã phiếu</th>
                  <th>Tên kế hoạch / Ca ăn</th>
                  <th>Số suất</th>
                  <th>Tổng Calo</th>
                  <th>Tiến độ cân đối chiếu</th>
                  <th>Trạng thái</th>
                </tr>
              </thead>
              <tbody id="chef-orders-tbody"></tbody>
            </table>
          </div>
        </div>

        <!-- Phần 3: Tạo mới Món ăn chuẩn từ 64 nguyên liệu trong Dataset -->
        <div class="card">
          <div class="card-head">
            <h3 class="card-title">Tạo Mới Món Ăn Chuẩn (Chỉ Dùng 64 Nguyên Liệu YOLO26n)</h3>
            <span class="badge badge-success">Đảm bảo AI nhận diện 100%</span>
          </div>

          <div style="display:grid; grid-template-columns:1.2fr 1fr 1.5fr; gap:10px; margin-bottom:12px;">
            <input id="new-dish-name" class="input" placeholder="Tên món ăn (VD: Cá hấp cà chua thì là)" />
            <select id="new-dish-cat" class="select">
              <option value="Món mặn chính">Món mặn chính</option>
              <option value="Món canh">Món canh</option>
              <option value="Món rau / Salad">Món rau / Salad</option>
              <option value="Tráng miệng">Tráng miệng</option>
              <option value="Bữa phụ">Bữa phụ</option>
            </select>
            <input id="new-dish-desc" class="input" placeholder="Mô tả ngắn món ăn..." />
          </div>

          <div id="new-dish-ing-list" style="display:flex; flex-direction:column; gap:8px; margin-bottom:12px;"></div>

          <div style="display:flex; gap:10px; flex-wrap:wrap;">
            <button id="btn-add-ing-row" class="btn btn-outline btn-sm" type="button">+ Thêm nguyên liệu</button>
            <button id="btn-save-dish" class="btn btn-green" type="button">Lưu món ăn mới vào thực đơn</button>
          </div>
        </div>
      </div>
    `;

    await this.loadData();
    this._bindEvents();
  }

  async loadData() {
    try {
      const [dishes, foods, orders] = await Promise.all([
        apiClient.getDishes(),
        apiClient.getFoods(),
        apiClient.getOrders(),
      ]);
      this.dishes = dishes;
      this.foods64 = foods;
      this.orders = orders;
      if (this.selectedDishIds.size === 0 && dishes.length >= 2) {
        this.selectedDishIds.add(dishes[0].id);
        this.selectedDishIds.add(dishes[1].id);
      }
      this._renderDishPicker();
      this._recalcMealPlan();
      this._renderOrdersTable();
      this._renderIngredientRows();
    } catch (e) {
      this.toast(`Lỗi tải dữ liệu thực đơn: ${e.message}`, "error");
    }
  }

  _renderDishPicker() {
    const picker = document.getElementById("chef-dish-picker");
    if (!picker) return;
    picker.innerHTML = this.dishes
      .map((d) => {
        const checked = this.selectedDishIds.has(d.id) ? "checked" : "";
        const ingText = d.ingredients.map((i) => `${i.vietnamese_name} (${i.grams_per_serving}g)`).join(", ");
        return `
          <label style="display:flex; align-items:flex-start; gap:10px; padding:8px 10px; border-radius:6px; border:1px solid var(--border-light); cursor:pointer; background:${checked ? "var(--bg-green-soft)" : "#fff"};">
            <input type="checkbox" class="dish-chk" value="${d.id}" ${checked} style="margin-top:3px; width:18px; height:18px;" />
            <div style="flex:1;">
              <div style="display:flex; justify-content:space-between; gap:8px;">
                <strong style="font-size:16px;">${d.name_vi}</strong>
                <span class="badge badge-neutral">${d.per_serving.energy_kcal} kcal/suất</span>
              </div>
              <div style="font-size:14px; color:var(--text-muted); margin-top:2px;">${ingText}</div>
            </div>
          </label>
        `;
      })
      .join("");

    picker.querySelectorAll(".dish-chk").forEach((chk) => {
      chk.addEventListener("change", () => {
        const id = Number(chk.value);
        if (chk.checked) this.selectedDishIds.add(id);
        else this.selectedDishIds.delete(id);
        this._renderDishPicker();
        this._recalcMealPlan();
      });
    });
  }

  _recalcMealPlan() {
    const servings = Math.max(1, Number(document.getElementById("plan-servings")?.value || 1));
    const tol = Math.max(0, Number(document.getElementById("plan-tolerance")?.value || 5));

    let kcalPer = 0, protPer = 0, fatPer = 0, carbPer = 0;
    const agg = new Map();

    this.dishes.forEach((d) => {
      if (!this.selectedDishIds.has(d.id)) return;
      kcalPer += d.per_serving.energy_kcal;
      protPer += d.per_serving.protein_g;
      fatPer += d.per_serving.fat_g;
      carbPer += d.per_serving.carbohydrate_g;
      d.ingredients.forEach((ing) => {
        const foodMeta = this.foods64.find((f) => f.class_name === ing.class_name);
        const unitPrice = foodMeta?.unit_price_vnd_per_kg || 40000;
        const cur = agg.get(ing.class_name) || {
          name: ing.vietnamese_name,
          cls: ing.class_name,
          grams: 0,
          unitPrice,
        };
        cur.grams += ing.grams_per_serving * servings;
        agg.set(ing.class_name, cur);
      });
    });

    const setText = (id, txt) => {
      const el = document.getElementById(id);
      if (el) el.textContent = txt;
    };
    const targetKcal = Number(document.getElementById("plan-target-kcal")?.value || 650);

    setText("plan-selected-count", `${this.selectedDishIds.size} món đã chọn`);
    setText("plan-kcal", `${Math.round(kcalPer * servings).toLocaleString("vi-VN")} kcal`);
    setText("plan-kcal-per", `${kcalPer.toFixed(1)} / mục tiêu ${targetKcal} kcal`);
    setText("plan-prot", `${(protPer * servings).toFixed(1)} g`);
    setText("plan-prot-per", `${protPer.toFixed(1)} g / suất`);
    setText("plan-fat", `${(fatPer * servings).toFixed(1)} g`);
    setText("plan-fat-per", `${fatPer.toFixed(1)} g / suất`);
    setText("plan-carb", `${(carbPer * servings).toFixed(1)} g`);
    setText("plan-carb-per", `${carbPer.toFixed(1)} g / suất`);

    const tbody = document.getElementById("plan-ingredients-preview");
    if (!tbody) return;
    const rows = Array.from(agg.values()).sort((a, b) => b.grams - a.grams);
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--text-muted);">Chưa có món ăn được chọn</td></tr>`;
      return;
    }
    tbody.innerHTML = rows
      .map((r) => {
        const minG = r.grams * (1 - tol / 100);
        const estCost = Math.round((r.grams / 1000) * r.unitPrice);
        return `
          <tr>
            <td><strong>${r.name}</strong> <span style="color:var(--text-muted);">(${r.cls})</span></td>
            <td class="tabular-nums"><strong>${r.grams.toLocaleString("vi-VN")} g</strong> (${(r.grams / 1000).toFixed(2)} kg)</td>
            <td class="tabular-nums">${r.unitPrice.toLocaleString("vi-VN")} đ/kg<br><span style="font-size:14px; color:var(--text-muted);">~${estCost.toLocaleString("vi-VN")} đ</span></td>
            <td class="tabular-nums">>= ${minG.toFixed(0)} g (-${tol}%)</td>
          </tr>
        `;
      })
      .join("");
  }

  _renderOrdersTable() {
    const tbody = document.getElementById("chef-orders-tbody");
    if (!tbody) return;
    if (!this.orders.length) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--text-muted);">Chưa có phiếu yêu cầu nào.</td></tr>`;
      return;
    }
    tbody.innerHTML = this.orders
      .map((o) => {
        const stBadge =
          o.status === "COMPLETED"
            ? `<span class="badge badge-success">HOÀN THÀNH ĐƠN HÀNG</span>`
            : o.status === "IN_PROGRESS"
            ? `<span class="badge badge-warning">ĐANG CÂN ĐỐI CHIẾU</span>`
            : `<span class="badge badge-info">CHỜ TIẾP NHẬN</span>`;
        return `
          <tr>
            <td class="tabular-nums"><strong>${o.order_code}</strong></td>
            <td><strong>${o.title}</strong><br><span style="font-size:14px; color:var(--text-muted);">${o.meal_date} | ${o.meal_shift}</span></td>
            <td class="tabular-nums">${o.servings} suất</td>
            <td class="tabular-nums">${Math.round(o.total_kcal).toLocaleString("vi-VN")} kcal</td>
            <td>
              <div style="font-size:14px; font-weight:700;">${o.progress.completed} / ${o.progress.total} nguyên liệu (${o.progress.percent}%)</div>
              <div class="progress-track" style="width:140px;"><div class="progress-fill" style="width:${o.progress.percent}%;"></div></div>
            </td>
            <td>${stBadge}</td>
          </tr>
        `;
      })
      .join("");
  }

  _renderIngredientRows() {
    const host = document.getElementById("new-dish-ing-list");
    if (!host) return;
    const options = this.foods64
      .map((f) => `<option value="${f.class_name}">${f.vietnamese_name} (${f.class_name})</option>`)
      .join("");

    host.innerHTML = this.newDishIngredients
      .map(
        (row, idx) => `
        <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;" data-idx="${idx}">
          <select class="select ing-cls" style="flex:1; min-width:240px;">${options}</select>
          <input type="number" class="input ing-grams" style="width:140px;" min="1" step="1" value="${row.grams_per_serving}" placeholder="gram/suất" />
          <span style="font-size:14.5px; color:var(--text-muted);">g / suất</span>
          <button type="button" class="btn btn-sm btn-outline btn-rem-ing">Xóa</button>
        </div>
      `
      )
      .join("");

    host.querySelectorAll("[data-idx]").forEach((div) => {
      const idx = Number(div.dataset.idx);
      const sel = div.querySelector(".ing-cls");
      const inp = div.querySelector(".ing-grams");
      sel.value = this.newDishIngredients[idx].class_name;
      sel.addEventListener("change", () => {
        this.newDishIngredients[idx].class_name = sel.value;
      });
      inp.addEventListener("input", () => {
        this.newDishIngredients[idx].grams_per_serving = Number(inp.value || 0);
      });
      div.querySelector(".btn-rem-ing").addEventListener("click", () => {
        if (this.newDishIngredients.length <= 1) return;
        this.newDishIngredients.splice(idx, 1);
        this._renderIngredientRows();
      });
    });
  }

  _bindEvents() {
    document.getElementById("plan-servings")?.addEventListener("input", () => this._recalcMealPlan());
    document.getElementById("plan-target-kcal")?.addEventListener("input", () => this._recalcMealPlan());
    document.getElementById("plan-tolerance")?.addEventListener("input", () => this._recalcMealPlan());
    document.getElementById("btn-refresh-orders")?.addEventListener("click", () => this.loadData());

    document.getElementById("btn-push-order")?.addEventListener("click", async () => {
      try {
        const payload = {
          title: document.getElementById("plan-title")?.value.trim() || "Thực đơn bếp ăn",
          meal_date: document.getElementById("plan-date")?.value,
          meal_shift: document.getElementById("plan-shift")?.value,
          servings: Number(document.getElementById("plan-servings")?.value || 50),
          target_kcal_per_serving: Number(document.getElementById("plan-target-kcal")?.value || 650),
          tolerance_percent: Number(document.getElementById("plan-tolerance")?.value || 5),
          dish_ids: Array.from(this.selectedDishIds),
        };
        const order = await apiClient.createOrder(payload);
        this.toast(`Đã đẩy phiếu ${order.order_code} xuống trạm cân!`, "success");
        await this.loadData();
      } catch (e) {
        this.toast(e.message, "error");
      }
    });

    document.getElementById("btn-add-ing-row")?.addEventListener("click", () => {
      this.newDishIngredients.push({ class_name: this.foods64[0]?.class_name || "Tomato", grams_per_serving: 50 });
      this._renderIngredientRows();
    });

    document.getElementById("btn-save-dish")?.addEventListener("click", async () => {
      try {
        const name = document.getElementById("new-dish-name")?.value.trim();
        const cat = document.getElementById("new-dish-cat")?.value;
        const desc = document.getElementById("new-dish-desc")?.value.trim() || "";
        await apiClient.createDish({
          name_vi: name,
          category: cat,
          description: desc,
          ingredients: this.newDishIngredients,
        });
        this.toast(`Đã thêm món "${name}" vào thực đơn!`, "success");
        document.getElementById("new-dish-name").value = "";
        document.getElementById("new-dish-desc").value = "";
        await this.loadData();
      } catch (e) {
        this.toast(e.message, "error");
      }
    });
  }

  update() {}

  onOrderEvent() {
    this.loadData();
  }
}
