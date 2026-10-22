// Code Hub website: texts in English and German, install commands, buy
// buttons from shop.json (the program's own shop file, copied here when the
// site is published) and the living graph at the top - the program's force
// simulation with made-up example projects.
(() => {
    const T = {
        en: {
            nav_how: "How it works", nav_pricing: "Pricing", nav_install: "Install", nav_faq: "FAQ",
            eyebrow: "Memory for Claude Code",
            title: "Claude stops searching. It remembers.",
            lead: "Code Hub knows which file is responsible for what, remembers decisions, solved bugs and every session – and hands Claude exactly the files it needs. Fewer searches, fewer tokens, sessions that remember yesterday.",
            cta_install: "Install for free", cta_premium: "Premium – 10 €",
            hero_fine: "macOS · Windows · Linux · runs locally · no account",
            how_title: "How it works",
            step1: "Install with one line", step1_text: "Code Hub maps your projects from their docs and file headers and connects itself to Claude Code.",
            step2: "Claude asks the map first", step2_text: "Before every search, Claude looks up the files for the topic – and opens only those.",
            step3: "Everything is remembered", step3_text: "Decisions, bugs with their cause and a log of every session land in your own Markdown vault.",
            f_map: "Project maps", f_map_text: "Topic → files, each with one line of description. Built without spending a single token, kept up to date while Claude works.",
            f_auto: "Matching files with every prompt", f_auto_text: "When the map is sure, up to six fitting files arrive with your prompt – Claude starts in the right place.",
            f_memory: "A memory that lasts", f_memory_text: "Claude records decisions and solved bugs; every session gets a note. Next week, Claude finds them again.",
            f_feed: "Live feed", f_feed_text: "See every step of Claude and its subagents as it happens – in the browser view.",
            f_local: "Yours, local, open", f_local_text: "Plain Markdown that works with Obsidian, a git repo you control, an open-source core under MIT.",
            f_numbers: "Honest numbers", f_numbers_text: "How often Claude asked the map instead of searching, and how often the map was right.",
            pricing_title: "Pricing",
            free: "Free", free_cta: "Install",
            free1: "Project maps and hub_lookup", free2: "Matching files with every prompt", free3: "Decisions, bugs, session notes", free4: "Overview and live feed in the browser", free5: "Open source (MIT)",
            once: "once", prem0: "Everything in Free, plus:",
            prem1: "3D graph of your whole memory – whatever Claude touches lights up", prem2: "Token statistics per day, month and project",
            prem3: "codehub bench – measures the savings on your own code", prem4: "Themes: black (OLED), light, system", prem5: "Up to 3 computers · no subscription",
            prem_fine: "After buying you get a license key and the premium package by email. Unlock: codehub premium <key>.",
            buy_at: "Buy at {shop}", soon: "The shop opens soon.",
            install_title: "Install", install_text: "Open a terminal, paste one line, answer two questions. Code Hub sets itself up for Claude Code and opens its view.",
            copy: "Copy", copied: "Copied",
            hint_unix: "Needs Python 3.9 or newer – macOS offers to install it if it is missing.",
            hint_win: "In PowerShell. Installs Python with winget if it is missing.",
            hint_pipx: "If you already use pipx: then run “codehub install”.",
            after1: "Restart Claude Code – it now asks the map before searching.",
            after2: "“codehub open” shows the view, “codehub doctor” checks the setup.",
            after3: "“codehub update” brings the newest version, “codehub uninstall” removes everything but your vault.",
            faq_title: "Questions",
            q_privacy: "Does my code leave my computer?", a_privacy: "No. Maps, notes and the index stay on your machine. Code Hub only adds short context to what Claude Code sends anyway. Unlocking premium sends the license key to the shop once and every 14 days.",
            q_tokens: "How many tokens does it save?", a_tokens: "That depends on your projects – we would rather not promise a number. Premium includes codehub bench: it asks Claude the same questions with and without Code Hub on your own code and shows the difference.",
            q_systems: "Which systems?", a_systems: "macOS, Windows and Linux with Python 3.9 or newer and Claude Code. No other dependencies.",
            q_license: "How does the premium license work?", a_license: "One payment, no subscription. The key unlocks premium on up to three of your computers; remove it from one to move it to another (codehub premium remove).",
            q_refund: "Refunds?", a_refund: "Purchases go through Lemon Squeezy or Gumroad; their refund policy and your rights as a consumer apply. A refunded key stops working.",
            q_obsidian: "Do I need Obsidian?", a_obsidian: "No. The vault is plain Markdown – Obsidian is a nice way to read it, not a requirement.",
            q_remove: "How do I remove it?", a_remove: "codehub uninstall takes out the hooks, the MCP server and the rule block. Your vault stays where it is.",
            not_anthropic: "Independent project, not affiliated with Anthropic. Claude is a trademark of Anthropic.",
            imprint: "Imprint", privacy: "Privacy",
        },
        de: {
            nav_how: "So geht's", nav_pricing: "Preise", nav_install: "Installieren", nav_faq: "Fragen",
            eyebrow: "Gedächtnis für Claude Code",
            title: "Claude sucht nicht mehr. Es erinnert sich.",
            lead: "Code Hub weiß, welche Datei wofür zuständig ist, merkt sich Entscheidungen, gelöste Bugs und jede Sitzung – und gibt Claude genau die Dateien, die es braucht. Weniger Suchen, weniger Tokens, Sitzungen, die sich an gestern erinnern.",
            cta_install: "Kostenlos installieren", cta_premium: "Premium – 10 €",
            hero_fine: "macOS · Windows · Linux · läuft lokal · ohne Konto",
            how_title: "So geht's",
            step1: "Mit einer Zeile installieren", step1_text: "Code Hub kartiert deine Projekte aus Doku und Dateiköpfen und verbindet sich mit Claude Code.",
            step2: "Claude fragt zuerst die Karte", step2_text: "Vor jeder Suche schaut Claude nach, welche Dateien zum Thema gehören – und öffnet nur diese.",
            step3: "Alles bleibt erhalten", step3_text: "Entscheidungen, Bugs mit Ursache und ein Protokoll jeder Sitzung landen in deinem eigenen Markdown-Vault.",
            f_map: "Projektkarten", f_map_text: "Thema → Dateien mit je einer Zeile Beschreibung. Entsteht ohne ein einziges Token und bleibt aktuell, während Claude arbeitet.",
            f_auto: "Passende Dateien bei jedem Prompt", f_auto_text: "Ist die Karte sicher, kommen bis zu sechs passende Dateien mit deinem Prompt – Claude fängt an der richtigen Stelle an.",
            f_memory: "Ein Gedächtnis, das bleibt", f_memory_text: "Claude hält Entscheidungen und gelöste Bugs fest; jede Sitzung bekommt eine Notiz. Nächste Woche findet Claude sie wieder.",
            f_feed: "Live-Feed", f_feed_text: "Jeder Schritt von Claude und seinen Subagenten, während er passiert – in der Browser-Ansicht.",
            f_local: "Deins, lokal, offen", f_local_text: "Einfaches Markdown, das mit Obsidian funktioniert, ein Git-Repo unter deiner Kontrolle, ein Open-Source-Kern unter MIT.",
            f_numbers: "Ehrliche Zahlen", f_numbers_text: "Wie oft Claude die Karte statt einer Suche gefragt hat – und wie oft die Karte richtig lag.",
            pricing_title: "Preise",
            free: "Gratis", free_cta: "Installieren",
            free1: "Projektkarten und hub_lookup", free2: "Passende Dateien bei jedem Prompt", free3: "Entscheidungen, Bugs, Sitzungsnotizen", free4: "Überblick und Live-Feed im Browser", free5: "Open Source (MIT)",
            once: "einmalig", prem0: "Alles aus Gratis, dazu:",
            prem1: "3D-Graph deines ganzen Gedächtnisses – was Claude anfasst, leuchtet auf", prem2: "Token-Statistik je Tag, Monat und Projekt",
            prem3: "codehub bench – misst die Ersparnis an deinem eigenen Code", prem4: "Themes: Schwarz (OLED), Hell, System", prem5: "Bis zu 3 Rechner · kein Abo",
            prem_fine: "Nach dem Kauf kommen Lizenzschlüssel und Premium-Paket per Mail. Freischalten: codehub premium <schlüssel>.",
            buy_at: "Kaufen bei {shop}", soon: "Der Shop öffnet bald.",
            install_title: "Installieren", install_text: "Terminal öffnen, eine Zeile einfügen, zwei Fragen beantworten. Code Hub richtet sich für Claude Code ein und öffnet seine Ansicht.",
            copy: "Kopieren", copied: "Kopiert",
            hint_unix: "Braucht Python 3.9 oder neuer – fehlt es, bietet macOS die Installation an.",
            hint_win: "In der PowerShell. Fehlt Python, wird es mit winget installiert.",
            hint_pipx: "Wenn du pipx schon nutzt: danach „codehub install“.",
            after1: "Claude Code neu starten – ab jetzt fragt es zuerst die Karte.",
            after2: "„codehub open“ zeigt die Ansicht, „codehub doctor“ prüft die Einrichtung.",
            after3: "„codehub update“ holt die neueste Version, „codehub uninstall“ entfernt alles außer deinem Vault.",
            faq_title: "Fragen",
            q_privacy: "Verlässt mein Code den Rechner?", a_privacy: "Nein. Karten, Notizen und Index bleiben auf deinem Rechner. Code Hub ergänzt nur kurzen Kontext zu dem, was Claude Code ohnehin sendet. Beim Freischalten von Premium geht der Lizenzschlüssel einmal und dann alle 14 Tage an den Shop.",
            q_tokens: "Wie viele Tokens spart das?", a_tokens: "Das hängt von deinen Projekten ab – eine Zahl versprechen wir lieber nicht. Premium enthält codehub bench: Es stellt Claude dieselben Fragen mit und ohne Code Hub an deinem eigenen Code und zeigt den Unterschied.",
            q_systems: "Welche Systeme?", a_systems: "macOS, Windows und Linux mit Python 3.9 oder neuer und Claude Code. Sonst nichts.",
            q_license: "Wie funktioniert die Premium-Lizenz?", a_license: "Einmal zahlen, kein Abo. Der Schlüssel schaltet Premium auf bis zu drei deiner Rechner frei; auf einem abmelden, um ihn auf einen anderen zu bringen (codehub premium remove).",
            q_refund: "Erstattung?", a_refund: "Gekauft wird über Lemon Squeezy oder Gumroad; deren Erstattungsregeln und deine Rechte als Verbraucher gelten. Ein erstatteter Schlüssel funktioniert danach nicht mehr.",
            q_obsidian: "Brauche ich Obsidian?", a_obsidian: "Nein. Der Vault ist einfaches Markdown – Obsidian ist eine schöne Art, ihn zu lesen, aber keine Pflicht.",
            q_remove: "Wie entferne ich es?", a_remove: "codehub uninstall nimmt Hooks, MCP-Server und Regelblock heraus. Dein Vault bleibt, wo er ist.",
            not_anthropic: "Unabhängiges Projekt, nicht mit Anthropic verbunden. Claude ist eine Marke von Anthropic.",
            imprint: "Impressum", privacy: "Datenschutz",
        },
    };
    const COMMANDS = {
        unix: "curl -fsSL https://raw.githubusercontent.com/UltraAlex2011/codehub-memory/main/scripts/install.sh | sh",
        win: "irm https://raw.githubusercontent.com/UltraAlex2011/codehub-memory/main/scripts/install.ps1 | iex",
        pipx: "pipx install git+https://github.com/UltraAlex2011/codehub-memory",
    };
    const store = { get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
                    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private window */ } } };
    let lang = store.get("codehub.site.lang") || ((navigator.language || "en").startsWith("de") ? "de" : "en");
    let os = /Windows/.test(navigator.userAgent) ? "win" : "unix";
    let shop = null;
    const t = (k, v) => (T[lang][k] || T.en[k] || k).replace(/\{(\w+)\}/g, (m, x) => (v || {})[x] ?? m);

    function texts() {
        document.documentElement.lang = lang;
        document.getElementById("lang").textContent = lang === "de" ? "EN" : "DE";
        for (const el of document.querySelectorAll("[data-t]")) el.textContent = t(el.dataset.t);
        document.title = lang === "de" ? "Code Hub – Gedächtnis für Claude Code" : "Code Hub – memory for Claude Code";
        command();
        buy();
    }

    function command() {
        document.getElementById("command").textContent = COMMANDS[os];
        document.getElementById("commandHint").textContent = t("hint_" + os);
        for (const b of document.querySelectorAll("[data-os]")) b.setAttribute("aria-selected", String(b.dataset.os === os));
    }

    function buy() {
        const box = document.getElementById("buy");
        if (!shop) return;
        document.getElementById("price").textContent = shop.price;
        const links = [["Lemon Squeezy", shop.lemonsqueezy && shop.lemonsqueezy.checkout], ["Gumroad", shop.gumroad && shop.gumroad.url]]
            .filter(([, url]) => url);
        box.innerHTML = "";
        for (const [name, url] of links) {
            const a = document.createElement("a");
            a.className = "btn primary";
            a.href = url;
            a.rel = "noopener";
            a.textContent = t("buy_at", { shop: name });
            box.appendChild(a);
        }
        if (!links.length) {
            const p = document.createElement("p");
            p.className = "fine";
            p.textContent = t("soon");
            box.appendChild(p);
        }
        const legal = document.getElementById("legal");
        legal.innerHTML = "";
        for (const [key, url] of [["imprint", shop.imprint], ["privacy", shop.privacy]]) {
            if (!url) continue;
            const a = document.createElement("a");
            a.href = url;
            a.textContent = t(key);
            legal.appendChild(a);
            legal.append(" ");
        }
    }

    document.getElementById("lang").onclick = () => { lang = lang === "de" ? "en" : "de"; store.set("codehub.site.lang", lang); texts(); };
    for (const b of document.querySelectorAll("[data-os]")) b.onclick = () => { os = b.dataset.os; command(); };
    document.getElementById("copy").onclick = async e => {
        try { await navigator.clipboard.writeText(COMMANDS[os]); } catch (err) { return; }
        e.target.textContent = t("copied");
        setTimeout(() => { e.target.textContent = t("copy"); }, 1600);
    };
    fetch("shop.json").then(r => r.json()).then(d => { shop = d; buy(); }).catch(() => {});
    texts();

    // ---- the living graph: example projects, Claude "reading" and "writing" ----
    const canvas = document.getElementById("hero");
    const ctx = canvas.getContext("2d");
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    let seed = 7;
    const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
    const nodes = [], edges = [];
    const add = (kind, name, parent, strength, length) => {
        nodes.push({ kind, name });
        if (parent >= 0) edges.push([parent, nodes.length - 1, strength, length]);
        return nodes.length - 1;
    };
    const projects = [["web-shop", ["Checkout", "Catalog", "Accounts", "Search", "Emails"]],
                      ["mobile-app", ["Onboarding", "Sync", "Settings", "Push"]],
                      ["api", ["Auth", "Orders", "Billing", "Rate limits", "Webhooks"]],
                      ["design-system", ["Buttons", "Tokens", "Forms"]]];
    const files = [];
    for (const [name, topics] of projects) {
        const p = add("p", name, -1);
        for (const topic of topics) {
            const tp = add("t", topic, p, 1, 85);
            const n = 3 + Math.floor(rnd() * 6);
            for (let i = 0; i < n; i++) files.push(add("d", "", tp, 1, 24));
            if (rnd() < 0.45) add("n", "", tp, 0.5, 50);
        }
        let prev = -1;
        for (let i = 0; i < 4; i++) {
            const s = add("s", "", p, 0.4, 95);
            if (prev >= 0) edges.push([prev, s, 0.6, 30]);
            prev = s;
        }
    }
    Forces.load({ nodes: nodes.map(n => ({ kind: n.kind })), edges, alpha: 1 });
    for (let i = 0; i < 300; i++) Forces.steps(1);        // settled before the first frame
    // size of the graph without outliers, so it always fits its place
    const start = Forces.positions(), spread = [];
    for (let i = 0; i < nodes.length; i++) spread.push(Math.hypot(start[i * 3], start[i * 3 + 1], start[i * 3 + 2]));
    spread.sort((a, b) => a - b);
    const reach = Math.max(1, spread[Math.floor(spread.length * 0.92)]);
    const RADIUS = { p: 9, t: 5.5, d: 2.4, n: 4, s: 3.2 };
    const glow = new Map();
    let yaw = 0.6, last = performance.now(), visible = true, nextGlow = 0, w = 1, h = 1, dpr = 1;

    function size() {
        dpr = Math.min(window.devicePixelRatio || 1, 2);
        const r = canvas.getBoundingClientRect();
        w = canvas.width = Math.max(1, Math.round(r.width * dpr));
        h = canvas.height = Math.max(1, Math.round(r.height * dpr));
    }

    function draw(now) {
        const dt = Math.min((now - last) / 1000, 0.1);
        last = now;
        if (!reduced) yaw += dt * 0.07;
        if (!reduced && now > nextGlow) {
            // Claude reads (blue) or writes (green) a file now and then
            glow.set(files[Math.floor(Math.random() * files.length)], { start: now, write: Math.random() < 0.35 });
            nextGlow = now + 700 + Math.random() * 900;
        }
        const pos = Forces.positions();
        const cg = Math.cos(yaw), sg = Math.sin(yaw), cn = Math.cos(0.32), sn = Math.sin(0.32);
        const wide = w > 900 * dpr;
        const scale = (wide ? Math.min(h, w * 0.5) : Math.min(w, h)) * 0.44 / reach;
        const cx = w * (wide ? 0.7 : 0.5), cy = h * 0.5;
        const pts = nodes.map((n, i) => {
            const x = pos[i * 3], y = pos[i * 3 + 1], z = pos[i * 3 + 2];
            const x1 = x * cg - z * sg, z1 = x * sg + z * cg;
            const y1 = y * cn - z1 * sn, depth = y * sn + z1 * cn;
            const f = scale * 3200 / (3200 + depth);
            return [cx + x1 * f, cy - y1 * f, depth, f];
        });
        ctx.clearRect(0, 0, w, h);
        ctx.lineWidth = dpr * 0.8;
        for (const [a, b, s] of edges) {
            const fog = Math.max(0.25, 1 - (pts[a][2] + pts[b][2] + 700) / 1800);
            ctx.strokeStyle = `rgba(124, 198, 165, ${(s < 0.5 ? 0.12 : 0.22) * fog})`;
            ctx.beginPath();
            ctx.moveTo(pts[a][0], pts[a][1]);
            ctx.lineTo(pts[b][0], pts[b][1]);
            ctx.stroke();
        }
        const colors = { p: "124,198,165", t: "185,163,227", d: "154,164,173", n: "217,201,154", s: "126,138,150" };
        const order = nodes.map((_, i) => i).sort((a, b) => pts[b][2] - pts[a][2]);
        for (const i of order) {
            const [x, y, depth, f] = pts[i];
            const r = RADIUS[nodes[i].kind] * f;
            const fog = Math.max(0.3, 1 - (depth + 600) / 1700);
            const g = glow.get(i);
            if (g) {
                const age = (now - g.start) / 1000;
                if (age > 2.6) glow.delete(i);
                else {
                    const c = g.write ? "124,198,165" : "127,180,230", k = 1 - age / 2.6;
                    const halo = ctx.createRadialGradient(x, y, 0, x, y, r * 9);
                    halo.addColorStop(0, `rgba(${c}, ${0.55 * k})`);
                    halo.addColorStop(1, `rgba(${c}, 0)`);
                    ctx.fillStyle = halo;
                    ctx.beginPath(); ctx.arc(x, y, r * 9, 0, Math.PI * 2); ctx.fill();
                    ctx.strokeStyle = `rgba(${c}, ${0.7 * k})`;
                    ctx.lineWidth = 1.2 * dpr;
                    ctx.beginPath(); ctx.arc(x, y, r * (1.5 + age * 5), 0, Math.PI * 2); ctx.stroke();
                }
            }
            ctx.fillStyle = `rgba(${colors[nodes[i].kind]}, ${fog})`;
            ctx.beginPath(); ctx.arc(x, y, Math.max(1, r), 0, Math.PI * 2); ctx.fill();
            if (nodes[i].kind === "p" || (nodes[i].kind === "t" && depth < -150)) {
                ctx.font = `${nodes[i].kind === "p" ? 600 : 500} ${Math.round((nodes[i].kind === "p" ? 14 : 12) * dpr)}px system-ui, sans-serif`;
                ctx.fillStyle = nodes[i].kind === "p" ? `rgba(124,198,165,${fog})` : `rgba(154,164,173,${fog})`;
                ctx.fillText(nodes[i].name, x + r + 6 * dpr, y + 4 * dpr);
            }
        }
        if (visible && !reduced && !document.hidden) requestAnimationFrame(draw);
    }

    size();
    window.addEventListener("resize", () => { size(); if (reduced) draw(performance.now()); });
    new IntersectionObserver(entries => {
        const was = visible;
        visible = entries[0].isIntersecting;
        if (visible && !was && !reduced) { last = performance.now(); requestAnimationFrame(draw); }
    }).observe(canvas);
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden && visible && !reduced) { last = performance.now(); requestAnimationFrame(draw); }
    });
    draw(performance.now());
})();
