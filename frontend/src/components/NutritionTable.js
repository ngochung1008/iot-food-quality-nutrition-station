/**
 * Component đánh giá chất lượng đầu vào & bảng định lượng dinh dưỡng theo trọng lượng cân.
 */
export function renderNutritionTable(container, foodsList = []) {
  const optionsHtml = foodsList
    .map((f) => `<option value="${f.class_name}">${f.vietnamese_name} (${f.class_name})</option>`)
    .join("");

  container.innerHTML = `
    <div class="card">
      <div class="card-head">
        <h3 class="card-title">Chất Lượng &amp; Giá Trị Dinh Dưỡng Thực Tế</h3>
        <span id="nt-edible-badge" class="badge badge-info">Phần ăn được: 100%</span>
      </div>

      <div id="nt-quality-banner" class="quality-banner success">
        <div style="font-size:14px; font-weight:800;" id="nt-quality-title">SẴN SÀNG TIẾP NHẬN THỰC PHẨM</div>
        <div style="font-size:12.5px; margin-top:2px;" id="nt-quality-desc">
          Đặt thực phẩm lên cân để tự động đánh giá độ tươi sạch và định lượng dinh dưỡng.
        </div>
      </div>

      <div style="display:flex; flex-wrap:wrap; gap:10px; align-items:flex-end; margin-bottom:12px;">
        <div style="flex:1; min-width:210px;">
          <label for="nt-food-select" style="display:block; font-size:12px; font-weight:700; color:var(--text-muted); margin-bottom:4px;">
            Loại thực phẩm (64 lớp YOLO26n)
          </label>
          <select id="nt-food-select" class="select" style="width:100%;">
            <option value="">-- Chờ AI nhận diện --</option>
            ${optionsHtml}
          </select>
        </div>
        <div style="min-width:150px;">
          <div style="font-size:12px; font-weight:700; color:var(--text-muted); margin-bottom:4px;">Nhóm thực phẩm</div>
          <div id="nt-food-group" style="font-size:13.5px; font-weight:700; padding:9px 12px; background:var(--bg-muted); border-radius:var(--radius); border:1px solid var(--border-light);">—</div>
        </div>
      </div>

      <div class="macro-grid">
        <div class="macro-card">
          <div class="macro-label">Năng lượng</div>
          <div class="macro-val tabular-nums" id="nt-kcal">0.0 <span style="font-size:12px;">kcal</span></div>
          <div class="macro-sub" id="nt-kcal-pct">0% nhu cầu ngày</div>
          <div class="progress-track"><div id="nt-kcal-bar" class="progress-fill" style="width:0%; background:#2E7D32;"></div></div>
        </div>
        <div class="macro-card">
          <div class="macro-label">Protein (Đạm)</div>
          <div class="macro-val tabular-nums" id="nt-protein">0.0 <span style="font-size:12px;">g</span></div>
          <div class="macro-sub" id="nt-protein-pct">0% nhu cầu ngày</div>
          <div class="progress-track"><div id="nt-protein-bar" class="progress-fill" style="width:0%; background:#1565C0;"></div></div>
        </div>
        <div class="macro-card">
          <div class="macro-label">Lipid (Béo)</div>
          <div class="macro-val tabular-nums" id="nt-fat">0.0 <span style="font-size:12px;">g</span></div>
          <div class="macro-sub" id="nt-fat-pct">0% nhu cầu ngày</div>
          <div class="progress-track"><div id="nt-fat-bar" class="progress-fill" style="width:0%; background:#F57C00;"></div></div>
        </div>
        <div class="macro-card">
          <div class="macro-label">Carbohydrate</div>
          <div class="macro-val tabular-nums" id="nt-carb">0.0 <span style="font-size:12px;">g</span></div>
          <div class="macro-sub" id="nt-carb-pct">0% nhu cầu ngày</div>
          <div class="progress-track"><div id="nt-carb-bar" class="progress-fill" style="width:0%; background:#6A1B9A;"></div></div>
        </div>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Chỉ số vi chất &amp; Chất xơ</th>
              <th>Chuẩn / 100g</th>
              <th>Thực tế (<span id="nt-edible-g">0g</span> ăn được)</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Chất xơ (Fiber)</td>
              <td class="tabular-nums" id="nt-100-fiber">—</td>
              <td class="tabular-nums" style="font-weight:700;" id="nt-act-fiber">0 g</td>
            </tr>
            <tr>
              <td>Canxi (Calcium)</td>
              <td class="tabular-nums" id="nt-100-ca">—</td>
              <td class="tabular-nums" style="font-weight:700;" id="nt-act-ca">0 mg</td>
            </tr>
            <tr>
              <td>Sắt (Iron)</td>
              <td class="tabular-nums" id="nt-100-fe">—</td>
              <td class="tabular-nums" style="font-weight:700;" id="nt-act-fe">0 mg</td>
            </tr>
            <tr>
              <td>Vitamin C</td>
              <td class="tabular-nums" id="nt-100-vitc">—</td>
              <td class="tabular-nums" style="font-weight:700;" id="nt-act-vitc">0 mg</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div id="nt-source" style="margin-top:8px; font-size:12px; color:var(--text-muted);">
        Nguồn tham chiếu: Bảng Thành Phần Thực Phẩm Việt Nam (VTN_FCT_2007 - Viện Dinh Dưỡng)
      </div>
    </div>
  `;
}

export function updateNutritionTable(snapshot) {
  const insp = snapshot?.current_inspection;
  const banner = document.getElementById("nt-quality-banner");
  const qTitle = document.getElementById("nt-quality-title");
  const qDesc = document.getElementById("nt-quality-desc");
  const selectEl = document.getElementById("nt-food-select");
  const groupEl = document.getElementById("nt-food-group");
  const edibleBadge = document.getElementById("nt-edible-badge");

  if (!banner || !qTitle || !qDesc) return;

  if (!insp) {
    banner.className = "quality-banner success";
    qTitle.textContent = "SẴN SÀNG TIẾP NHẬN THỰC PHẨM";
    qDesc.textContent = "Đặt thực phẩm từ 15g trở lên để kiểm định chất lượng và tính dinh dưỡng.";
    if (groupEl) groupEl.textContent = "—";
    if (selectEl && document.activeElement !== selectEl) selectEl.value = "";
    return;
  }

  const qual = insp.quality || {};
  banner.className = `quality-banner ${qual.alert_level || "success"}`;
  qTitle.textContent = qual.badge_text || qual.status || "ĐẠT CHUẨN";
  qDesc.textContent = qual.recommendation || "";

  const nut = insp.nutrition || {};
  const act = nut.actual || {};
  const p100 = nut.per_100g || {};
  const pct = nut.daily_percent || {};

  if (selectEl && document.activeElement !== selectEl && nut.class_name) {
    selectEl.value = nut.class_name;
  }
  if (groupEl) groupEl.textContent = nut.food_group || "—";
  if (edibleBadge) {
    edibleBadge.textContent = `Ăn được: ${nut.edible_portion_percent || 100}% (${nut.edible_gram || 0}g)`;
  }

  const setText = (id, text) => {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  };
  const setHtml = (id, html) => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
  };
  const setBar = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.style.width = `${Math.min(100, Math.max(0, Number(val || 0)))}%`;
  };

  setHtml("nt-kcal", `${Number(act.energy_kcal || 0).toFixed(1)} <span style="font-size:12px;">kcal</span>`);
  setText("nt-kcal-pct", `${pct.kcal_pct || 0}% (2000 kcal)`);
  setBar("nt-kcal-bar", pct.kcal_pct);

  setHtml("nt-protein", `${Number(act.protein_g || 0).toFixed(1)} <span style="font-size:12px;">g</span>`);
  setText("nt-protein-pct", `${pct.protein_pct || 0}% (60g)`);
  setBar("nt-protein-bar", pct.protein_pct);

  setHtml("nt-fat", `${Number(act.fat_g || 0).toFixed(1)} <span style="font-size:12px;">g</span>`);
  setText("nt-fat-pct", `${pct.fat_pct || 0}% (65g)`);
  setBar("nt-fat-bar", pct.fat_pct);

  setHtml("nt-carb", `${Number(act.carbohydrate_g || 0).toFixed(1)} <span style="font-size:12px;">g</span>`);
  setText("nt-carb-pct", `${pct.carb_pct || 0}% (300g)`);
  setBar("nt-carb-bar", pct.carb_pct);

  setText("nt-edible-g", `${nut.edible_gram || 0}g`);
  setText("nt-100-fiber", p100.fiber_g !== undefined ? `${p100.fiber_g} g` : "—");
  setText("nt-act-fiber", `${act.fiber_g || 0} g`);
  setText("nt-100-ca", p100.calcium_mg !== undefined ? `${p100.calcium_mg} mg` : "—");
  setText("nt-act-ca", `${act.calcium_mg || 0} mg`);
  setText("nt-100-fe", p100.iron_mg !== undefined ? `${p100.iron_mg} mg` : "—");
  setText("nt-act-fe", `${act.iron_mg || 0} mg`);
  setText("nt-100-vitc", p100.vitamin_c_mg !== undefined ? `${p100.vitamin_c_mg} mg` : "—");
  setText("nt-act-vitc", `${act.vitamin_c_mg || 0} mg`);
  setText("nt-source", `Nguồn tham chiếu: ${nut.source || "VTN_FCT_2007"}`);
}
