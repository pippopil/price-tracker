// Настройки
const API_BASE = "http://localhost:8000";

// Добавление товара
async function addProduct() {
  const userId = document.getElementById("userId").value.trim();
  const url = document.getElementById("productUrl").value.trim();

  if (!userId || !url) {
    alert("Заполните оба поля");
    return;
  }

  const button = event.target;
  const originalText = button.textContent;
  button.textContent = "⏳ Добавляем...";
  button.disabled = true;

  try {
    const response = await fetch(`${API_BASE}/track/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, user_id: parseInt(userId) }),
    });

    const data = await response.json();

    if (response.ok) {
      alert(`✅ ${data.message}`);
      document.getElementById("productUrl").value = "";
      loadProducts();
    } else {
      alert(`❌ Ошибка: ${data.detail || "Неизвестная ошибка"}`);
    }
  } catch (error) {
    alert(`❌ Ошибка соединения: ${error.message}`);
    console.error("Fetch error:", error);
  } finally {
    button.textContent = originalText;
    button.disabled = false;
  }
}

// Загрузка списка товаров
async function loadProducts() {
  const userId = document.getElementById("userId").value.trim();
  if (!userId) {
    document.getElementById("productList").innerHTML =
      '<li class="loading">Введите Telegram ID</li>';
    return;
  }

  const list = document.getElementById("productList");
  list.innerHTML = '<li class="loading">Загрузка...</li>';

  try {
    const response = await fetch(`${API_BASE}/products/${userId}`);
    const products = await response.json();

    if (products.length === 0) {
      list.innerHTML = "<li>📭 Пока нет отслеживаемых товаров</li>";
      return;
    }

    list.innerHTML = products
      .map(
        (p) => `
            <li>
                <strong>${p.marketplace.toUpperCase()}</strong><br>
                <span class="price">${p.current_price ? p.current_price + " ₽" : "Цена неизвестна"}</span><br>
                <small>${p.title || p.url.substring(0, 50)}...</small>
                <div class="actions">
                    <button onclick="stopTracking(${p.id})">🛑 Остановить</button>
                </div>
            </li>
        `,
      )
      .join("");
  } catch (error) {
    list.innerHTML = `<li class="error">❌ Ошибка загрузки: ${error.message}</li>`;
    console.error("Load error:", error);
  }
}

// Остановка отслеживания
async function stopTracking(id) {
  if (!confirm("Остановить отслеживание этого товара?")) return;

  try {
    const response = await fetch(`${API_BASE}/stop/${id}`, { method: "POST" });
    if (response.ok) {
      const userId = document.getElementById("userId").value;
      loadProducts();
    } else {
      alert("❌ Не удалось остановить отслеживание");
    }
  } catch (error) {
    alert(`❌ Ошибка: ${error.message}`);
  }
}

// Автозагрузка при изменении ID
document.getElementById("userId").addEventListener("change", loadProducts);

// Загрузка при старте, если ID уже введён
document.addEventListener("DOMContentLoaded", () => {
  const savedId = localStorage.getItem("price_tracker_user_id");
  if (savedId) {
    document.getElementById("userId").value = savedId;
    loadProducts();
  }
});

// Сохранение ID при вводе
document.getElementById("userId").addEventListener("blur", (e) => {
  if (e.target.value) {
    localStorage.setItem("price_tracker_user_id", e.target.value);
  }
});
