const authView = document.querySelector("#authView");
const appView = document.querySelector("#appView");
const authForm = document.querySelector("#authForm");
const authMessage = document.querySelector("#authMessage");
const logoutButton = document.querySelector("#logoutButton");
const currentUser = document.querySelector("#currentUser");

const list = document.querySelector("#habitList");
const form = document.querySelector("#habitForm");
const filter = document.querySelector("#filter");
const activeDate = document.querySelector("#activeDate");
const message = document.querySelector("#formMessage");
const totalHabits = document.querySelector("#totalHabits");
const doneToday = document.querySelector("#doneToday");
const weekAverage = document.querySelector("#weekAverage");
const todayScore = document.querySelector("#todayScore");
const bestStreak = document.querySelector("#bestStreak");
const historyChart = document.querySelector("#historyChart");
const reminderTime = document.querySelector("#reminderTime");
const enableNotifications = document.querySelector("#enableNotifications");

let habits = [];
let user = null;

activeDate.value = new Date().toISOString().slice(0, 10);
reminderTime.value = localStorage.getItem("pulseReminderTime") || "20:00";

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    ...options,
  });

  const contentType = response.headers.get("Content-Type") || "";
  const data = contentType.includes("application/json") ? await response.json() : {};
  if (!response.ok) {
    throw new Error(data.error || "Algo deu errado.");
  }
  return data;
}

async function boot() {
  const data = await request("/api/me");
  user = data.user;
  if (!user) {
    showAuth();
    return;
  }
  showApp();
  await refresh();
}

function showAuth() {
  authView.classList.remove("hidden");
  appView.classList.add("hidden");
}

function showApp() {
  authView.classList.add("hidden");
  appView.classList.remove("hidden");
  currentUser.textContent = user ? `Logado como ${user.username}` : "";
}

async function refresh() {
  const [habitData, historyData] = await Promise.all([
    request("/api/habits"),
    request("/api/history?days=30"),
  ]);
  habits = habitData.habits;
  render();
  renderHistory(historyData.days);
}

function render() {
  const selected = filter.value;
  const visible = selected === "Todos"
    ? habits
    : habits.filter((habit) => habit.category === selected);

  renderStats();

  if (visible.length === 0) {
    list.innerHTML = '<p class="empty">Nenhum habito encontrado para este filtro.</p>';
    return;
  }

  list.innerHTML = visible.map((habit) => `
    <article class="habit-card">
      <div>
        <div class="habit-title-row">
          <h3>${escapeHtml(habit.name)}</h3>
          <span class="streak">${habit.streak} dias</span>
        </div>
        <div class="habit-meta">
          <span class="pill">${escapeHtml(habit.category)}</span>
          <span>${habit.week_count}/${habit.weekly_goal} na semana</span>
          <span>${habit.progress}% da meta</span>
        </div>
        <div class="progress" aria-label="Progresso semanal">
          <span style="width: ${habit.progress}%"></span>
        </div>
        <div class="mini-history" aria-label="Historico recente">
          ${habit.history.map((day) => `
            <button
              type="button"
              class="day-dot ${day.done ? "done-day" : ""} ${day.date === activeDate.value ? "selected-day" : ""}"
              data-action="toggle-date"
              data-id="${habit.id}"
              data-date="${day.date}"
              title="${formatDate(day.date)}"
              aria-label="${formatDate(day.date)}">
            </button>
          `).join("")}
        </div>
      </div>
      <div class="actions">
        <button class="done ${isDoneOnSelectedDate(habit) ? "active" : ""}" data-action="toggle" data-id="${habit.id}" title="Marcar na data selecionada">
          ${isDoneOnSelectedDate(habit) ? "OK" : "+"}
        </button>
        <button class="edit" data-action="edit" data-id="${habit.id}" title="Editar">Ed</button>
        <button class="delete" data-action="delete" data-id="${habit.id}" title="Remover">x</button>
      </div>
    </article>
  `).join("");
}

function isDoneOnSelectedDate(habit) {
  return habit.history.some((day) => day.date === activeDate.value && day.done);
}

function renderStats() {
  const total = habits.length;
  const today = new Date().toISOString().slice(0, 10);
  const completed = habits.filter((habit) =>
    habit.history.some((day) => day.date === today && day.done)
  ).length;
  const average = total === 0
    ? 0
    : Math.round(habits.reduce((sum, habit) => sum + habit.progress, 0) / total);
  const todayPercent = total === 0 ? 0 : Math.round((completed / total) * 100);
  const streak = habits.reduce((max, habit) => Math.max(max, habit.streak), 0);

  totalHabits.textContent = total;
  doneToday.textContent = completed;
  weekAverage.textContent = `${average}%`;
  todayScore.textContent = `${todayPercent}%`;
  bestStreak.textContent = streak;
}

function renderHistory(days) {
  const maxTotal = Math.max(1, ...days.map((day) => day.total));
  historyChart.innerHTML = days.map((day) => `
    <div class="bar-wrap" title="${formatDate(day.date)}: ${day.percent}%">
      <span class="bar" style="height: ${Math.max(8, (day.total / maxTotal) * 100)}%"></span>
      <small>${new Date(`${day.date}T00:00:00`).getDate()}</small>
    </div>
  `).join("");
}

function formatDate(value) {
  return new Date(`${value}T00:00:00`).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  authMessage.textContent = "";
  const submitter = event.submitter;
  const mode = submitter?.dataset.mode || "login";

  try {
    const data = await request(`/api/${mode}`, {
      method: "POST",
      body: JSON.stringify({
        username: authForm.username.value,
        password: authForm.password.value,
      }),
    });
    user = data.user;
    showApp();
    await refresh();
  } catch (error) {
    authMessage.textContent = error.message;
  }
});

logoutButton.addEventListener("click", async () => {
  await request("/api/logout", { method: "POST" });
  user = null;
  habits = [];
  showAuth();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  message.textContent = "";

  const payload = {
    name: form.name.value,
    category: form.category.value,
    weekly_goal: Number(form.weeklyGoal.value),
  };

  try {
    await request("/api/habits", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    form.reset();
    form.weeklyGoal.value = 5;
    await refresh();
  } catch (error) {
    message.textContent = error.message;
  }
});

filter.addEventListener("change", render);
activeDate.addEventListener("change", render);

list.addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button) return;

  const id = button.dataset.id;
  const action = button.dataset.action;

  if (action === "toggle" || action === "toggle-date") {
    await request(`/api/habits/${id}/toggle`, {
      method: "POST",
      body: JSON.stringify({ date: button.dataset.date || activeDate.value }),
    });
  }

  if (action === "delete") {
    await request(`/api/habits/${id}`, { method: "DELETE" });
  }

  if (action === "edit") {
    await editHabit(id);
  }

  await refresh();
});

async function editHabit(id) {
  const habit = habits.find((item) => String(item.id) === String(id));
  if (!habit) return;

  const name = window.prompt("Nome do habito", habit.name);
  if (name === null) return;
  const category = window.prompt("Categoria", habit.category);
  if (category === null) return;
  const weeklyGoal = window.prompt("Meta semanal de 1 a 7", habit.weekly_goal);
  if (weeklyGoal === null) return;

  await request(`/api/habits/${id}`, {
    method: "PATCH",
    body: JSON.stringify({
      name,
      category,
      weekly_goal: Number(weeklyGoal),
    }),
  });
}

enableNotifications.addEventListener("click", async () => {
  localStorage.setItem("pulseReminderTime", reminderTime.value);
  if (!("Notification" in window)) {
    enableNotifications.textContent = "Sem suporte";
    return;
  }
  const permission = await Notification.requestPermission();
  enableNotifications.textContent = permission === "granted" ? "Lembrete ativo" : "Permissao negada";
});

setInterval(() => {
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  const now = new Date();
  const current = now.toTimeString().slice(0, 5);
  const configured = localStorage.getItem("pulseReminderTime") || reminderTime.value;
  const key = `pulseReminder:${now.toISOString().slice(0, 10)}:${configured}`;
  if (current === configured && localStorage.getItem(key) !== "sent") {
    localStorage.setItem(key, "sent");
    new Notification("PulseHabits", {
      body: "Hora de registrar seus habitos de hoje.",
    });
  }
}, 30_000);

boot().catch((error) => {
  authMessage.textContent = error.message;
  showAuth();
});
