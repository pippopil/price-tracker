const API = "http://localhost:8000";
async function track() {
  const uid = +document.getElementById("uid").value;
  const url = document.getElementById("url").value.trim();
  if (!uid || !url) return alert("Заполни оба поля");
  const r = await fetch(`${API}/track/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, user_id: uid }),
  });
  const d = await r.json();
  if (r.ok) {
    alert("✅ Добавлено");
    load(uid);
  } else alert("❌ " + d.detail);
}
async function load(uid) {
  const r = await fetch(`${API}/products/${uid}`);
  const items = await r.json();
  const ul = document.getElementById("list");
  ul.innerHTML = "";
  items.forEach((i) => {
    const li = document.createElement("li");
    li.innerHTML = `${i.marketplace} <button onclick="stop(${i.id})">🛑</button>`;
    ul.appendChild(li);
  });
}
async function stop(id) {
  await fetch(`${API}/stop/${id}`, { method: "POST" });
  load(+document.getElementById("uid").value);
}
