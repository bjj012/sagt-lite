const $ = (selector) => document.querySelector(selector);

const state = {
  customers: [],
  currentCustomerId: null,
  currentTaskId: null,
};

const taskLabels = {
  profile: "生成客户画像",
  tags: "生成客户标签",
  chat_advice: "生成聊天建议",
  service_advice: "生成客服建议",
  schedule_advice: "生成日程建议",
};

async function api(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

async function loadCustomers() {
  const data = await api("/api/customers");
  state.customers = data.customers;
  if (!state.currentCustomerId && data.customers.length) {
    state.currentCustomerId = data.customers[0].id;
  }
  renderCustomerSelect();
  await loadCustomerDetail();
}

function renderCustomerSelect() {
  $("#customerSelect").innerHTML = state.customers
    .map((customer) => `<option value="${customer.id}">${customer.name} - ${customer.level}级客户</option>`)
    .join("");
  $("#customerSelect").value = state.currentCustomerId;
}

async function loadCustomerDetail() {
  if (!state.currentCustomerId) return;
  const data = await api(`/api/customers/${state.currentCustomerId}`);
  renderCustomer(data.customer);
  renderMemory(data.customer);
}

function renderCustomer(customer) {
  const profile = customer.profile || {};
  const tags = customer.tags || [];
  $("#customerCard").innerHTML = `
    <h2>${customer.name} <span class="chip">${customer.level}级</span></h2>
    <p>${customer.notes}</p>
    <div class="chips">
      ${tags.length ? tags.map((tag) => `<span class="chip">${tag}</span>`).join("") : "<span class='chip'>暂无确认标签</span>"}
    </div>
    <p><strong>画像摘要：</strong>${profile["关键诉求"] || "尚未确认客户画像"}</p>
  `;
}

function renderMemory(customer) {
  const interactions = customer.interactions || [];
  $("#memoryList").innerHTML = interactions
    .map(
      (item) => `
      <article class="memory-item">
        ${escapeHtml(item.content)}
        <small>${item.channel} / ${item.created_at}</small>
      </article>`
    )
    .join("");
}

async function runTask(taskType) {
  $("#status").textContent = `正在执行：${taskLabels[taskType]}`;
  $("#resultBox").innerHTML = "<p>智能体正在读取客户记忆、调用工具并生成建议...</p>";
  $("#reviewActions").classList.add("hidden");
  const data = await api(`/api/customers/${state.currentCustomerId}/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task_type: taskType }),
  });
  state.currentTaskId = data.task.id;
  renderTask(data.task);
}

function renderTask(task) {
  $("#status").textContent = `需要您的确认：${taskLabels[task.task_type]}`;
  $("#resultBox").innerHTML = `<pre>${escapeHtml(formatResult(task.result))}</pre><p><strong>执行链路：</strong>${escapeHtml(task.reasoning)}</p>`;
  $("#reviewActions").classList.remove("hidden");
}

async function taskAction(action) {
  if (!state.currentTaskId) return;
  const data = await api(`/api/tasks/${state.currentTaskId}/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }),
  });
  $("#status").textContent = data.message;
  renderTask(data.task);
  if (action !== "regenerate") {
    $("#reviewActions").classList.add("hidden");
    await loadCustomerDetail();
  }
}

function formatResult(result) {
  if (Array.isArray(result)) {
    return result.map((item) => `• ${item}`).join("\n");
  }
  if (typeof result === "object") {
    return Object.entries(result)
      .map(([key, value]) => {
        if (Array.isArray(value)) return `${key}：\n${value.map((item) => `  • ${item}`).join("\n")}`;
        return `${key}：${value}`;
      })
      .join("\n\n");
  }
  return String(result);
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

$("#customerSelect").addEventListener("change", async (event) => {
  state.currentCustomerId = Number(event.target.value);
  state.currentTaskId = null;
  $("#status").textContent = "已切换客户，请选择下方菜单执行智能体任务。";
  $("#resultBox").innerHTML = "<p>当前任务结果会显示在这里。</p>";
  $("#reviewActions").classList.add("hidden");
  await loadCustomerDetail();
});

document.querySelectorAll(".tabbar button").forEach((button) => {
  button.addEventListener("click", () => runTask(button.dataset.task));
});

document.querySelectorAll(".review-actions button").forEach((button) => {
  button.addEventListener("click", () => taskAction(button.dataset.action));
});

$("#refreshBtn").addEventListener("click", loadCustomers);

loadCustomers().catch((error) => {
  $("#customerCard").innerHTML = `<h2>服务未启动</h2><p>${error.message}</p>`;
});
