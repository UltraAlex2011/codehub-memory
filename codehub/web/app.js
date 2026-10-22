// Code Hub web view: connection to the local server, texts, header numbers,
// overview, live feed, sessions, the detail card, settings and premium.
// Messages arrive as server-sent events, commands go out as POST /api/cmd -
// both carry the token of this server run. Premium views (3D graph, token
// statistics, themes) arrive as extra scripts and register themselves with
// CodeHub.register(); without them their tabs show what premium brings.
(() => {
    const $ = id => document.getElementById(id);
    const root = document.documentElement;
    const TOKEN = root.dataset.token;
    const FEED_MAX = 400;
    const VIEWS = { overview: "viewOverview", graph: "viewGraph", tokens: "viewTokens", settings: "viewSettings" };
    const PREMIUM_VIEWS = ["graph", "tokens"];
    const ACCENTS = ["#7cc6a5", "#7fb4e6", "#b9a3e3", "#e6a37f", "#e58fb0", "#d8cf8a"];
    const THEMES = ["dark", "black", "light", "system"];

    // ---- per-viewer preferences (only this browser) ----
    const prefs = Object.assign({ theme: "dark", accent: ACCENTS[0], motion: "full", view: "overview" }, load("codehub.prefs"));
    function load(key) {
        try { return JSON.parse(localStorage.getItem(key) || "{}"); } catch (e) { return {}; }
    }
    function savePrefs() {
        try { localStorage.setItem("codehub.prefs", JSON.stringify(prefs)); } catch (e) { /* private window */ }
    }

    // ---- texts ----
    let lang = root.lang || "en", texts = {}, fallback = {};
    async function loadTexts(l) {
        const get = async x => { try { return await (await fetch(`/locale/${x}.json`)).json(); } catch (e) { return {}; } };
        [texts, fallback] = await Promise.all([get(l), l === "en" ? Promise.resolve({}) : get("en")]);
        lang = l;
        root.lang = l;
    }
    function t(key, vars) {
        let s = texts[key] ?? fallback[key] ?? key;
        if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => vars[k] ?? m);
        return s;
    }
    function applyTexts() {
        for (const el of document.querySelectorAll("[data-i18n]")) el.textContent = t(el.dataset.i18n);
        for (const el of document.querySelectorAll("[data-i18n-placeholder]")) el.placeholder = t(el.dataset.i18nPlaceholder);
        for (const el of document.querySelectorAll("[data-i18n-title]")) {
            el.title = t(el.dataset.i18nTitle);
            el.setAttribute("aria-label", el.title);
        }
    }
    const nf = (n, digits) => new Intl.NumberFormat(lang, { maximumFractionDigits: digits ?? 0, minimumFractionDigits: digits ?? 0 }).format(n);
    function big(n) {
        n = n || 0;
        if (n >= 1e9) return nf(n / 1e9, 2) + " " + t("web.unit_b");
        if (n >= 1e6) return nf(n / 1e6, 1) + " M";
        if (n >= 1e3) return nf(n / 1e3, 0) + " k";
        return nf(n);
    }
    const two = n => String(n).padStart(2, "0");
    const clock = s => { const d = new Date(s * 1000); return `${two(d.getHours())}:${two(d.getMinutes())}:${two(d.getSeconds())}`; };
    function dateOf(iso) {
        // "2026-10-22" as a local date (new Date(iso) would read it as UTC)
        const [y, m, d] = iso.split("-").map(Number);
        return new Date(y, m - 1, d || 1);
    }
    const day = iso => dateOf(iso).toLocaleDateString(lang, { day: "numeric", month: "short", year: "numeric" });
    const when = s => new Date(s * 1000).toLocaleString(lang, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
    const esc = Markdown.esc;

    // ---- look ----
    function applyLook() {
        // themes other than dark come with premium; without it they fall back
        const theme = license.active ? prefs.theme : "dark";
        const dark = matchMedia("(prefers-color-scheme: dark)").matches;
        root.dataset.theme = theme === "system" ? (dark ? "dark" : "light") : theme;
        root.style.setProperty("--accent", prefs.accent);
        root.dataset.motion = prefs.motion;
        for (const v of Object.values(views)) v.look && v.look();
        drawSpark();
    }
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyLook);

    // ---- server ----
    async function send(cmd) {
        try {
            const r = await fetch("/api/cmd", { method: "POST", headers: { "Content-Type": "application/json", "X-CodeHub-Token": TOKEN },
                                                body: JSON.stringify(cmd) });
            if (!r.ok) throw new Error(r.status);
            for (const m of await r.json()) handle(m);
        } catch (e) {
            toast(t("web.cmd_failed"));
        }
    }
    function connect() {
        const source = new EventSource(`/api/events?token=${encodeURIComponent(TOKEN)}`);
        source.onmessage = e => { $("offline").hidden = true; handle(JSON.parse(e.data)); };
        source.onerror = () => {
            $("offline").textContent = t("web.offline");
            $("offline").hidden = false;
        };
    }

    // ---- state ----
    let stats = {}, tokens = null, settings = null, detail = null, graphData = null, license = { active: false };
    let editing = false, editAfterOpen = "", titles = {}, current = "";
    const feedRows = [];
    const views = {};              // registered premium views: name -> {mount, show, message, ...}

    function handle(m) {
        switch (m.type) {
        case "graph": onGraph(m); break;
        case "stats": stats = m; renderNumbers(); renderSessions(); break;
        case "tokens": tokens = m; renderNumbers(); break;
        case "history": feedRows.length = 0; $("feed").textContent = ""; for (const e of m.list) addEvent(e, true); feedEmpty(); break;
        case "event": addEvent(m, false); break;
        case "detail": onDetail(m); break;
        case "saved": onSaved(m); break;
        case "created": onCreated(m); break;
        case "settings": onSettings(m); break;
        case "license": onLicense(m); break;
        case "notice": toast(m.text); break;
        case "doc_error": toast(m.text); break;
        }
        for (const v of Object.values(views)) v.message && v.message(m);
    }

    // ---- overview (free) ----
    function onGraph(m) {
        graphData = m;
        titles = {};
        for (const n of m.nodes) if (n.kind === "s") titles[n.id.slice(2, 10)] = n.name;
        if (current === "overview") renderOverview();
    }

    function renderOverview() {
        const v = $(VIEWS.overview);
        if (!graphData) { v.innerHTML = `<div class="empty"><strong>${esc(t("web.loading"))}</strong></div>`; return; }
        const q = $("search").value.trim().toLowerCase();
        if (q.length >= 2) return renderMatches(v, q);
        const nodes = graphData.nodes;
        const projects = nodes.filter(n => n.kind === "p").map(p => ({
            name: p.name,
            files: nodes.filter(n => n.kind === "d" && n.group === p.name).length,
            topics: nodes.filter(n => n.kind === "t" && n.group === p.name).length,
            sessions: nodes.filter(n => n.kind === "s" && n.group === p.name),
        })).map(p => Object.assign(p, { last: Math.max(0, ...p.sessions.map(s => s.time || 0)) }))
            .sort((a, b) => b.last - a.last || b.files - a.files);
        if (!projects.length) {
            v.innerHTML = `<div class="empty"><strong>${esc(t("web.graph_empty_title"))}</strong><span>${esc(t("web.graph_empty"))}</span><code>codehub add ~/path/to/project</code></div>`;
            return;
        }
        const recent = nodes.filter(n => n.kind === "s").sort((a, b) => (b.time || 0) - (a.time || 0)).slice(0, 8);
        const knowledge = nodes.filter(n => n.kind === "n" && (n.note === "decision" || n.note === "bug")).slice(-10).reverse();
        const card = p => `<button class="card project" data-node="p:${esc(p.name)}"><b>${esc(p.name)}</b>`
            + `<span>${esc(t("web.project_line", { files: nf(p.files), topics: nf(p.topics), sessions: nf(p.sessions.length) }))}</span>`
            + `<small>${p.last ? esc(t("web.last_session", { when: when(p.last) })) : "&nbsp;"}</small></button>`;
        const row = (n, color) => `<button data-node="${esc(n.id)}" style="--c:var(${color})"><i></i><span>${esc(n.name)}</span>`
            + (n.time ? `<em>${esc(when(n.time))}</em>` : "") + "</button>";
        v.innerHTML = `<div class="overview">`
            + `<div class="section-head"><h2>${esc(t("web.projects"))}</h2><span>${esc(t("web.overview_hint"))}</span></div>`
            + `<div class="projects">${projects.map(card).join("")}</div>`
            + `<div class="columns"><section><div class="section-head"><h2>${esc(t("web.recent_sessions"))}</h2></div>`
            + `<div class="links">${recent.map(n => row(n, "--session")).join("") || `<p class="info">${esc(t("web.nothing_yet"))}</p>`}</div></section>`
            + `<section><div class="section-head"><h2>${esc(t("web.knowledge"))}</h2></div>`
            + `<div class="links">${knowledge.map(n => row(n, n.note === "bug" ? "--bug" : "--decision")).join("") || `<p class="info">${esc(t("web.no_knowledge"))}</p>`}</div></section></div>`
            + (license.active ? "" : teaser())
            + `</div>`;
        wireNodes(v);
        const go = v.querySelector("[data-go]");
        if (go) go.onclick = () => showView(go.dataset.go);
    }

    function renderMatches(v, q) {
        // search without the graph: names and paths, the most important kinds first
        const order = "ptnsd";
        const found = graphData.nodes.filter(n => n.name.toLowerCase().includes(q) || n.id.toLowerCase().includes(q))
            .sort((a, b) => order.indexOf(a.kind) - order.indexOf(b.kind)).slice(0, 40);
        const color = { p: "--accent", t: "--topic", d: "--muted", n: "--note", s: "--session" };
        v.innerHTML = `<div class="overview"><div class="section-head"><h2>${esc(t("web.matches", { n: found.length }))}</h2></div>`
            + `<div class="links">${found.map(n => `<button data-node="${esc(n.id)}" style="--c:var(${color[n.kind]})"><i></i><span>${esc(n.name)}</span>`
                + `<em>${esc(n.path || n.group || "")}</em></button>`).join("") || `<p class="info">${esc(t("web.no_matches"))}</p>`}</div></div>`;
        wireNodes(v);
    }

    function teaser() {
        return `<button class="card teaser" data-go="graph"><svg><use href="#i-spark"/></svg><span><b>${esc(t("web.teaser_title"))}</b>`
            + `<small>${esc(t("web.teaser", { price: license.price || "" }))}</small></span></button>`;
    }

    function wireNodes(el) {
        for (const b of el.querySelectorAll("[data-node]")) b.onclick = () => selectNode(b.dataset.node);
    }

    // ---- premium: what it brings, buying, activating ----
    function onLicense(m) {
        const was = license.active && license.installed;
        license = m;
        applyLook();
        if (m.active && m.installed && !was && m.scripts.length) loadPremium(m.scripts);
        for (const name of PREMIUM_VIEWS) if (current === name && !views[name]) renderLocked(name);
        if (current === "overview") renderOverview();
        if (current === "settings") renderSettings();
    }

    async function loadPremium(files) {
        // the graph's layout simulation lives in the core (the Quickshell view shares it)
        for (const f of ["forces.js", ...files.map(x => "premium/" + x)]) {
            await new Promise(done => {
                const el = f.endsWith(".css")
                    ? Object.assign(document.createElement("link"), { rel: "stylesheet", href: f })
                    : Object.assign(document.createElement("script"), { src: f });
                el.onload = el.onerror = done;
                document.head.appendChild(el);
            });
        }
        applyLook();
        if (graphData) handle(graphData);
        if (tokens) handle(tokens);
        showView(current);
    }

    function renderLocked(name) {
        const v = $(VIEWS[name]);
        const buy = license.buy || {};
        const shops = [["lemonsqueezy", "Lemon Squeezy"], ["gumroad", "Gumroad"]].filter(([k]) => buy[k]);
        const needsPackage = license.active && !license.installed;
        v.innerHTML = `<div class="offer-wrap"><div class="card offer">`
            + `<div class="offer-head"><svg><use href="#i-lock"/></svg><h2>${esc(t("web.premium_title"))}</h2><span class="price">${esc(license.price || "")}</span></div>`
            + `<p>${esc(t(name === "graph" ? "web.premium_graph" : "web.premium_tokens"))}</p>`
            + `<ul>${["web.pf_graph", "web.pf_tokens", "web.pf_bench", "web.pf_themes", "web.pf_once"].map(k => `<li>${esc(t(k, { devices: license.devices || 3 }))}</li>`).join("")}</ul>`
            + (needsPackage
                ? `<div class="drop" id="drop"><b>${esc(t("web.premium_package"))}</b><span>${esc(t("web.premium_package_hint"))}</span>`
                  + `<button class="btn" id="pickZip">${esc(t("web.choose_file"))}</button><input type="file" id="zipInput" accept=".zip" hidden></div>`
                : (shops.length
                    ? `<div class="buy">${shops.map(([k, label]) => `<a class="btn primary" href="${esc(buy[k])}" target="_blank" rel="noopener">${esc(t("web.buy_at", { shop: label }))}</a>`).join("")}</div>`
                    : `<p class="info">${esc(t("web.shop_soon"))}</p>`)
                  + `<form class="activate" id="activate"><input id="licenseKey" autocomplete="off" spellcheck="false" placeholder="${esc(t("web.key_placeholder"))}">`
                  + `<button class="btn" type="submit">${esc(t("web.activate"))}</button></form>`
                  + `<p class="info">${esc(t("web.key_hint"))}</p>`)
            + `</div></div>`;
        const form = $("activate");
        if (form) form.onsubmit = e => {
            e.preventDefault();
            const key = $("licenseKey").value.trim();
            if (key) { form.querySelector("button").disabled = true; send({ cmd: "activate", key }).then(() => { if ($("activate")) $("activate").querySelector("button").disabled = false; }); }
        };
        const drop = $("drop");
        if (drop) {
            const take = file => file && file.arrayBuffer().then(buf => {
                let bin = "";
                const bytes = new Uint8Array(buf);
                for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
                send({ cmd: "premium_install", data: btoa(bin) });
            });
            drop.ondragover = e => { e.preventDefault(); drop.classList.add("over"); };
            drop.ondragleave = () => drop.classList.remove("over");
            drop.ondrop = e => { e.preventDefault(); drop.classList.remove("over"); take(e.dataTransfer.files[0]); };
            $("pickZip").onclick = () => $("zipInput").click();
            $("zipInput").onchange = e => take(e.target.files[0]);
        }
    }

    // ---- header numbers ----
    function renderNumbers() {
        const today = stats.today || {};
        const hooks = stats.hooks !== false;
        const asked = (today.lookup || 0) + (today.auto || 0) + (today.search || 0), free = today.free || 0;
        const share = $("nShare"), hits = $("nHits"), tok = $("nTokens");
        share.toggleAttribute("data-off", !hooks);
        hits.toggleAttribute("data-off", !hooks);
        share.querySelector("b").textContent = hooks && asked + free ? Math.round(100 * asked / (asked + free)) + " %" : "–";
        share.querySelector("small").textContent = hooks ? t("web.share_detail", { hub: asked, free }) : t("web.needs_hooks");
        share.title = t("web.share_tip");
        hits.querySelector("b").textContent = hooks ? `${today.hit || 0} / ${today.read || 0}` : "–";
        hits.querySelector("small").textContent = hooks ? t("web.hits_detail") : t("web.needs_hooks");
        hits.title = t("web.hits_tip");
        const used = tokens ? tokens.today.tokens : (today.tok_in || 0) + (today.tok_out || 0) + (today.tok_cache_write || 0);
        const cache = tokens ? tokens.today.cache : today.tok_cache_read || 0;
        tok.querySelector("b").textContent = big(used);
        tok.querySelector("small").textContent = cache ? t("web.cache_read", { n: big(cache) }) : "";
        tok.title = tokens ? t("web.tokens_tip", { week: big(tokens.week.tokens), month: big(tokens.month.tokens), total: big(tokens.total.tokens) }) : "";
        drawSpark();
    }

    function drawSpark() {
        const days = stats.days || [];
        const svg = $("spark");
        if (!days.length) { svg.innerHTML = ""; return; }
        const most = Math.max(1, ...days.map(d => d.tokens));
        const w = 70 / days.length;
        svg.innerHTML = days.map((d, i) => {
            const h = Math.max(1.5, 26 * d.tokens / most);
            const share = d.hub + d.free ? d.hub / (d.hub + d.free) : 0;
            return `<rect x="${i * w + 1}" y="${28 - h}" width="${w - 2}" height="${h}" rx="1.5" fill="var(--accent)" opacity="${0.25 + 0.6 * share}"><title>${esc(d.day)}: ${big(d.tokens)}</title></rect>`;
        }).join("");
    }

    // ---- sessions ----
    function renderSessions() {
        const list = stats.active || [];
        $("sessionCount").textContent = t("web.active", { n: list.length });
        const box = $("sessions");
        box.textContent = "";
        if (!list.length) {
            box.innerHTML = `<p class="none">${esc(t("web.no_sessions"))}</p>`;
            return;
        }
        for (const a of list.slice(0, 4)) {
            const b = document.createElement("button");
            const working = a.state === "working";
            b.className = "session" + (working ? " working" : "");
            const who = a.agent && a.agent !== "main" ? a.agent.split("#")[0] + ": " : "";
            b.innerHTML = `<i></i><b>${esc(a.title)}${a.project ? " · " + esc(a.project) : ""}</b><em>${big(a.tokens)}</em>`
                + `<small>${esc(who + (a.action || (working ? t("web.working") : t("web.waiting"))))}</small>`;
            b.onclick = () => selectNode("s:" + a.id);
            box.appendChild(b);
        }
    }

    // ---- live feed ----
    const TOOL_ICON = { Read: "read", Edit: "edit", MultiEdit: "edit", Write: "edit", NotebookEdit: "edit", Bash: "shell",
                        Grep: "find", Glob: "find", Agent: "agent", Task: "agent", WebFetch: "web", WebSearch: "web" };
    const EVENT_ICON = { prompt: "prompt", lookup: "hub", map: "map", note: "note", stop: "done", start: "flag", end: "flag",
                         compact: "compact", notify: "bell", log: "flag", "sub+": "agent", "sub-": "agent" };
    function icon(e) {
        if (e.e === "pre" || e.e === "post" || e.e === "error") {
            if ((e.w || "").startsWith("mcp__codehub__")) return "hub";
            return TOOL_ICON[e.w] || "flag";
        }
        return EVENT_ICON[e.e] || "flag";
    }
    function agentName(a, session) {
        if (a === "main") {
            const title = titles[session];
            // several sessions at once: short title instead of "Claude"
            return (stats.active || []).length > 1 && title ? (title.length > 14 ? title.slice(0, 13) + "…" : title) : "Claude";
        }
        if (a === "hub") return "Hub";
        if (a === "claude") return "Claude";
        return (a || "").split("#")[0];
    }
    const agentColor = a => a === "main" || a === "claude" ? "var(--accent)" : a === "hub" ? "var(--read)" : "var(--topic)";
    function eventText(m) {
        const tool = (m.w || "").startsWith("mcp__") ? m.w.split("__").slice(2).join("__") : m.w;
        switch (m.e) {
        case "prompt": return esc(m.d || "");
        case "lookup": return esc(t(m.x === "auto" ? "web.e_lookup_auto" : "web.e_lookup"));
        case "map": return esc(t("web.e_map", { path: m.r, topic: m.x }));
        case "note": return esc(t("web.e_note", { path: m.d }));
        case "stop": return esc(t("web.e_stop") + (m.x ? " – " + m.x : ""));
        case "start": return esc(t("web.e_start") + (m.d ? " · " + m.d : ""));
        case "end": return esc(t("web.e_end"));
        case "compact": return esc(t(m.x === "done" ? "web.e_compacted" : "web.e_compacting"));
        case "notify": return esc(m.x || "");
        case "log": return esc((m.w || "") + (m.d ? ": " + m.d : ""));
        case "sub+": return esc(t("web.e_sub_start") + (m.d ? ": " + m.d : ""));
        case "sub-": return esc(t("web.e_sub_done") + (m.x ? ": " + m.x : ""));
        }
        return `<b>${esc(tool || "")}</b>  ${esc(m.r || m.d || "")}`;
    }
    function target(m) {
        if (m.p && m.r) return `d:${m.p}:${m.r}`;
        if (m.e === "note" && m.d) return "n:" + m.d;
        return m.s ? "s:" + m.s : "";
    }
    function addEvent(e, quiet) {
        const feed = $("feed");
        if (e.e === "post" || e.e === "error") {
            // finish the matching "pre" line instead of adding a new one
            for (let i = 0; i < Math.min(feedRows.length, 60); i++) {
                const r = feedRows[i];
                if (r.id && r.id === e.id && r.s === e.s) {
                    r.el.classList.remove("running");
                    r.el.classList.toggle("failed", e.e === "error");
                    const how = r.el.querySelector(".how");
                    how.className = "how" + (e.h ? " hit" : "");
                    how.textContent = e.h ? t("web.from_hub") : e.ms ? (e.ms < 1000 ? e.ms + " ms" : nf(e.ms / 1000, 1) + " s") : "";
                    if (e.e === "error" && e.x) r.el.title = e.x;
                    return;
                }
            }
        }
        const el = document.createElement("button");
        el.className = "row" + (e.e === "pre" ? " running" : e.e === "error" ? " failed" : "");
        if (quiet) el.style.animation = "none";
        el.innerHTML = `<time>${clock(e.t)}</time><span class="who" style="--c:${agentColor(e.a)}">${esc(agentName(e.a, e.s))}</span>`
            + `<svg><use href="#t-${icon(e)}"/></svg><span class="what">${eventText(e)}</span>`
            + `<span class="how${e.h ? " hit" : ""}">${e.h ? esc(t("web.from_hub")) : e.ms ? e.ms + " ms" : ""}</span>`;
        const goal = target(e);
        el.title = e.x && e.e !== "stop" ? String(e.x) : "";
        if (goal) el.onclick = () => selectNode(goal);
        feed.insertBefore(el, feed.firstChild);
        feedRows.unshift({ id: e.id, s: e.s, el });
        while (feedRows.length > FEED_MAX) feedRows.pop().el.remove();
        if (!quiet) feedEmpty();
    }
    function feedEmpty() {
        const feed = $("feed");
        const old = feed.querySelector(".empty");
        if (old) old.remove();
        if (feedRows.length) return;
        const box = document.createElement("div");
        box.className = "empty";
        box.innerHTML = stats.hooks === false
            ? `<strong>${esc(t("web.feed_no_hooks_title"))}</strong><span>${esc(t("web.feed_no_hooks"))}</span><code>codehub install</code>`
            : `<strong>${esc(t("web.feed_empty_title"))}</strong><span>${esc(t("web.feed_empty"))}</span>`;
        feed.appendChild(box);
    }

    function selectNode(id) {
        // with the graph: fly there; without it: the card over the current view
        const graph = views.graph;
        if (graph && graph.select(id)) { showView("graph"); return; }
        if (id.startsWith("s:") && id.length <= 10 && graphData) {
            // the feed knows only the first 8 characters of a session id
            const full = graphData.nodes.find(n => n.id.startsWith(id));
            if (full) id = full.id;
        }
        if (PREMIUM_VIEWS.includes(current)) showView("overview");
        send({ cmd: "detail", id });
    }

    // ---- detail card ----
    const KIND_COLOR = { p: "--accent", t: "--topic", d: "--muted", n: "--note", s: "--session" };
    function onDetail(d) {
        if (editing && detail && detail.id === d.id) {
            // while writing only the stamp changes: saving again overwrites
            const text = $("editor").value;
            detail = d;
            renderDetail();
            $("editor").value = text;
            return;
        }
        if (editing) return;            // never throw away unsaved text for another node
        detail = d;
        editing = editAfterOpen === d.id && d.raw !== undefined;
        editAfterOpen = "";
        renderDetail();
    }
    function renderDetail() {
        const card = $("detail");
        const d = detail;
        if (!d || current === "settings" || (PREMIUM_VIEWS.includes(current) && !views[current])) { card.hidden = true; return; }
        const kind = d.id.split(":")[0];
        card.hidden = false;
        card.style.setProperty("--c", `var(${KIND_COLOR[kind] || "--accent"})`);
        let body = `<p class="sub">${esc(d.sub || "")}</p>`;
        if (kind === "d") {
            body += `<p class="lead">${esc(d.text || t("web.no_description"))}</p>`;
            const topics = [d.topic].concat((d.also || "").split(" · ").filter(Boolean)).filter(Boolean);
            body += `<div class="tags">${topics.map(x => `<button class="tag" data-topic="${esc(x)}">${esc(x)}</button>`).join("")}`
                + `<span class="info">${esc(d.info || "")}</span></div>`;
            if ((d.sessions || []).length)
                body += `<h4>${esc(t("web.changed_in"))}</h4><div class="links">` + d.sessions.map(x =>
                    `<button data-node="${esc(x.id)}"><i></i><span>${esc(x.time)}  ${esc(x.title)}${x.n > 1 ? `  (${x.n}×)` : ""}</span></button>`).join("") + "</div>";
        }
        if ((d.backlinks || []).length && !editing) {
            const color = k => k === "session" ? "--session" : k === "decision" ? "--decision" : k === "bug" ? "--bug" : "--note";
            body += `<h4>${esc(t("web.linked_from"))}${d.backlinks.length > 6 ? " · " + d.backlinks.length : ""}</h4><div class="links">`
                + d.backlinks.slice(0, 6).map(x => `<button data-node="${esc(x.id)}" style="--c:var(${color(x.kind)})"><i></i><span>${esc(x.title)}</span></button>`).join("")
                + "</div>";
        }
        if (editing) {
            body += `<textarea class="editor" id="editor" spellcheck="false"></textarea>`
                + `<div class="edit-bar"><span class="grow">${esc(t("web.edit_keys"))}</span>`
                + `<button class="btn" id="editCancel">${esc(t("web.cancel"))}</button><button class="btn primary" id="editSave">${esc(t("web.save"))}</button></div>`;
        } else if (kind === "d") {
            if (d.preview) body += `<pre class="preview">${esc(d.preview)}</pre>`;
        } else if (d.text) {
            body += `<div class="md">${Markdown.render(d.text)}</div>`;
        }
        const editable = d.raw !== undefined;
        card.innerHTML = `<div class="detail-head"><span class="dot"></span><h3>${esc(d.title || "")}</h3>`
            + (editable && !editing ? `<button class="icon-btn" id="dEdit" title="${esc(t("web.edit"))}"><svg><use href="#i-pen"/></svg></button>` : "")
            + (d.path ? `<button class="icon-btn" id="dOpen" title="${esc(t("web.open_external"))}"><svg><use href="#i-open"/></svg></button>` : "")
            + (views.graph ? `<button class="icon-btn" id="dFly" title="${esc(t("web.fly"))}"><svg><use href="#i-target"/></svg></button>` : "")
            + `<button class="icon-btn" id="dClose" title="${esc(t("web.close"))}"><svg><use href="#i-close"/></svg></button></div>`
            + `<div class="detail-body">${body}</div>`;
        const on = (id, f) => { const el = $(id); if (el) el.onclick = f; };
        on("dClose", closeDetail);
        on("dOpen", () => send({ cmd: "open", id: d.id }));
        on("dFly", () => selectNode(d.id));
        on("dEdit", startEdit);
        on("editCancel", () => { editing = false; renderDetail(); });
        on("editSave", saveEdit);
        if (editing) {
            const ed = $("editor");
            ed.value = d.raw;
            ed.focus();
            ed.onkeydown = e => {
                if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); saveEdit(); }
                if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); editing = false; renderDetail(); }
            };
        }
        wireNodes(card);
        for (const b of card.querySelectorAll("[data-topic]"))
            b.onclick = () => selectNode(`t:${d.id.split(":")[1]}:${b.dataset.topic}`);
        for (const a of card.querySelectorAll("a[data-hub]"))
            a.onclick = e => { e.preventDefault(); selectNode(decodeURIComponent(a.dataset.hub)); };
    }
    function closeDetail() {
        detail = null;
        editing = false;
        $("detail").hidden = true;
        views.graph && views.graph.clear();
    }
    function startEdit() { editing = true; renderDetail(); }
    function saveEdit() {
        const ed = $("editor");
        if (ed && detail) send({ cmd: "save", id: detail.id, text: ed.value, stamp: detail.stamp });
    }
    function onSaved(m) {
        // the fresh detail follows in the same answer
        if (m.ok) { editing = false; toast(t("web.saved")); }
        else toast(m.reason || t("web.cmd_failed"));
    }
    function onCreated(m) {
        editAfterOpen = m.id;
        selectNode(m.id);
    }

    // ---- settings ----
    function onSettings(m) {
        const first = !settings;
        settings = m;
        if (m.language !== lang) {
            loadTexts(m.language).then(() => { applyTexts(); renderAll(); });
        } else if (first) {
            renderAll();
        }
        if (current === "settings") renderSettings();
    }
    function renderAll() {
        renderNumbers();
        renderSessions();
        feedEmpty();
        renderKeys();
        for (const v of Object.values(views)) v.relabel && v.relabel();
        showView(current);
    }
    function renderSettings() {
        const v = $(VIEWS.settings);
        if (!settings) return;
        const s = settings.values;
        const seg = (name, options, value, locked) => `<div class="segmented" data-seg="${name}">` + options.map(([key, label]) =>
            `<button data-value="${esc(key)}" aria-pressed="${key === value}"${locked && locked.includes(key) ? ` class="locked" title="${esc(t("web.premium_only"))}"` : ""}>${esc(label)}</button>`).join("") + "</div>";
        const sw = (name, on) => `<button class="switch" role="switch" data-switch="${name}" aria-checked="${!!on}"></button>`;
        const row = (title, hint, control) => `<div class="setting"><div><strong>${esc(title)}</strong>${hint ? `<small>${esc(hint)}</small>` : ""}</div>${control}</div>`;
        const swatches = `<div class="swatches">` + ACCENTS.map(c => `<button class="swatch" style="--c:${c}" data-accent="${c}" aria-pressed="${c === prefs.accent}" title="${c}"></button>`).join("")
            + `<input type="color" id="accentCustom" value="${prefs.accent}" title="${esc(t("web.custom_color"))}"></div>`;
        const lockedThemes = license.active ? [] : THEMES.slice(1);
        const lic = license.active
            ? `<p><i style="--c:var(--accent)"></i>${esc(t("web.premium_on", { email: license.email || "" }))}</p>`
              + `<p class="info">${esc(t("web.premium_key", { key: license.key || "", version: license.version || "–" }))}</p>`
              + `<p><button class="btn" id="deactivate">${esc(t("web.deactivate"))}</button></p>`
            : `<p><i style="--c:var(--faint)"></i>${esc(t("web.premium_off", { price: license.price || "" }))}</p>`
              + `<p><button class="btn primary" data-go="graph">${esc(t("web.premium_see"))}</button></p>`;
        v.innerHTML = `<div class="settings">`
            + `<section><h2>${esc(t("web.s_look"))}</h2><div class="group card">`
            + row(t("web.s_theme"), license.active ? "" : t("web.themes_premium"), seg("theme", [["dark", t("web.theme_dark")], ["black", t("web.theme_black")], ["light", t("web.theme_light")], ["system", t("web.theme_system")]], license.active ? prefs.theme : "dark", lockedThemes))
            + row(t("web.s_accent"), t("web.s_accent_hint"), swatches)
            + row(t("web.s_motion"), t("web.s_motion_hint"), seg("motion", [["full", t("web.motion_full")], ["reduced", t("web.motion_reduced")]], prefs.motion))
            + row(t("web.s_language"), t("web.s_language_hint"), seg("language", [["en", "English"], ["de", "Deutsch"]], settings.language))
            + `</div></section>`
            + `<section><h2>${esc(t("web.s_claude"))}</h2><div class="group card">`
            + row(t("web.s_auto"), t("web.s_auto_hint"), sw("autoLookup", s.autoLookup))
            + row(t("web.s_start"), t("web.s_start_hint"), sw("startContext", s.startContext))
            + `</div></section>`
            + `<section><h2>${esc(t("web.s_vault"))}</h2><div class="group card">`
            + row(t("web.s_push"), t("web.s_push_hint"), sw("push", s.push))
            + row(t("web.s_logs"), t("web.s_logs_hint"), `<input class="number-input" type="number" min="3" max="365" id="logDays" value="${Number(s.logDays) || 30}">`)
            + `</div></section>`
            + `<section><h2>Premium</h2><div class="card state">${lic}</div></section>`
            + `<section><h2>${esc(t("web.s_state"))}</h2><div class="card state">`
            + `<p><i style="--c:var(${settings.hooks ? "--accent" : "--warn"})"></i>${esc(t(settings.hooks ? "web.hooks_on" : "web.hooks_off"))}</p>`
            + (settings.hooks ? "" : `<p><code class="info">codehub install</code></p>`)
            + `</div></section></div>`;
        for (const g of v.querySelectorAll("[data-seg]")) for (const b of g.querySelectorAll("button")) b.onclick = () => {
            const name = g.dataset.seg, value = b.dataset.value;
            if (b.classList.contains("locked")) { showView("graph"); return; }
            if (name === "language") send({ cmd: "settings_set", name: "language", value });
            else { prefs[name] = value; savePrefs(); applyLook(); renderSettings(); }
        };
        for (const b of v.querySelectorAll("[data-switch]")) b.onclick = () => {
            const value = b.getAttribute("aria-checked") !== "true";
            b.setAttribute("aria-checked", String(value));
            send({ cmd: "settings_set", name: b.dataset.switch, value });
        };
        for (const b of v.querySelectorAll("[data-accent]")) b.onclick = () => { prefs.accent = b.dataset.accent; savePrefs(); applyLook(); renderSettings(); };
        for (const b of v.querySelectorAll("[data-go]")) b.onclick = () => showView(b.dataset.go);
        $("accentCustom").oninput = e => { prefs.accent = e.target.value; savePrefs(); applyLook(); };
        $("accentCustom").onchange = () => renderSettings();
        $("logDays").onchange = e => {
            const n = Math.max(3, Math.min(365, Number(e.target.value) || 30));
            e.target.value = n;
            send({ cmd: "settings_set", name: "logDays", value: n });
        };
        const off = $("deactivate");
        if (off) off.onclick = () => send({ cmd: "deactivate" });
    }

    // ---- views and keys ----
    function showView(name) {
        if (!VIEWS[name]) name = "overview";
        const leaving = current !== name;
        current = name;
        prefs.view = name;
        savePrefs();
        for (const [view, id] of Object.entries(VIEWS)) $(id).hidden = view !== name;
        for (const b of document.querySelectorAll(".rail-btn[data-view]")) {
            if (b.dataset.view === name) b.setAttribute("aria-current", "page");
            else b.removeAttribute("aria-current");
            b.classList.toggle("locked", PREMIUM_VIEWS.includes(b.dataset.view) && !views[b.dataset.view]);
        }
        if (name === "overview") renderOverview();
        else if (name === "settings") renderSettings();
        else if (views[name]) views[name].show();
        else renderLocked(name);
        if (leaving || !detail) renderDetail();
    }

    const KEYS = [[["/"], "web.k_search"], [["Enter"], "web.k_choose"], [["Esc"], "web.k_escape"], [["F"], "web.k_fit"],
                  [["R"], "web.k_rotate"], [["N"], "web.k_new"], [["1"], "web.view_overview"], [["2"], "web.view_graph"],
                  [["3"], "web.view_tokens"], [["4"], "web.view_settings"], [["?"], "web.keys"]];
    function renderKeys() {
        $("keys").innerHTML = `<div class="card"><h2>${esc(t("web.keys"))}</h2><dl>`
            + KEYS.map(([k, label]) => `<dt>${k.map(x => `<kbd>${esc(x)}</kbd>`).join("")}</dt><dd>${esc(t(label))}</dd>`).join("") + "</dl></div>";
    }
    function toggleKeys(show) { $("keys").hidden = !(show ?? $("keys").hidden); }
    $("keys").onclick = () => toggleKeys(false);
    $("keysBtn").onclick = () => toggleKeys(true);

    function search(q) {
        const v = views[current];
        if (v && v.search) v.search(q);
        else if (current === "overview") renderOverview();
        else if (q.trim().length >= 2) { showView(views.graph ? "graph" : "overview"); search(q); }
    }

    document.addEventListener("keydown", e => {
        const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
        if (e.key === "Escape") {
            if (!$("keys").hidden) return toggleKeys(false);
            if (typing) { document.activeElement.blur(); if (document.activeElement !== $("search")) return; }
            if ($("search").value) { $("search").value = ""; search(""); return; }
            if (detail) return closeDetail();
            return;
        }
        if (typing || e.ctrlKey || e.metaKey || e.altKey) return;
        const k = e.key;
        const order = ["overview", "graph", "tokens", "settings"];
        if (k === "/") { e.preventDefault(); $("search").focus(); }
        else if (k === "?") toggleKeys();
        else if (k === "n" || k === "N") send({ cmd: "new" });
        else if (k >= "1" && k <= "4") showView(order[Number(k) - 1]);
        else if (views[current] && views[current].key) views[current].key(k.toLowerCase());
    });

    let toastTimer = 0;
    function toast(text) {
        const el = $("toast");
        el.textContent = text;
        el.hidden = false;
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => { el.hidden = true; }, 3600);
    }

    // ---- what premium scripts may use ----
    window.CodeHub = {
        t, esc, nf, big, day, dateOf, when, send, toast, prefs, savePrefs, selectNode, closeDetail,
        get stats() { return stats; },
        get tokens() { return tokens; },
        get graph() { return graphData; },
        get editing() { return editing; },
        element: name => $(VIEWS[name]),
        detailShown: id => !!detail && detail.id === id,
        hideDetail() { if (!editing) { detail = null; $("detail").hidden = true; } },
        register(name, view) {
            views[name] = view;
            view.mount($(VIEWS[name]));
            if (current === name) showView(name);
        },
    };

    // ---- start ----
    async function start() {
        await loadTexts(lang);
        applyTexts();
        applyLook();
        renderKeys();
        $("search").addEventListener("input", e => search(e.target.value));
        $("search").addEventListener("keydown", e => {
            if (e.key !== "Enter") return;
            const v = views[current];
            if (v && v.choose) { v.choose(); e.target.blur(); }
            else {
                const first = $(VIEWS.overview).querySelector("[data-node]");
                if (first) { first.click(); e.target.blur(); }
            }
        });
        $("nTokens").onclick = () => showView("tokens");
        $("newNote").onclick = () => send({ cmd: "new" });
        for (const b of document.querySelectorAll(".rail-btn[data-view]")) b.onclick = () => showView(b.dataset.view);
        showView(prefs.view);
        connect();
    }
    start();
})();
