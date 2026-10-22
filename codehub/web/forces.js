// Force simulation in 3D for the Code Hub graph, shared by both views: the
// Quickshell view imports this file, the web server wraps it as a module for
// the browser (no ".pragma library" for that reason). Own rebuild of the idea
// behind d3-force-3d: repulsion of all nodes through a Barnes-Hut octree
// (O(n log n) instead of O(n^2)), springs along the edges, a light pull to the
// centre, cooling through alpha. Runs only while the graph settles, with a
// time budget per frame.
//   load({nodes: [{kind, xyz?}], edges: [[a, b, strength, length]], alpha})
//   steps(ms)     -> computes up to ms milliseconds; true = settled
//   positions()   -> [x0, y0, z0, x1, ...]
//   heat(alpha)   wakes the simulation up again
//   hold(i, xyz) / release()   a node hangs on the pointer (dragging)

const THETA2 = 0.81;            // Barnes-Hut accuracy (0.9^2)
const ALPHA_MIN = 0.004;
const ALPHA_DECAY = 1 - Math.pow(ALPHA_MIN, 1 / 260);
const FRICTION = 0.6;           // share of the velocity that stays
const CENTRE = 0.015;           // pull to the centre
const FAR2 = 1100 * 1100;       // no repulsion beyond this
const CHARGE = { p: 260, t: 70, d: 22, n: 45, s: 38 };

let n = 0, m = 0;
let x, y, z, vx, vy, vz, charge;
let source, target, length, force, bias;
let alpha = 1;
let held = -1, hx = 0, hy = 0, hz = 0;   // dragged node

// octree as a pool of flat arrays - no object per cell
let capacity = 0, cells = 0;
let cx, cy, cz, ch, sx, sy, sz, sq, children, leaf, stack;

function pool(size) {
    capacity = size;
    cx = new Float64Array(size); cy = new Float64Array(size); cz = new Float64Array(size);
    ch = new Float64Array(size);
    sx = new Float64Array(size); sy = new Float64Array(size); sz = new Float64Array(size);
    sq = new Float64Array(size);
    children = new Int32Array(size * 8);
    leaf = new Int32Array(size);            // >= 0 node, -1 empty, -2 inner
    stack = new Int32Array(size * 8 + 64);
}

function cell(x0, y0, z0, h) {
    if (cells >= capacity) {
        // rare: very uneven nodes need deeper trees
        const old = { cx, cy, cz, ch, sx, sy, sz, sq, children, leaf };
        pool(capacity * 2);
        cx.set(old.cx); cy.set(old.cy); cz.set(old.cz); ch.set(old.ch);
        sx.set(old.sx); sy.set(old.sy); sz.set(old.sz); sq.set(old.sq);
        children.set(old.children); leaf.set(old.leaf);
    }
    const i = cells++;
    cx[i] = x0; cy[i] = y0; cz[i] = z0; ch[i] = h;
    sx[i] = sy[i] = sz[i] = sq[i] = 0;
    children.fill(-1, i * 8, i * 8 + 8);
    leaf[i] = -1;
    return i;
}

function octant(i, b) {
    return (x[b] >= cx[i] ? 1 : 0) | (y[b] >= cy[i] ? 2 : 0) | (z[b] >= cz[i] ? 4 : 0);
}

function child(i, o) {
    let k = children[i * 8 + o];
    if (k < 0) {
        const h = ch[i] / 2;
        k = cell(cx[i] + (o & 1 ? h : -h), cy[i] + (o & 2 ? h : -h), cz[i] + (o & 4 ? h : -h), h);
        children[i * 8 + o] = k;
    }
    return k;
}

function add(i, b) {
    const q = charge[b];
    sq[i] += q; sx[i] += x[b] * q; sy[i] += y[b] * q; sz[i] += z[b] * q;
}

function insert(b) {
    let i = 0;
    for (;;) {
        add(i, b);
        const old = leaf[i];
        if (old === -1) { leaf[i] = b; return; }
        if (old >= 0) {
            if (ch[i] < 0.02) {
                // two nodes on the same spot: jiggle them apart instead of splitting forever
                x[b] += Math.random() - 0.5; y[b] += Math.random() - 0.5; z[b] += Math.random() - 0.5;
                return;
            }
            leaf[i] = -2;
            const k = child(i, octant(i, old));
            add(k, old);
            leaf[k] = old;
        }
        i = child(i, octant(i, b));
    }
}

function tree() {
    let x0 = Infinity, y0 = Infinity, z0 = Infinity, x1 = -Infinity, y1 = -Infinity, z1 = -Infinity;
    for (let i = 0; i < n; i++) {
        if (x[i] < x0) x0 = x[i]; if (x[i] > x1) x1 = x[i];
        if (y[i] < y0) y0 = y[i]; if (y[i] > y1) y1 = y[i];
        if (z[i] < z0) z0 = z[i]; if (z[i] > z1) z1 = z[i];
    }
    cells = 0;
    cell((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2, Math.max(x1 - x0, y1 - y0, z1 - z0) / 2 + 1);
    for (let i = 0; i < n; i++) insert(i);
}

function repel() {
    for (let b = 0; b < n; b++) {
        let fx = 0, fy = 0, fz = 0, sp = 0;
        stack[sp++] = 0;
        while (sp > 0) {
            const i = stack[--sp];
            const q = sq[i];
            if (q === 0 || leaf[i] === b) continue;
            const dx = sx[i] / q - x[b], dy = sy[i] / q - y[b], dz = sz[i] / q - z[b];
            let l = dx * dx + dy * dy + dz * dz;
            const width = 2 * ch[i];
            if (leaf[i] === -2 && width * width / THETA2 >= l) {
                const k0 = i * 8;
                for (let o = 0; o < 8; o++) {
                    const k = children[k0 + o];
                    if (k >= 0) stack[sp++] = k;
                }
                continue;
            }
            if (l > FAR2) continue;
            if (l < 1) l = Math.sqrt(l) || 1;
            const w = q * alpha / l;
            fx -= dx * w; fy -= dy * w; fz -= dz * w;
        }
        vx[b] += fx; vy[b] += fy; vz[b] += fz;
    }
}

function springs() {
    for (let e = 0; e < m; e++) {
        const s = source[e], t = target[e];
        let dx = x[t] + vx[t] - x[s] - vx[s];
        let dy = y[t] + vy[t] - y[s] - vy[s];
        let dz = z[t] + vz[t] - z[s] - vz[s];
        let l = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1e-6;
        l = (l - length[e]) / l * alpha * force[e];
        dx *= l; dy *= l; dz *= l;
        const b = bias[e];
        vx[t] -= dx * b; vy[t] -= dy * b; vz[t] -= dz * b;
        vx[s] += dx * (1 - b); vy[s] += dy * (1 - b); vz[s] += dz * (1 - b);
    }
}

function step() {
    if (n === 0) return;
    alpha += (0 - alpha) * ALPHA_DECAY;
    tree();
    repel();
    springs();
    const pull = CENTRE * alpha;
    for (let i = 0; i < n; i++) {
        vx[i] = (vx[i] - x[i] * pull) * FRICTION;
        vy[i] = (vy[i] - y[i] * pull) * FRICTION;
        vz[i] = (vz[i] - z[i] * pull) * FRICTION;
        x[i] += vx[i]; y[i] += vy[i]; z[i] += vz[i];
    }
    if (held >= 0 && held < n) {
        x[held] = hx; y[held] = hy; z[held] = hz;
        vx[held] = vy[held] = vz[held] = 0;
    }
}

function load(msg) {
    const nodes = msg.nodes || [], edges = msg.edges || [];
    n = nodes.length;
    m = edges.length;
    x = new Float64Array(n); y = new Float64Array(n); z = new Float64Array(n);
    vx = new Float64Array(n); vy = new Float64Array(n); vz = new Float64Array(n);
    charge = new Float64Array(n);
    const degree = new Int32Array(n);
    for (const e of edges) { degree[e[0]]++; degree[e[1]]++; }
    // start: the saved spot, else next to a neighbour already placed, else
    // somewhere in a sphere
    const placed = new Uint8Array(n);
    const radius = 40 * Math.cbrt(Math.max(n, 1));
    for (let i = 0; i < n; i++) {
        const k = nodes[i];
        charge[i] = (CHARGE[k.kind] || 30) * (1 + Math.min(degree[i], 40) / 40);
        if (k.xyz && k.xyz.length === 3) {
            x[i] = k.xyz[0]; y[i] = k.xyz[1]; z[i] = k.xyz[2];
            placed[i] = 1;
        }
    }
    for (let round = 0; round < 3; round++) {
        for (const e of edges) {
            const a = e[0], b = e[1];
            if (placed[a] === placed[b]) continue;
            const from = placed[a] ? a : b, fresh = placed[a] ? b : a;
            x[fresh] = x[from] + (Math.random() - 0.5) * 30;
            y[fresh] = y[from] + (Math.random() - 0.5) * 30;
            z[fresh] = z[from] + (Math.random() - 0.5) * 30;
            placed[fresh] = 1;
        }
    }
    for (let i = 0; i < n; i++) {
        if (placed[i]) continue;
        const u = Math.random() * 2 - 1, phi = Math.random() * 2 * Math.PI, r = radius * Math.cbrt(Math.random());
        const s = Math.sqrt(1 - u * u);
        x[i] = r * s * Math.cos(phi); y[i] = r * s * Math.sin(phi); z[i] = r * u;
    }
    source = new Int32Array(m); target = new Int32Array(m);
    length = new Float64Array(m); force = new Float64Array(m); bias = new Float64Array(m);
    for (let e = 0; e < m; e++) {
        const k = edges[e];
        source[e] = k[0]; target[e] = k[1];
        length[e] = k[3] || 30;
        force[e] = (k[2] || 1) / Math.max(1, Math.min(degree[k[0]], degree[k[1]]));
        bias[e] = degree[k[0]] / Math.max(1, degree[k[0]] + degree[k[1]]);
    }
    pool(Math.max(64, n * 3));
    alpha = Math.max(msg.alpha || 1, 0.05);
    held = -1;
}

function positions() {
    const pos = new Array(n * 3);
    for (let i = 0, j = 0; i < n; i++, j += 3) {
        pos[j] = x[i]; pos[j + 1] = y[i]; pos[j + 2] = z[i];
    }
    return pos;
}

function steps(ms) {
    const end = Date.now() + ms;
    do {
        if (alpha <= ALPHA_MIN) return true;
        step();
    } while (Date.now() < end);
    return alpha <= ALPHA_MIN;
}

function heat(a) {
    alpha = Math.max(alpha, a || 0.3);
}

function strength() {
    return alpha;
}

function hold(i, xyz) {
    held = i;
    hx = xyz[0]; hy = xyz[1]; hz = xyz[2];
    if (i >= 0 && i < n) {
        x[i] = hx; y[i] = hy; z[i] = hz;
    }
}

function release() {
    held = -1;
}
