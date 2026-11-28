"use strict";

const state = { token: null, enums: {} };
try {
  state.token = sessionStorage.getItem("lifeos_token");
} catch (err) {
  state.token = null;
}

const app = document.getElementById("app");
const nav = document.getElementById("nav");
const statusLine = document.getElementById("status");

class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

// Builds elements with textContent only, so nothing the server sends is ever parsed as HTML.
function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === false || value == null) continue;
    if (key === "class") el.className = value;
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

function say(text, isError) {
  statusLine.textContent = text || "";
  statusLine.className = isError ? "error" : "";
}

function label(value) {
  return String(value).replace(/_/g, " ");
}

function pct(value) {
  return value == null ? "not enough data yet" : value + "%";
}

function isoToday() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
}

function detailText(data, status) {
  if (data && typeof data.detail === "string") return data.detail;
  if (data && Array.isArray(data.detail)) {
    return data.detail
      .map((d) => (d.loc ? d.loc.slice(1).join(".") + ": " : "") + d.msg)
      .join("; ");
  }
  return "Something went wrong (" + status + ").";
}

async function api(method, path, body) {
  const headers = {};
  if (body !== undefined) headers["content-type"] = "application/json";
  if (state.token) headers.authorization = "Bearer " + state.token;
  const slow = setTimeout(() => {
    say("Working... the free server may be waking up, which can take a minute.");
  }, 4000);
  try {
    const res = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    let data = null;
    try {
      data = await res.json();
    } catch (err) {
      data = null;
    }
    if (res.status === 401 && state.token && !path.startsWith("/auth/login")) {
      signOut("Your session ended. Please sign in again.");
      throw new ApiError(401, "Signed out.");
    }
    if (!res.ok) throw new ApiError(res.status, detailText(data, res.status));
    return data;
  } finally {
    clearTimeout(slow);
    if (statusLine.textContent.startsWith("Working")) say("");
  }
}

async function run(task) {
  say("");
  try {
    await task();
  } catch (err) {
    if (err.status !== 401) say(err.message || String(err), true);
  }
}

function setToken(token) {
  state.token = token;
  try {
    if (token) sessionStorage.setItem("lifeos_token", token);
    else sessionStorage.removeItem("lifeos_token");
  } catch (err) {
    // storage can be unavailable; the session then lasts until the page closes
  }
}

function signOut(message) {
  setToken(null);
  show("auth");
  say(message || "");
}

async function loadEnums() {
  try {
    const res = await fetch("/openapi.json");
    const schemas = (await res.json()).components.schemas;
    for (const name of ["TaskStatus", "BlockReason", "RoadblockType"]) {
      state.enums[name] = (schemas[name] && schemas[name].enum) || [];
    }
  } catch (err) {
    state.enums = {};
  }
}

function choices(name) {
  return state.enums[name] || [];
}

function selectOf(values, blank) {
  return h(
    "select",
    {},
    blank != null ? h("option", { value: "" }, blank) : null,
    values.map((v) => h("option", { value: v }, label(v))),
  );
}

function field(text, input) {
  return h("label", {}, text, input);
}

const TITLES = { plan: "Today", checkin: "Check-in", review: "Weekly review", methods: "Methods" };

function show(view) {
  app.replaceChildren();
  say("");
  if (view === "auth" || !state.token) {
    nav.hidden = true;
    renderAuth();
    return;
  }
  nav.hidden = false;
  nav.replaceChildren(
    ...Object.keys(TITLES).map((key) =>
      h("button", { class: key === view ? "tab active" : "tab", onclick: () => show(key) }, TITLES[key]),
    ),
    h("button", { class: "tab quiet", onclick: () => show("account") }, "Account"),
  );
  const views = { plan: viewPlan, checkin: viewCheckin, review: viewReview, methods: viewMethods };
  run(() => (views[view] || viewAccount)(app));
}

function renderAuth() {
  const loginEmail = h("input", { type: "email", required: true, autocomplete: "email" });
  const loginPassword = h("input", { type: "password", required: true, autocomplete: "current-password" });
  const newEmail = h("input", { type: "email", required: true, autocomplete: "email" });
  const newPassword = h("input", { type: "password", required: true, autocomplete: "new-password" });
  const consent = h("input", { type: "checkbox", required: true });

  const login = async (email, password) => {
    const token = await api("POST", "/auth/login", { email, password });
    setToken(token.access_token);
    show("plan");
  };

  app.append(
    h("p", {}, "Tell it your goals and what gets in the way. It plans a realistic day, " +
      "checks how the day went, and suggests methods that fit your pattern. " +
      "Use a throwaway email: this is an open demo."),
    h("form", { class: "card", onsubmit: (e) => {
      e.preventDefault();
      run(() => login(loginEmail.value, loginPassword.value));
    } },
      h("h2", {}, "Sign in"),
      field("Email", loginEmail),
      field("Password", loginPassword),
      h("button", { type: "submit" }, "Sign in"),
    ),
    h("form", { class: "card", onsubmit: (e) => {
      e.preventDefault();
      run(async () => {
        await api("POST", "/auth/register", {
          email: newEmail.value, password: newPassword.value, consent: consent.checked,
        });
        await login(newEmail.value, newPassword.value);
      });
    } },
      h("h2", {}, "Create an account"),
      field("Email", newEmail),
      field("Password", newPassword),
      h("label", { class: "check" }, consent,
        "I agree that this demo stores my plans and check-ins so it can work. " +
        "I can download my data from the Account page at any time."),
      h("button", { type: "submit" }, "Create account"),
    ),
  );
}

async function getOrNull(path) {
  try {
    return await api("GET", path);
  } catch (err) {
    if (err.status === 404) return null;
    throw err;
  }
}

function noteList(title, items) {
  if (!items || !items.length) return null;
  return h("div", {}, h("h3", {}, title),
    h("ul", {}, items.map((i) => h("li", {}, i.message || i.reason || JSON.stringify(i)))));
}

function planCard(plan) {
  return h("section", { class: "card" },
    h("p", {}, h("strong", {}, label(plan.mode)), " - ", plan.reason),
    h("p", { class: "muted" }, plan.focus_minutes + " minutes of focus work planned."),
    h("div", { class: "timeline" }, plan.blocks.map((b) =>
      h("div", { class: "slot " + b.kind },
        h("span", { class: "time" }, b.start + " - " + b.end),
        h("div", { class: "what" }, h("span", { class: "dot" }), h("span", { class: "name" }, b.title))))),
    noteList("Could not fit", plan.unplaced),
    noteList("Dropped", plan.dropped),
    noteList("Shortened", plan.trimmed),
  );
}

function planForm(date) {
  const rows = h("div", {});
  const low = h("input", { type: "checkbox" });
  const addRow = () => {
    const title = h("input", { type: "text", placeholder: "Task, e.g. Revise DSA", required: true, maxlength: "120" });
    const minutes = h("input", { type: "number", min: "1", max: "600", value: "45", required: true });
    const effort = selectOf(["focus", "light"]);
    const row = h("div", { class: "row" }, title, minutes, effort,
      h("button", { type: "button", class: "quiet", onclick: () => row.remove() }, "Remove"));
    row.read = () => ({ title: title.value.trim(), minutes: Number(minutes.value), effort: effort.value });
    rows.append(row);
  };
  addRow();
  return h("form", { class: "card", onsubmit: (e) => {
    e.preventDefault();
    run(async () => {
      const tasks = [...rows.children].map((row, i) => ({ key: "t" + (i + 1), ...row.read() }));
      await api("POST", "/plans/" + date, { tasks, low_energy: low.checked });
      show("plan");
    });
  } },
    h("p", {}, "What do you want to get done today? Minutes are your honest estimate."),
    rows,
    h("button", { type: "button", class: "secondary", onclick: addRow }, "Add another task"),
    h("label", { class: "check" }, low, "I am low on energy today"),
    h("button", { type: "submit" }, "Make my plan"),
  );
}

async function viewPlan(box) {
  const date = isoToday();
  const plan = await getOrNull("/plans/" + date);
  box.append(h("h2", {}, "Today, " + date));
  if (!plan) {
    box.append(planForm(date));
    return;
  }
  box.append(planCard(plan), h("button", { class: "secondary", onclick: () => run(async () => {
    await api("DELETE", "/plans/" + date);
    show("plan");
  }) }, "Plan this day again"));
}

function reportCard(saved) {
  const r = saved.report;
  return h("section", { class: "card" },
    h("h3", {}, "Saved check-in"),
    h("p", {}, "Planned " + r.planned_minutes + " min, counted " + r.counted_minutes +
      " min. Adherence: " + pct(r.adherence_percent) + "."),
    r.overrun_minutes ? h("p", {}, "Over the estimate by " + r.overrun_minutes + " min.") : null,
    r.unreported.length ? h("p", { class: "muted" }, "Not reported: " + r.unreported.join(", ")) : null,
  );
}

async function viewCheckin(box) {
  const date = isoToday();
  box.append(h("h2", {}, "Check-in for " + date));
  const plan = await getOrNull("/plans/" + date);
  if (!plan) {
    box.append(h("p", { class: "muted" }, "Make today's plan first, then come back to say how it went."));
    return;
  }
  const saved = await getOrNull("/checkins/" + date);
  if (saved) box.append(reportCard(saved));
  const tasks = new Map();
  for (const b of plan.blocks) if (b.task_key) tasks.set(b.task_key, b.title);
  const rows = [...tasks].map(([key, title]) => {
    const status = selectOf(choices("TaskStatus"));
    const minutes = h("input", { type: "number", min: "0", max: "1000", value: "0", required: true });
    const reason = selectOf(choices("BlockReason"), "No reason");
    const el = h("div", { class: "row wide" }, h("span", {}, title), status, minutes, reason);
    el.read = () => ({ task: key, status: status.value, actual_minutes: Number(minutes.value),
      reason: reason.value || null });
    return el;
  });
  const energy = selectOf(["1", "2", "3", "4", "5"], "Skip");
  const note = h("input", { type: "text", maxlength: "300" });
  box.append(h("form", { class: "card", onsubmit: (e) => {
    e.preventDefault();
    run(async () => {
      await api("PUT", "/checkins/" + date, {
        outcomes: rows.map((r) => r.read()),
        energy: energy.value ? Number(energy.value) : null,
        note: note.value,
      });
      show("checkin");
    });
  } },
    h("p", { class: "muted" }, "For each task: what happened, minutes actually spent, and why if it slipped."),
    rows,
    field("Energy today (1 low, 5 high)", energy),
    field("Note (optional)", note),
    h("button", { type: "submit" }, saved ? "Update check-in" : "Save check-in"),
  ));
}

async function viewReview(box) {
  const w = await api("GET", "/reviews/weekly");
  box.append(h("h2", {}, "Week of " + w.start + " to " + w.end));
  if (!w.days_with_checkins) {
    box.append(h("p", { class: "muted" }, "No check-ins in this week yet. Plan a day and check in first."));
    return;
  }
  const stat = (name, value) => h("div", { class: "stat" }, h("b", {}, value), name);
  box.append(
    h("div", { class: "grid" },
      stat("days checked in", w.days_with_checkins),
      stat("planned minutes", w.planned_minutes),
      stat("counted minutes", w.counted_minutes),
      stat("adherence", pct(w.adherence_percent)),
      stat("actual vs estimate", pct(w.estimate_ratio_percent)),
      stat("not reported", pct(w.unreported_percent)),
    ),
    w.roadblocks.length ? h("section", { class: "card" }, h("h3", {}, "What got in the way"),
      h("ul", {}, w.roadblocks.map((r) =>
        h("li", {}, label(r.reason) + ": " + r.occurrences + " times over " + r.days_affected +
          " days, " + r.minutes_lost + " min lost (" + r.share_percent + "%)")))) : null,
    w.suggestions.length ? h("section", { class: "card" }, h("h3", {}, "What the rules suggest"),
      h("ul", {}, w.suggestions.map((s) => h("li", {}, s.message)))) : null,
  );
}

function methodCard(m, matchedRoadblock) {
  const start = h("button", { class: "secondary", onclick: (e) => run(async () => {
    await api("POST", "/methods/experiments", { method_slug: m.slug, roadblock: matchedRoadblock });
    e.target.disabled = true;
    e.target.textContent = "Started. Check in for a few days, then rate it.";
  }) }, "Try this for a week");
  return h("section", { class: "card" },
    h("h3", {}, m.title, " ", h("span", { class: "badge" }, "evidence: " + label(m.evidence_level))),
    h("p", {}, m.summary),
    m.steps ? h("ol", {}, m.steps.map((s) => h("li", {}, s))) : null,
    m.reasons && m.reasons.length ? h("p", { class: "muted" }, "Why it fits: " + m.reasons.join(" ")) : null,
    m.contraindications && m.contraindications.length
      ? h("p", { class: "muted" }, "Skip it if: " + m.contraindications.join("; ")) : null,
    m.evidence_note ? h("p", { class: "muted" }, m.evidence_note) : null,
    m.sources_reviewed === false ? h("p", { class: "muted" }, "Sources not yet independently verified.") : null,
    matchedRoadblock ? start : null,
  );
}

async function viewMethods(box) {
  const out = h("div", {});
  const boxes = choices("RoadblockType").map((name) => {
    const input = h("input", { type: "checkbox", value: name });
    return h("label", { class: "check" }, input, label(name));
  });
  const situation = h("input", { type: "text", maxlength: "300", placeholder: "Optional: what is going on?" });
  box.append(h("h2", {}, "Methods that fit"),
    h("form", { class: "card", onsubmit: (e) => {
      e.preventDefault();
      run(async () => {
        const picked = boxes.map((b) => b.firstChild).filter((i) => i.checked).map((i) => i.value);
        const body = { roadblocks: picked };
        if (situation.value.trim()) body.situation = situation.value.trim();
        const res = await api("POST", "/methods/suggest", body);
        const parts = [
          res.safety ? h("p", { class: "callout" }, res.safety.message || JSON.stringify(res.safety)) : null,
          res.care_note ? h("p", { class: "callout" }, res.care_note) : null,
          res.notes.map((n) => h("p", { class: "muted" }, n)),
          res.suggestions.map((m) => methodCard(m, m.matched_roadblocks[0])),
          res.already_trying.length ? h("p", { class: "muted" }, "Already trying: " + res.already_trying.join(", ")) : null,
        ];
        out.replaceChildren(...parts.flat().filter(Boolean));
      });
    } },
      h("p", {}, "What is getting in the way?"), boxes, field("Situation", situation),
      h("button", { type: "submit" }, "Suggest methods")),
    out);
}

async function viewAccount(box) {
  const me = await api("GET", "/auth/me");
  box.append(h("h2", {}, "Account"), h("p", {}, "Signed in as " + me.email + "."),
    h("button", { class: "secondary", onclick: () => run(async () => {
      const data = await api("GET", "/auth/me/export");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const link = h("a", { href: URL.createObjectURL(blob), download: "my-lifeos-data.json" });
      document.body.append(link);
      link.click();
      link.remove();
    }) }, "Download my data"),
    " ", h("button", { class: "quiet", onclick: () => signOut("") }, "Sign out"));
}

loadEnums().then(() => show(state.token ? "plan" : "auth"));
