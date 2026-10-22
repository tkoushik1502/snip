// User-supplied values (URLs, aliases, referrers) are only ever inserted with
// textContent, never innerHTML, so they can't inject markup or script.

const $ = (id) => document.getElementById(id);

function el(tag, props = {}, children = []) {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (res.status === 204) return null;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    // FastAPI validation errors arrive as a list under `detail`.
    const detail = Array.isArray(body.detail)
      ? body.detail.map((d) => d.msg).join("; ")
      : body.detail;
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return body;
}

function setMessage(text, kind) {
  const msg = $("form-msg");
  msg.textContent = text;
  msg.className = kind || "";
}

async function loadLinks() {
  const links = await api("/api/links");
  const tbody = $("links");
  tbody.replaceChildren(
    ...links.map((link) =>
      el("tr", {}, [
        el("td", {}, [el("a", { href: link.short_url, target: "_blank", textContent: "/" + link.code })]),
        el("td", { title: link.target_url, textContent: link.target_url }),
        el("td", { className: "num", textContent: link.click_count }),
        el("td", {}, [
          el("button", { className: "link", type: "button", textContent: "Stats", onclick: () => showStats(link.code) }),
        ]),
      ])
    )
  );
  $("empty").hidden = links.length > 0;
}

function renderChart(days) {
  const w = 600, h = 160, pad = 18;
  const max = Math.max(1, ...days.map((d) => d.clicks));
  const barW = (w - pad) / days.length;
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  svg.setAttribute("preserveAspectRatio", "none");

  days.forEach((d, i) => {
    const barH = ((h - pad) * d.clicks) / max;
    const rect = document.createElementNS(ns, "rect");
    rect.setAttribute("x", pad + i * barW + 1);
    rect.setAttribute("y", h - pad - barH);
    rect.setAttribute("width", Math.max(1, barW - 2));
    rect.setAttribute("height", barH);
    rect.setAttribute("rx", 2);
    const title = document.createElementNS(ns, "title");
    title.textContent = `${d.date}: ${d.clicks} click${d.clicks === 1 ? "" : "s"}`;
    rect.append(title);
    svg.append(rect);
  });

  const maxLabel = document.createElementNS(ns, "text");
  maxLabel.setAttribute("x", 0);
  maxLabel.setAttribute("y", 10);
  maxLabel.textContent = max;
  const first = document.createElementNS(ns, "text");
  first.setAttribute("x", pad);
  first.setAttribute("y", h - 4);
  first.textContent = days[0].date;
  const last = document.createElementNS(ns, "text");
  last.setAttribute("x", w);
  last.setAttribute("y", h - 4);
  last.setAttribute("text-anchor", "end");
  last.textContent = days[days.length - 1].date;
  svg.append(maxLabel, first, last);

  $("chart").replaceChildren(svg);
}

async function showStats(code) {
  const stats = await api(`/api/links/${encodeURIComponent(code)}/stats`);
  $("stats-code").textContent = "/" + stats.link.code;
  $("stats-total").textContent = stats.total_clicks;
  renderChart(stats.clicks_by_day);
  const items = stats.top_referrers.map((r) =>
    el("li", { textContent: `${r.referrer} — ${r.clicks}` })
  );
  $("referrers").replaceChildren(...(items.length ? items : [el("li", { className: "muted", textContent: "No clicks yet" })]));
  $("stats").hidden = false;
  $("stats").scrollIntoView({ behavior: "smooth" });
}

$("create-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = { url: $("url").value.trim() };
  const alias = $("alias").value.trim();
  const expires = $("expires").value.trim();
  if (alias) payload.alias = alias;
  if (expires) payload.expires_in_hours = Number(expires);

  try {
    const link = await api("/api/links", { method: "POST", body: JSON.stringify(payload) });
    setMessage(`Created ${link.short_url}`, "ok");
    event.target.reset();
    await loadLinks();
  } catch (err) {
    setMessage(err.message, "error");
  }
});

loadLinks().catch((err) => setMessage(err.message, "error"));
