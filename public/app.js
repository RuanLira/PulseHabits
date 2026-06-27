const list = document.querySelector("#habitList");
const form = document.querySelector("#habitForm");
const filter = document.querySelector("#filter");
const message = document.querySelector("#formMessage");
const totalHabits = document.querySelector("#totalHabits");
const doneToday = document.querySelector("#doneToday");
const weekAverage = document.querySelector("#weekAverage");
const todayScore = document.querySelector("#todayScore");

let habits = [];

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Algo deu errado.");
  }
  return data;
}

async function loadHabits() {
  const data = await request("/api/habits");
  habits = data.habits;
  render();
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
        <h3>${escapeHtml(habit.name)}</h3>
        <div class="habit-meta">
          <span class="pill">${escapeHtml(habit.category)}</span>
          <span>${habit.week_count}/${habit.weekly_goal} na semana</span>
          <span>${habit.progress}% da meta</span>
        </div>
        <div class="progress" aria-label="Progresso semanal">
          <span style="width: ${habit.progress}%"></span>
        </div>
      </div>
      <div class="actions">
        <button class="done ${habit.completed_today ? "active" : ""}" data-action="toggle" data-id="${habit.id}" title="Marcar hoje">
          ${habit.completed_today ? "✓" : "+"}
        </button>
        <button class="delete" data-action="delete" data-id="${habit.id}" title="Remover">x</button>
      </div>
    </article>
  `).join("");
}

function renderStats() {
  const total = habits.length;
  const completed = habits.filter((habit) => habit.completed_today).length;
  const average = total === 0
    ? 0
    : Math.round(habits.reduce((sum, habit) => sum + habit.progress, 0) / total);
  const today = total === 0 ? 0 : Math.round((completed / total) * 100);

  totalHabits.textContent = total;
  doneToday.textContent = completed;
  weekAverage.textContent = `${average}%`;
  todayScore.textContent = `${today}%`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

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
    await loadHabits();
  } catch (error) {
    message.textContent = error.message;
  }
});

filter.addEventListener("change", render);

list.addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button) return;

  const id = button.dataset.id;
  const action = button.dataset.action;

  if (action === "toggle") {
    await request(`/api/habits/${id}/toggle`, { method: "POST" });
  }

  if (action === "delete") {
    await request(`/api/habits/${id}`, { method: "DELETE" });
  }

  await loadHabits();
});

loadHabits();
