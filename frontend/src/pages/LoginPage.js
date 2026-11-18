/**
 * Trang Đăng nhập thương mại FreshKitchen AI kèm 3 tài khoản demo theo vai trò RBAC.
 */
import { apiClient, setAuthSession } from "../services/apiClient.js";

export class LoginPage {
  constructor(toast, onSuccess) {
    this.toast = toast;
    this.onSuccess = onSuccess;
  }

  mount(rootEl) {
    rootEl.innerHTML = `
      <div class="login-shell">
        <div class="login-card">
          <div style="display:flex; align-items:center; gap:12px; margin-bottom:18px;">
            <div class="brand-mark">FK</div>
            <div>
              <h1 style="margin:0; font-size:20px; font-weight:800; color:var(--text-primary);">
                FreshKitchen Enterprise
              </h1>
              <p style="margin:0; font-size:12.5px; color:var(--text-muted);">
                Hệ thống quản lý thực đơn, kiểm định chất lượng &amp; định lượng dinh dưỡng
              </p>
            </div>
          </div>

          <form id="login-form" style="display:flex; flex-direction:column; gap:12px;">
            <div>
              <label for="login-username" style="display:block; font-size:12.5px; font-weight:700; color:var(--text-secondary); margin-bottom:4px;">
                Tên đăng nhập
              </label>
              <input id="login-username" class="input" style="width:100%;" placeholder="Nhập tên đăng nhập..." required />
            </div>

            <div>
              <label for="login-password" style="display:block; font-size:12.5px; font-weight:700; color:var(--text-secondary); margin-bottom:4px;">
                Mật khẩu
              </label>
              <input id="login-password" type="password" class="input" style="width:100%;" placeholder="Nhập mật khẩu..." required />
            </div>

            <button id="btn-login-submit" class="btn btn-primary" type="submit" style="width:100%; margin-top:4px;">
              Đăng nhập hệ thống
            </button>
          </form>

          <div style="margin-top:20px; padding-top:16px; border-top:1px solid var(--border-light);">
            <div style="font-size:12px; font-weight:700; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.03em;">
              Tài khoản Demo (Nhấn để đăng nhập nhanh)
            </div>
            <div class="demo-account-grid">
              <button type="button" class="demo-btn" data-user="admin" data-pass="admin123">
                <div>
                  <div style="font-weight:700; font-size:13.5px; color:var(--text-primary);">Quản trị viên (Admin)</div>
                  <div style="font-size:12px; color:var(--text-muted);">admin / admin123 — Toàn quyền báo cáo, nhân sự, hiệu chuẩn</div>
                </div>
                <span class="badge badge-success">ADMIN</span>
              </button>

              <button type="button" class="demo-btn" data-user="chef" data-pass="chef123">
                <div>
                  <div style="font-weight:700; font-size:13.5px; color:var(--text-primary);">Đầu bếp trưởng (Chef)</div>
                  <div style="font-size:12px; color:var(--text-muted);">chef / chef123 — Lập thực đơn, tính Calo, đẩy phiếu nguyên liệu</div>
                </div>
                <span class="badge badge-info">CHEF</span>
              </button>

              <button type="button" class="demo-btn" data-user="receiver" data-pass="receiver123">
                <div>
                  <div style="font-weight:700; font-size:13.5px; color:var(--text-primary);">Nhân viên tiếp nhận &amp; QC</div>
                  <div style="font-size:12px; color:var(--text-muted);">receiver / receiver123 — Vận hành trạm cân Pi 4, kiểm định &amp; tích xanh</div>
                </div>
                <span class="badge badge-warning">RECEIVER</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    `;

    const doLogin = async (username, password) => {
      try {
        const res = await apiClient.login(username, password);
        setAuthSession(res.access_token, res.user);
        this.toast(`Xin chào, ${res.user.full_name}`, "success");
        this.onSuccess?.(res.user);
      } catch (err) {
        this.toast(err.message, "error");
      }
    };

    document.getElementById("login-form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const u = document.getElementById("login-username").value.trim();
      const p = document.getElementById("login-password").value;
      await doLogin(u, p);
    });

    rootEl.querySelectorAll(".demo-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const u = btn.dataset.user;
        const p = btn.dataset.pass;
        document.getElementById("login-username").value = u;
        document.getElementById("login-password").value = p;
        await doLogin(u, p);
      });
    });
  }
}
