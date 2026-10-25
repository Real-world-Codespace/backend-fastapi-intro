const $ = (id) => document.getElementById(id);
const state = { user: null, users: [], tasks: [], filter: "all", register: false, editingId: null };
const statusNames = { todo: "Cần làm", doing: "Đang làm", done: "Hoàn thành" };
const priorityNames = { low: "Thấp", medium: "Trung bình", high: "Cao" };

async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map((x) => x.msg).join("; ") : data.detail;
    throw new Error(detail || `Yêu cầu thất bại (${response.status})`);
  }
  return data;
}

function showAuth() {
  state.user = null;
  $("auth-view").classList.remove("hidden");
  $("app-view").classList.add("hidden");
  $("logout").classList.add("hidden");
  $("whoami").textContent = "";
}

async function showApp(user) {
  state.user = user;
  $("auth-view").classList.add("hidden");
  $("app-view").classList.remove("hidden");
  $("logout").classList.remove("hidden");
  $("whoami").textContent = user.name;
  try {
    const [users, tasks, history, health] = await Promise.all([
      api("/users"), api("/tasks"), api("/chat/history"), api("/health"),
    ]);
    state.users = users;
    state.tasks = tasks;
    renderAssignees();
    renderTasks();
    renderHistory(history);
    $("ai-banner").textContent = health.ai_mode === "demo"
      ? "Chế độ demo: chatbot trả lời theo quy tắc mẫu, chưa gọi OpenAI."
      : "Trợ lý dùng OpenAI và chỉ nhận những công việc bạn có quyền xem.";
  } catch (error) {
    $("task-error").textContent = error.message;
  }
}

function renderAssignees() {
  const select = $("task-assignee");
  select.replaceChildren();
  for (const user of state.users) {
    const option = document.createElement("option");
    option.value = user.id;
    option.textContent = user.id === state.user.id ? `${user.name} (tôi)` : user.name;
    select.append(option);
  }
  select.value = String(state.user.id);
}

function renderTasks() {
  const list = $("task-list");
  list.replaceChildren();
  const filtered = state.filter === "all" ? state.tasks : state.tasks.filter((task) => task.status === state.filter);
  const open = state.tasks.filter((task) => task.status !== "done").length;
  const high = state.tasks.filter((task) => task.status !== "done" && task.priority === "high").length;
  $("stats").innerHTML = `<div class="stat"><strong>${state.tasks.length}</strong><span>Tổng việc</span></div><div class="stat"><strong>${open}</strong><span>Đang mở</span></div><div class="stat"><strong>${high}</strong><span>Ưu tiên cao</span></div>`;
  if (!filtered.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "Chưa có công việc trong nhóm này.";
    list.append(empty);
    return;
  }
  for (const task of filtered) list.append(makeTaskCard(task));
}

function makeTaskCard(task) {
  const card = document.createElement("article");
  card.className = "task-card";
  const top = document.createElement("div");
  top.className = "task-top";
  const title = document.createElement("h3");
  title.textContent = task.title;
  const priority = document.createElement("span");
  priority.className = `badge ${task.priority}`;
  priority.textContent = `Ưu tiên ${priorityNames[task.priority]}`;
  top.append(title, priority);
  card.append(top);
  if (task.description) {
    const desc = document.createElement("p");
    desc.textContent = task.description;
    card.append(desc);
  }
  const assignee = state.users.find((user) => user.id === task.assignee_id);
  const meta = document.createElement("div");
  meta.className = "task-meta";
  for (const value of [`#${task.id}`, `Người làm: ${assignee?.name || "Không rõ"}`, `Hạn: ${task.due_date || "Chưa đặt"}`]) {
    const span = document.createElement("span");
    span.textContent = value;
    meta.append(span);
  }
  card.append(meta);
  const actions = document.createElement("div");
  actions.className = "task-actions";
  const status = document.createElement("select");
  status.setAttribute("aria-label", `Trạng thái của ${task.title}`);
  for (const [key, label] of Object.entries(statusNames)) {
    const option = document.createElement("option");
    option.value = key;
    option.textContent = label;
    status.append(option);
  }
  status.value = task.status;
  status.addEventListener("change", async () => {
    try {
      const updated = await api(`/tasks/${task.id}`, { method: "PATCH", body: JSON.stringify({ status: status.value }) });
      state.tasks = state.tasks.map((item) => item.id === updated.id ? updated : item);
      renderTasks();
    } catch (error) {
      status.value = task.status;
      $("task-error").textContent = error.message;
    }
  });
  actions.append(status);
  if (task.created_by_id === state.user.id) {
    const edit = document.createElement("button");
    edit.className = "secondary small";
    edit.textContent = "Sửa";
    edit.addEventListener("click", () => openEdit(task));
    actions.append(edit);
    const remove = document.createElement("button");
    remove.className = "delete-button";
    remove.textContent = "Xóa";
    remove.addEventListener("click", async () => {
      if (!confirm(`Xóa công việc “${task.title}”?`)) return;
      try {
        await api(`/tasks/${task.id}`, { method: "DELETE" });
        state.tasks = state.tasks.filter((item) => item.id !== task.id);
        renderTasks();
      } catch (error) { $("task-error").textContent = error.message; }
    });
    actions.append(remove);
  }
  card.append(actions);
  return card;
}

function openEdit(task) {
  state.editingId = task.id;
  $("edit-title").value = task.title;
  $("edit-description").value = task.description;
  $("edit-priority").value = task.priority;
  $("edit-due").value = task.due_date || "";
  const select = $("edit-assignee");
  select.replaceChildren();
  for (const user of state.users) {
    const option = document.createElement("option");
    option.value = user.id;
    option.textContent = user.name;
    select.append(option);
  }
  select.value = String(task.assignee_id);
  $("edit-error").textContent = "";
  $("edit-dialog").showModal();
}

$("close-edit").addEventListener("click", () => $("edit-dialog").close());
$("edit-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("edit-error").textContent = "";
  try {
    const updated = await api(`/tasks/${state.editingId}`, { method: "PATCH", body: JSON.stringify({
      title: $("edit-title").value.trim(),
      description: $("edit-description").value.trim(),
      priority: $("edit-priority").value,
      assignee_id: Number($("edit-assignee").value),
      due_date: $("edit-due").value || null,
    }) });
    state.tasks = state.tasks.map((item) => item.id === updated.id ? updated : item);
    $("edit-dialog").close();
    renderTasks();
  } catch (error) { $("edit-error").textContent = error.message; }
});

function addBubble(role, content) {
  const bubble = document.createElement("div");
  bubble.className = `bubble ${role === "user" ? "user" : "assistant"}`;
  bubble.textContent = content;
  $("chat-messages").append(bubble);
  $("chat-messages").scrollTop = $("chat-messages").scrollHeight;
}

function renderHistory(history) {
  $("chat-messages").replaceChildren();
  if (!history.length) addBubble("assistant", "Xin chào! Bạn có thể hỏi tôi về những công việc được giao, tiến độ hoặc việc cần ưu tiên.");
  for (const item of history) addBubble(item.role, item.content);
}

$("login-tab").addEventListener("click", () => setAuthMode(false));
$("register-tab").addEventListener("click", () => setAuthMode(true));
function setAuthMode(register) {
  state.register = register;
  $("login-tab").classList.toggle("active", !register);
  $("register-tab").classList.toggle("active", register);
  $("name-field").classList.toggle("hidden", !register);
  $("name").required = register;
  $("password").minLength = register ? 10 : 1;
  $("password").autocomplete = register ? "new-password" : "current-password";
  $("auth-submit").firstChild.textContent = register ? "Tạo tài khoản " : "Đăng nhập ";
  $("auth-error").textContent = "";
}
$("auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("auth-error").textContent = "";
  const email = $("email").value.trim();
  const password = $("password").value;
  try {
    if (state.register) await api("/auth/register", { method: "POST", body: JSON.stringify({ name: $("name").value.trim(), email, password }) });
    const user = await api("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
    $("password").value = "";
    await showApp(user);
  } catch (error) { $("auth-error").textContent = error.message; }
});
$("logout").addEventListener("click", async () => {
  await api("/auth/logout", { method: "POST" }).catch(() => {});
  showAuth();
});
$("task-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("task-error").textContent = "";
  try {
    const task = await api("/tasks", { method: "POST", body: JSON.stringify({
      title: $("task-title").value.trim(), description: $("task-description").value.trim(),
      assignee_id: Number($("task-assignee").value), priority: $("task-priority").value,
      due_date: $("task-due").value || null,
    }) });
    state.tasks.unshift(task);
    $("task-form").reset();
    $("task-assignee").value = String(state.user.id);
    renderTasks();
  } catch (error) { $("task-error").textContent = error.message; }
});
$("refresh-tasks").addEventListener("click", async () => {
  try { state.tasks = await api("/tasks"); renderTasks(); }
  catch (error) { $("task-error").textContent = error.message; }
});
document.querySelectorAll(".filter").forEach((button) => button.addEventListener("click", () => {
  state.filter = button.dataset.filter;
  document.querySelectorAll(".filter").forEach((item) => item.classList.toggle("active", item === button));
  renderTasks();
}));
$("chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("chat-error").textContent = "";
  const message = $("chat-input").value.trim();
  if (!message) return;
  const button = $("chat-form").querySelector("button");
  button.disabled = true;
  try {
    const { reply } = await api("/chat", { method: "POST", body: JSON.stringify({ message }) });
    addBubble("user", message);
    addBubble("assistant", reply);
    $("chat-input").value = "";
  } catch (error) { $("chat-error").textContent = error.message; }
  finally { button.disabled = false; }
});

api("/auth/me").then(showApp).catch(showAuth);
