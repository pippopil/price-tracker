const API = "http://localhost:8000";

async function trackProduct() {
  const url = document.getElementById("urlInput").value.trim();
  const userId = parseInt(document.getElementById("userId").value);
  if (!url || isNaN(userId)) return alert("Заполните все поля");

  const res = await fetch(`${API}/track/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, user_id: userId }),
  });
  const data = await res.json();
  if (res.ok) {
    alert("✅ Добавлено!");
    loadProducts(userId);
  } else {
    alert("❌ " + data.detail);
  }
}

async function loadProducts(userId) {
  const res = await fetch(`${API}/products/${userId}`);
  const products = await res.json();
  const list = document.getElementById("productList");
  list.innerHTML = "";
  products.forEach((p) => {
    const li = document.createElement("li");
    li.innerHTML = `${p.marketplace} | ${p.url} <button onclick="stopTrack(${p.id})">Остановить</button>`;
    list.appendChild(li);
  });
}

async function stopTrack(id) {
  await fetch(`${API}/stop/${id}`, { method: "POST" });
  const userId = document.getElementById("userId").value;
  loadProducts(userId);
}

// Автозагрузка при открытии
document
  .getElementById("userId")
  .addEventListener("change", (e) => loadProducts(e.target.value));
