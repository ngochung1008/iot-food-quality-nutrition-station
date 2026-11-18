/**
 * Client giao tiếp REST API tới Backend FastAPI (tích hợp JWT Bearer Token & Blob export).
 */
const TOKEN_KEY = "fresh_station_token";
const USER_KEY = "fresh_station_user";

export function getAuthSession() {
  const token = localStorage.getItem(TOKEN_KEY);
  const rawUser = localStorage.getItem(USER_KEY);
  let user = null;
  try {
    user = rawUser ? JSON.parse(rawUser) : null;
  } catch {
    user = null;
  }
  return { token, user };
}

export function setAuthSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearAuthSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

async function request(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const { token } = getAuthSession();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const adminPin = localStorage.getItem("station_admin_pin");
  if (adminPin) {
    headers["X-Admin-Pin"] = adminPin;
  }

  const res = await fetch(url, { ...options, headers });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }

  if (res.status === 401 && !url.includes("/api/auth/login")) {
    clearAuthSession();
    window.dispatchEvent(new CustomEvent("auth:unauthorized"));
  }

  if (!res.ok) {
    const msg = (data && data.detail) || (data && data.error) || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

export async function downloadProtectedFile(url, filename) {
  const { token } = getAuthSession();
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await fetch(url, { headers });
  if (!res.ok) throw new Error(`Không thể xuất file (HTTP ${res.status})`);
  const blob = await res.blob();
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
}

export const apiClient = {
  // Auth & Users
  login: (username, password) =>
    request("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  getMe: () => request("/api/auth/me"),
  getUsers: () => request("/api/users"),
  createUser: (payload) =>
    request("/api/users", { method: "POST", body: JSON.stringify(payload) }),
  updateUser: (id, payload) =>
    request(`/api/users/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteUser: (id) => request(`/api/users/${id}`, { method: "DELETE" }),

  // Kitchen Menu & Procurement Orders
  getDishes: (search = "", category = "") => {
    const q = new URLSearchParams();
    if (search) q.set("search", search);
    if (category) q.set("category", category);
    return request(`/api/kitchen/dishes?${q.toString()}`);
  },
  createDish: (payload) =>
    request("/api/kitchen/dishes", { method: "POST", body: JSON.stringify(payload) }),
  deleteDish: (id) => request(`/api/kitchen/dishes/${id}`, { method: "DELETE" }),

  getOrders: (status = "") => {
    const q = new URLSearchParams();
    if (status) q.set("status", status);
    return request(`/api/kitchen/orders?${q.toString()}`);
  },
  getOrderDetail: (orderId) => request(`/api/kitchen/orders/${orderId}`),
  createOrder: (payload) =>
    request("/api/kitchen/orders", { method: "POST", body: JSON.stringify(payload) }),
  checkOrderItem: (orderId, itemId, overrideClass = null, note = "") =>
    request(`/api/kitchen/orders/${orderId}/check-item`, {
      method: "POST",
      body: JSON.stringify({ item_id: itemId, override_class: overrideClass, note }),
    }),

  // Station
  getState: () => request("/api/station/state"),
  tare: () => request("/api/station/tare", { method: "POST" }),
  inspectNow: (payload = {}) =>
    request("/api/station/inspect", { method: "POST", body: JSON.stringify(payload) }),
  commitReceipt: (payload = {}) =>
    request("/api/station/commit", { method: "POST", body: JSON.stringify(payload) }),
  overrideFood: (className) =>
    request("/api/station/override-food", {
      method: "POST",
      body: JSON.stringify({ class_name: className }),
    }),
  setAutoCommit: (enabled) =>
    request("/api/station/auto-commit", {
      method: "POST",
      body: JSON.stringify({ enabled }),
    }),
  simulateWeight: (weightGram) =>
    request("/api/station/simulate/weight", {
      method: "POST",
      body: JSON.stringify({ weight_gram: weightGram }),
    }),
  simulateAI: (label, quality) =>
    request("/api/station/simulate/ai", {
      method: "POST",
      body: JSON.stringify({ label, quality }),
    }),

  // Hardware & Calibration
  getHardwareStatus: () => request("/api/hardware/status"),
  calibrateTare: () => request("/api/hardware/calibrate/tare", { method: "POST" }),
  calibrateMeasure: (knownWeightG, invertIfNegative = true) =>
    request("/api/hardware/calibrate/measure", {
      method: "POST",
      body: JSON.stringify({
        known_weight_g: knownWeightG,
        invert_if_negative: invertIfNegative,
      }),
    }),
  calibrateInvert: () => request("/api/hardware/calibrate/invert", { method: "POST" }),
  testLcd: (line1, line2) =>
    request("/api/hardware/lcd/test", {
      method: "POST",
      body: JSON.stringify({ line1, line2 }),
    }),

  // Foods & Reports
  getFoods: (search = "", foodGroup = "") => {
    const q = new URLSearchParams();
    if (search) q.set("search", search);
    if (foodGroup) q.set("food_group", foodGroup);
    return request(`/api/foods?${q.toString()}`);
  },
  updateFood: (id, fields) =>
    request(`/api/foods/${id}`, { method: "PUT", body: JSON.stringify(fields) }),

  getLogs: (params = {}) => {
    const q = new URLSearchParams();
    if (params.limit) q.set("limit", params.limit);
    if (params.date_from) q.set("date_from", params.date_from);
    if (params.date_to) q.set("date_to", params.date_to);
    if (params.quality_status) q.set("quality_status", params.quality_status);
    return request(`/api/logs?${q.toString()}`);
  },
  deleteLog: (id) => request(`/api/logs/${id}`, { method: "DELETE" }),
  getAnalytics: (days = 14) => request(`/api/analytics?days=${days}`),
};
