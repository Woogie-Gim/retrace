// 공통 유틸

let configPromise = null;

function getConfig() {
  if (!configPromise) {
    configPromise = fetch("/api/config").then((r) => r.json());
  }
  return configPromise;
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (res.status === 401) {
    location.href = "login.html";
    throw new Error("unauthorized");
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const err = new Error((data && data.detail) || `HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return data;
}

function won(n) {
  return `${Number(n).toLocaleString("ko-KR")}원`;
}

function uuid() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "testid") node.dataset.testid = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) node.append(c);
  return node;
}

// 상단 네비게이션
async function renderNav() {
  const nav = document.querySelector("nav");
  if (!nav) return null;
  const me = await api("/api/me");
  nav.replaceChildren(
    el("a", { href: "products.html", testid: "nav-products", text: "상품" }),
    el("a", { href: "cart.html", testid: "nav-cart", text: "장바구니" }),
    el("a", { href: "orders.html", testid: "nav-orders", text: "주문 내역" }),
    el("span", { class: "spacer" }),
    el("span", { testid: "nav-user", text: `${me.grade_name} 회원` }),
    el("a", { href: "login.html", testid: "nav-logout", text: "로그아웃" }),
  );
  return me;
}

// 장바구니 수량 변경
// on : 병렬 요청 (호출 측에서 낙관적 반영)
// off : 직렬 큐 → 서버 응답 순서대로 처리
let cartQueue = Promise.resolve();

async function updateCart(productId, delta) {
  const { bug_mode } = await getConfig();
  const send = () =>
    api("/api/cart", {
      method: "POST",
      body: JSON.stringify({ product_id: productId, delta }),
    });
  if (bug_mode) return send();
  const job = cartQueue.then(send);
  cartQueue = job.catch(() => {});
  return job;
}
