// Small Markdown renderer for notes and session logs: headings, paragraphs,
// lists, code, quotes, tables, emphasis and links. Everything is escaped
// first - a note can never inject markup. Links: hub:<id> jumps to a node,
// http(s) opens a new tab, anything else stays text.
const Markdown = (() => {
    const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

    function inline(text) {
        const codes = [];
        let s = esc(text).replace(/`([^`]+)`/g, (_, c) => { codes.push(c); return `\u0000${codes.length - 1}\u0000`; });
        s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, label, url) => {
            if (url.startsWith("hub:")) return `<a href="#" data-hub="${url.slice(4)}">${label}</a>`;
            if (/^https?:\/\//.test(url)) return `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`;
            return label;
        });
        s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
             .replace(/(^|[^*\w])\*([^*\s][^*]*)\*(?!\w)/g, '$1<em class="dead">$2</em>')
             .replace(/(^|\W)_([^_\s][^_]*)_(?!\w)/g, "$1<em>$2</em>");
        return s.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${codes[Number(i)]}</code>`);
    }

    function table(rows) {
        const cells = r => r.replace(/^\||\|$/g, "").split("|").map(c => inline(c.trim()));
        const head = cells(rows[0]);
        const body = rows.slice(2).map(cells);
        return "<table><thead><tr>" + head.map(c => `<th>${c}</th>`).join("") + "</tr></thead><tbody>"
            + body.map(r => "<tr>" + r.map(c => `<td>${c}</td>`).join("") + "</tr>").join("") + "</tbody></table>";
    }

    function render(source) {
        const lines = String(source || "").replace(/\r/g, "").split("\n");
        const out = [];
        let i = 0;
        while (i < lines.length) {
            const line = lines[i];
            if (/^```/.test(line)) {
                const code = [];
                i++;
                while (i < lines.length && !/^```/.test(lines[i])) code.push(lines[i++]);
                i++;
                out.push(`<pre><code>${esc(code.join("\n"))}</code></pre>`);
                continue;
            }
            const h = /^(#{1,6})\s+(.*)$/.exec(line);
            if (h) { out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`); i++; continue; }
            if (/^\s*(---|\*\*\*)\s*$/.test(line)) { out.push("<hr>"); i++; continue; }
            if (/^\|/.test(line) && i + 1 < lines.length && /^\|?\s*:?-{2,}/.test(lines[i + 1])) {
                const rows = [];
                while (i < lines.length && /^\|/.test(lines[i])) rows.push(lines[i++]);
                out.push(table(rows));
                continue;
            }
            if (/^>\s?/.test(line)) {
                const quote = [];
                while (i < lines.length && /^>\s?/.test(lines[i])) quote.push(lines[i++].replace(/^>\s?/, ""));
                out.push(`<blockquote>${render(quote.join("\n"))}</blockquote>`);
                continue;
            }
            const list = /^\s*([-*+]|\d+\.)\s+/.exec(line);
            if (list) {
                const ordered = /\d/.test(list[1]);
                const items = [];
                while (i < lines.length && /^\s*([-*+]|\d+\.)\s+/.test(lines[i])) {
                    let item = lines[i++].replace(/^\s*([-*+]|\d+\.)\s+/, "");
                    while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !/^\s*([-*+]|\d+\.)\s+/.test(lines[i]))
                        item += " " + lines[i++].trim();
                    items.push(`<li>${inline(item)}</li>`);
                }
                out.push(ordered ? `<ol>${items.join("")}</ol>` : `<ul>${items.join("")}</ul>`);
                continue;
            }
            if (!line.trim()) { i++; continue; }
            const para = [];
            while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|```|>|\s*([-*+]|\d+\.)\s+|\|)/.test(lines[i]))
                para.push(lines[i++]);
            out.push(`<p>${inline(para.join(" "))}</p>`);
        }
        return out.join("");
    }

    return { render, esc };
})();
