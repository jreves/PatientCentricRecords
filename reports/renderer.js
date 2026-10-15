// Generic swim-lane timeline renderer (inline SVG). One config per chart; see build.py.
// Layout is computed first (marker stacking rows, bar rows, label rows/sides), then each lane grows to fit.
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const T = s => new Date(s + "T00:00:00").getTime();
  const DAY = 864e5;
  const fmt = s => { const d = new Date(s + "T00:00:00"); return `${d.getMonth() + 1}/${d.getDate()}/${d.getFullYear()}`; };
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const canvas = document.createElement("canvas").getContext("2d");
  const textW = (s, size) => { canvas.font = `${size}px system-ui, -apple-system, "Segoe UI", sans-serif`; return canvas.measureText(s).width * 1.1; };
  const MROW = 19, LROW = 14;

  function tipLayer() {
    let tip = document.getElementById("tl-tip");
    if (!tip) { tip = document.createElement("div"); tip.id = "tl-tip"; tip.className = "tip"; tip.setAttribute("role", "tooltip"); document.querySelector(".viz-root").appendChild(tip); }
    const move = ev => { const pad = 14, r = tip.getBoundingClientRect(); let x = ev.clientX + pad, y = ev.clientY + pad;
      if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - pad; if (y + r.height > innerHeight - 8) y = ev.clientY - r.height - pad;
      tip.style.left = x + "px"; tip.style.top = y + "px"; };
    return { show: (html, ev) => { tip.innerHTML = html; tip.style.display = "block"; move(ev); }, move, hide: () => { tip.style.display = "none"; } };
  }
  const overlaps = (boxes, a, c) => boxes.some(([p, q]) => !(c < p - 6 || a > q + 6));

  function render(host, cfg, rangeKey, opts = {}) {
    const css = v => getComputedStyle(host.closest(".viz-root") || document.body).getPropertyValue(v).trim();
    const tip = tipLayer();
    const W = opts.width || Math.max(760, host.clientWidth), L = cfg.labelWidth || 196, R = 22, plotW = W - L - R;
    const [d0, d1] = cfg.ranges[rangeKey].slice(0, 2).map(T);
    const x = s => L + (T(s) - d0) / (d1 - d0) * plotW;
    const inRange = s => T(s) >= d0 && T(s) <= d1;
    const laneOf = id => cfg.lanes.find(l => l.id === id);

    // Static (print) mode: every visible marker is numbered in date order and explained in a key under the chart.
    const num = new Map(), ann = opts.annotate;
    if (ann) {
      const order = cfg.lanes.map(l => l.id);
      cfg.markers.filter(m => inRange(m.date) && laneOf(m.lane) && !(ann.until && T(m.date) >= T(ann.until)))
        .sort((a, b) => T(a.date) - T(b.date) || order.indexOf(a.lane) - order.indexOf(b.lane))
        .forEach((m, i) => num.set(m, String(i + 1)));
    }
    const labelOf = m => ann ? num.get(m) : m.label;

    // ---- layout pass ----------------------------------------------------------------------------------------
    const mPlace = new Map(), maxMRow = {};
    for (const m of cfg.markers) {
      if (!inRange(m.date) || !laneOf(m.lane)) continue;
      const xx = x(m.date), P = (mPlace[m.lane] = mPlace[m.lane] || []);
      const gap = labelOf(m) ? 22 + textW(String(labelOf(m)), 11) : 17;
      let row = m.row || 0; while (P.some(p => p.row === row && Math.abs(p.x - xx) < Math.max(gap, p.gap))) row++;
      P.push({ x: xx, row, gap }); mPlace.set(m, row); maxMRow[m.lane] = Math.max(maxMRow[m.lane] ?? -1, row);
    }
    const bLayout = new Map(), aboveRows = {}, sideBoxes = {}, maxBRow = {};
    for (const b of cfg.bars) {
      const lane = laneOf(b.lane); if (!lane) continue;
      maxBRow[b.lane] = Math.max(maxBRow[b.lane] ?? -1, b.row || 0);
      const xs = x(b.start), xe = x(b.end);
      if (b.nolabel || xe < L || xs > L + plotW) { bLayout.set(b, null); continue; }
      if (lane.labels === "above") {
        const rows = (aboveRows[b.lane] = aboveRows[b.lane] || [[], [], []]);
        let chosen = null;
        for (const text of [b.label, b.short].filter(Boolean)) {
          const lw = textW(text, 12), lx = Math.min(Math.max(L + 2, xs), L + plotW - lw - 4);
          const row = rows.findIndex(rw => !overlaps(rw, lx, lx + lw));
          if (row >= 0) { rows[row].push([lx, lx + lw]); chosen = { text, lx, row, anchor: "start" }; break; }
        }
        bLayout.set(b, chosen);   // null: no room — the tooltip still names it
      } else {
        const key = b.lane + ":" + (b.row || 0), boxes = (sideBoxes[key] = sideBoxes[key] || []);
        const barH = lane.barH || 12, lw = textW(b.label, 12);
        const cands = [{ lx: xe + (b.continues ? 32 : b.ongoing ? 14 : 6), anchor: "start", a: xe + (b.continues ? 32 : b.ongoing ? 14 : 6), c: xe + (b.continues ? 32 : b.ongoing ? 14 : 6) + lw },
                       { lx: xs - 6, anchor: "end", a: xs - 6 - lw, c: xs - 6 }];
        const ok = cands.find(k => k.a >= L && k.c <= L + plotW - 2 && !overlaps(boxes, k.a, k.c)
                                && !cfg.bars.some(o => o !== b && o.lane === b.lane && (o.row || 0) === (b.row || 0) && !(x(o.end) < k.a - 2 || x(o.start) > k.c + 2)));
        const v0 = Math.max(xs, L), v1 = Math.min(xe, L + plotW);
        if (ok) { boxes.push([ok.a, ok.c]); bLayout.set(b, { text: b.label, lx: ok.lx, anchor: ok.anchor, row: 0 }); }
        else if (v1 - v0 >= textW(b.label, 10.5) + 12) bLayout.set(b, { text: b.label, lx: v0 + 6, anchor: "start", row: 0, inside: true });
        else bLayout.set(b, null);   // no room: the tooltip still names it
      }
    }
    const H_ = {};
    for (const l of cfg.lanes) {
      const barH = l.barH || 12;
      let need = l.h;
      if (l.labels === "above") { const used = (aboveRows[l.id] || []).filter(r => r.length).length; need = Math.max(need, used * LROW + barH + 16); }
      else if (maxBRow[l.id] >= 0) need = Math.max(need, 7 + (maxBRow[l.id] + 1) * (barH + 6) + 2);
      if (maxMRow[l.id] >= 0) need = Math.max(need, (l.markerTop || 14) + maxMRow[l.id] * MROW + 14);
      H_[l.id] = need;
    }
    let y = 8; const laneY = {};
    for (const l of cfg.lanes) { laneY[l.id] = y; y += H_[l.id]; }
    const lanesBottom = y;
    const line = cfg.line, lineTop = y + 26, lineH = line ? 150 : 0, lineBottom = line ? lineTop + lineH : lanesBottom;
    const H = lineBottom + 44;

    // ---- draw ---------------------------------------------------------------------------------------------------
    host.innerHTML = "";
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("width", W); svg.setAttribute("height", H); svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("role", "img"); svg.setAttribute("aria-label", cfg.aria || "Timeline; the tables below list the same data.");
    host.appendChild(svg);
    const el = (tag, attrs, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); (parent || svg).appendChild(e); return e; };
    const tipOn = (e, html) => { e.addEventListener("mouseenter", ev => tip.show(html, ev)); e.addEventListener("mousemove", tip.move); e.addEventListener("mouseleave", tip.hide); };
    const defs = el("defs", {}); const cp = el("clipPath", { id: "plot-" + cfg.id }, defs); el("rect", { x: L, y: 0, width: plotW, height: H }, cp);

    const spanYears = (d1 - d0) / (365.25 * DAY);
    const months = spanYears > 9 ? null : spanYears > 2.5 ? [0] : spanYears > 1.2 ? [0, 3, 6, 9] : [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];
    const yearStep = spanYears > 14 ? 2 : 1;
    const MN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    for (let yr = new Date(d0).getFullYear(); yr <= new Date(d1).getFullYear() + 1; yr++) {
      for (const m of (months || (yr % yearStep === 0 ? [0] : []))) {
        const s = `${yr}-${String(m + 1).padStart(2, "0")}-01`; if (!inRange(s)) continue;
        el("line", { x1: x(s), x2: x(s), y1: 4, y2: lineBottom, stroke: css("--grid"), "stroke-width": m === 0 ? 1 : 0.6 });
        const t = el("text", { x: x(s), y: lineBottom + 16, "text-anchor": "middle", "font-size": 11.5, fill: css("--text-secondary") });
        t.textContent = m === 0 ? yr : MN[m];
      }
    }
    for (const l of cfg.lanes) {
      const words = l.label.split("\n");
      words.forEach((w, i) => { const t = el("text", { x: L - 12, y: laneY[l.id] + H_[l.id] / 2 + 4 + (i - (words.length - 1) / 2) * 14, "text-anchor": "end", "font-size": 12.5, fill: css("--text-secondary") }); t.textContent = w; });
      el("line", { x1: L, x2: L + plotW, y1: laneY[l.id] + H_[l.id], y2: laneY[l.id] + H_[l.id], stroke: css("--grid") });
    }
    const g = el("g", { "clip-path": `url(#plot-${cfg.id})` });
    if (cfg.today && inRange(cfg.today)) {
      el("line", { x1: x(cfg.today), x2: x(cfg.today), y1: 4, y2: lineBottom, stroke: css("--text-muted"), "stroke-width": 1.2 }, g);
      const tt = el("text", { x: x(cfg.today) + 3, y: lineBottom + 30, "text-anchor": "end", "font-size": 11, fill: css("--text-muted") }, g); tt.textContent = `today ${fmt(cfg.today)}`;
    }
    for (const gd of cfg.guides || []) if (inRange(gd.date))
      el("line", { x1: x(gd.date), x2: x(gd.date), y1: 4, y2: lineBottom, stroke: css("--guide"), "stroke-width": 1, "stroke-dasharray": "3 3" }, g);

    for (const b of cfg.bars) {
      const lane = laneOf(b.lane); if (!lane) continue;
      const color = css(cfg.cls[b.cls] || "--text-muted"), top = laneY[b.lane], barH = lane.barH || 12;
      const by = lane.labels === "above" ? top + H_[b.lane] - barH - 8 : top + 7 + (b.row || 0) * (barH + 6);
      const xs = x(b.start), xe = x(b.end), w = Math.max(3, xe - xs);
      let segs = [[xs, xs + w]];
      const holds = (b.holds || []).map(h => [x(h[0]), x(h[1]), h[2], h[0], h[1]]);
      for (const [hs, he] of holds) segs = segs.flatMap(([a, c]) => (he <= a || hs >= c) ? [[a, c]] : [[a, hs], [he, c]].filter(([p, q]) => q - p > 0.5));
      for (const [a, c] of segs) el("rect", { x: a, y: by, width: Math.max(2, c - a - (segs.length > 1 ? 1 : 0)), height: barH, rx: 4, fill: color, opacity: b.faint ? 0.45 : 1 }, g);
      for (const [hs, he, why, h0, h1] of holds) {
        const r = el("rect", { x: hs + 1, y: by + 1, width: Math.max(2, he - hs - 2), height: barH - 2, rx: 3, fill: "none", stroke: color, "stroke-width": 1.5, "stroke-dasharray": "3 2" }, g);
        tipOn(r, `<b>${esc(b.label)}: held</b><span class="when">${fmt(h0)} – ${fmt(h1)}</span><br>${esc(why)}${b.holdCtx ? `<br><span class="when">${esc(b.holdCtx)}</span>` : ""}`);
      }
      if (b.ongoing) el("path", { d: `M${xe + 3},${by} l7,${barH / 2} l-7,${barH / 2} z`, fill: color }, g);
      if (b.continues) el("line", { x1: xe + 2, x2: xe + 26, y1: by + barH / 2, y2: by + barH / 2, stroke: color, "stroke-width": 2, "stroke-dasharray": "2 4" }, g);
      const hit = el("rect", { x: xs - 4, y: by - 4, width: w + 8 + (b.continues ? 24 : 0), height: barH + 8, fill: "transparent" }, g);
      const when = `${b.startApprox ? "~" : ""}${fmt(b.start)} – ${b.endApprox ? "~" : ""}${fmt(b.end)}${b.ongoing ? " (ongoing)" : ""}`;
      tipOn(hit, `<b>${esc(b.label || b.title || "")}</b><span class="when">${when}</span>${b.note ? "<br>" + esc(b.note) : ""}${b.ctx ? `<br><span class="when">${esc(b.ctx)}</span>` : ""}`);
      const lab = bLayout.get(b); if (!lab) continue;
      const ly = lane.labels === "above" ? by - 5 - lab.row * LROW : by + barH - 1;
      const t = lab.inside   // on the bar itself: surface-coloured ink, the bar's colour carries identity
        ? el("text", { x: lab.lx, y: by + barH - 2.5, "font-size": 10.5, "font-weight": 600, fill: css("--surface-1"), "text-anchor": "start", "pointer-events": "none" }, g)
        : el("text", { x: lab.lx, y: ly, "font-size": 12, fill: css("--text-primary"), "text-anchor": lab.anchor }, g);
      t.textContent = lab.text;
    }

    const ink = css("--text-primary"), surf = css("--surface-1");
    for (const m of cfg.markers) {
      if (!mPlace.has(m)) continue;
      const lane = laneOf(m.lane), row = mPlace.get(m), xx = x(m.date);
      const cy = laneY[m.lane] + (lane.markerTop || 14) + row * MROW, s = 6.5;
      const color = m.cls ? css(cfg.cls[m.cls]) : ink, shape = m.shape || "diamond";
      if (shape === "diamond") el("path", { d: `M${xx},${cy - s} L${xx + s},${cy} L${xx},${cy + s} L${xx - s},${cy} Z`, fill: color, stroke: surf, "stroke-width": 2 }, g);
      else if (shape === "diamond-open") el("path", { d: `M${xx},${cy - s} L${xx + s},${cy} L${xx},${cy + s} L${xx - s},${cy} Z`, fill: surf, stroke: color, "stroke-width": 2 }, g);
      else if (shape === "circle") el("circle", { cx: xx, cy, r: 5.5, fill: color, stroke: surf, "stroke-width": 2 }, g);
      else if (shape === "circle-open") el("circle", { cx: xx, cy, r: 5.5, fill: surf, stroke: color, "stroke-width": 2 }, g);
      else if (shape === "square") el("rect", { x: xx - 5.5, y: cy - 5.5, width: 11, height: 11, rx: 2, fill: color, stroke: surf, "stroke-width": 2 }, g);
      else if (shape === "tri-up") el("path", { d: `M${xx},${cy - 7} L${xx + 7},${cy + 5} L${xx - 7},${cy + 5} Z`, fill: color, stroke: surf, "stroke-width": 1.5 }, g);
      else if (shape === "tri-down") el("path", { d: `M${xx},${cy + 7} L${xx + 7},${cy - 5} L${xx - 7},${cy - 5} Z`, fill: surf, stroke: color, "stroke-width": 2 }, g);
      else if (shape === "bang") { el("circle", { cx: xx, cy, r: 7.5, fill: surf, stroke: color, "stroke-width": 1.5 }, g);
        const t = el("text", { x: xx, y: cy + 4, "text-anchor": "middle", "font-size": 11, "font-weight": 700, fill: color }, g); t.textContent = "!"; }
      const lab = labelOf(m);
      if (lab) { const t = el("text", { x: xx + 10, y: cy + 4, "font-size": 11, "font-weight": ann ? 700 : 400, fill: css(ann ? "--text-primary" : "--text-secondary") }, g); t.textContent = lab; }
      const hit = el("rect", { x: xx - 11, y: cy - 11, width: 22 + (lab ? textW(String(lab), 11) + 4 : 0), height: 22, fill: "transparent" }, g);
      tipOn(hit, `<b>${esc(m.title || "")}</b><span class="when">${m.approx ? "~" : ""}${fmt(m.date)}</span>${m.text ? "<br>" + esc(m.text) : ""}${m.ctx ? `<br><span class="when">${esc(m.ctx)}</span>` : ""}`);
    }

    if (line) {
      const vis = line.points.filter(([d]) => inRange(d)), vmax = Math.max(line.uln * 1.25, ...vis.map(p => p[1])) * 1.08;
      const yv = v => lineBottom - v / vmax * lineH;
      const t0 = el("text", { x: L - 12, y: lineTop + 14, "text-anchor": "end", "font-size": 12.5, fill: css("--text-secondary") }); t0.textContent = line.title;
      const step = vmax > 120 ? 50 : vmax > 60 ? 20 : 10;
      for (let v = 0; v <= vmax; v += step) {
        el("line", { x1: L, x2: L + plotW, y1: yv(v), y2: yv(v), stroke: css("--grid"), "stroke-width": v === 0 ? 1 : 0.6 });
        const t = el("text", { x: L - 6, y: yv(v) + 4, "text-anchor": "end", "font-size": 11, fill: css("--text-muted") }); t.textContent = v;
      }
      el("line", { x1: L, x2: L + plotW, y1: yv(line.uln), y2: yv(line.uln), stroke: css("--text-muted"), "stroke-dasharray": "5 4" }, g);
      const ul = el("text", { x: L - 6, y: yv(line.uln) + 4, "text-anchor": "end", "font-size": 11, fill: css("--text-muted") }); ul.textContent = `ULN ${line.uln}`;
      const pts = line.points.map(([d, v, ctx]) => [x(d), yv(v), d, v, ctx]);
      el("path", { d: pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(""), fill: "none", stroke: ink, "stroke-width": 2, "stroke-linejoin": "round" }, g);
      for (const p of pts) el("circle", { cx: p[0], cy: p[1], r: 2.2, fill: ink }, g);
      const cross = el("line", { y1: lineTop, y2: lineBottom, stroke: css("--guide"), visibility: "hidden" }, g);
      const dot = el("circle", { r: 5, fill: ink, stroke: surf, "stroke-width": 2, visibility: "hidden" }, g);
      const ov = el("rect", { x: L, y: lineTop, width: plotW, height: lineH, fill: "transparent" });
      ov.addEventListener("mousemove", ev => {
        const mx = ev.clientX - svg.getBoundingClientRect().left; let best = null;
        for (const p of pts) if (p[0] >= L && p[0] <= L + plotW && (!best || Math.abs(p[0] - mx) < Math.abs(best[0] - mx))) best = p;
        if (!best) return; const i = pts.indexOf(best), prev = pts[i - 1];
        cross.setAttribute("x1", best[0]); cross.setAttribute("x2", best[0]); cross.setAttribute("visibility", "visible");
        dot.setAttribute("cx", best[0]); dot.setAttribute("cy", best[1]); dot.setAttribute("visibility", "visible");
        const chg = prev ? `<br>${best[3] > prev[3] ? "↑ +" : best[3] < prev[3] ? "↓ " : "→ "}${(best[3] - prev[3]).toFixed(1)} since ${fmt(prev[2])} (${prev[3]})` : "";
        tip.show(`<b>${esc(line.label)}: ${best[3]} ${esc(line.unit)}</b><span class="when">${fmt(best[2])}${best[3] > line.uln ? " · above normal" : ""}</span>${chg}${best[4] ? "<br>On: " + esc(best[4]) : ""}`, ev);
      });
      ov.addEventListener("mouseleave", () => { cross.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); tip.hide(); });
      if (ann) {   // print: write the first, highest and latest values on the line
        const shown = pts.filter(p => p[0] >= L && p[0] <= L + plotW);
        if (shown.length) {
          const pick = [shown[0], shown.reduce((a, b) => (b[3] > a[3] ? b : a)), shown[shown.length - 1]];
          [...new Set(pick)].forEach(p => {
            el("circle", { cx: p[0], cy: p[1], r: 3.5, fill: ink, stroke: surf, "stroke-width": 1.5 }, g);
            const right = p[0] < L + plotW - 120;
            const t = el("text", { x: p[0] + (right ? 7 : -7), y: Math.max(lineTop + 10, p[1] - 6), "text-anchor": right ? "start" : "end",
                                   "font-size": 11, "font-weight": 600, fill: ink, stroke: surf, "stroke-width": 3, "paint-order": "stroke" }, g);
            t.textContent = `${p[3]} (${fmt(p[2])})`;
          });
        }
      }
    }
    if (ann && opts.keyHost) writeKey(document.getElementById(opts.keyHost), cfg, num, inRange, laneOf, ann);
  }

  // Print key: numbered events, then the bars (treatments, drops, stays) with their dates and notes.
  function writeKey(host, cfg, num, inRange, laneOf, ann) {
    const when = m => `${m.approx ? "~" : ""}${fmt(m.date)}`;
    const ms = [...num.entries()].sort((a, b) => a[1] - b[1]);
    let h = `<table class="key"><thead><tr><th>#</th><th>Date</th><th>Row</th><th>Event</th></tr></thead><tbody>`;
    for (const [m, n] of ms) {
      const lane = laneOf(m.lane).label.replace(/\n/g, " ");
      h += `<tr><td class="num">${n}</td><td class="n">${when(m)}</td><td class="n">${esc(lane)}</td><td><b>${esc(m.title || "")}</b>` +
           `${m.text ? " " + esc(m.text) : ""}${m.ctx ? `<br><span class="ctx">${esc(m.ctx)}</span>` : ""}</td></tr>`;
    }
    h += "</tbody></table>";
    const skip = new Set(ann.skipLanes || []);
    const bars = cfg.bars.filter(b => laneOf(b.lane) && !skip.has(b.lane) && (b.note || b.label) && !(ann.until && T(b.start) >= T(ann.until)) && !(T(b.end) < T(cfg.ranges[ann.range][0]) || T(b.start) > T(cfg.ranges[ann.range][1])));
    if (bars.length) {
      h += `<h3>${esc(ann.barsTitle || "Bars in the chart")}</h3><table class="key"><thead><tr><th>Row</th><th>Item</th><th>Dates</th><th>Notes</th></tr></thead><tbody>`;
      for (const b of bars) {
        const dates = `${b.startApprox ? "~" : ""}${fmt(b.start)} – ${b.ongoing ? "ongoing" : (b.endApprox ? "~" : "") + fmt(b.end)}`;
        const holds = (b.holds || []).map(x => ` Held ${fmt(x[0])} – ${fmt(x[1])}: ${x[2]}.`).join("");
        h += `<tr><td class="n">${esc(laneOf(b.lane).label.replace(/\n/g, " "))}</td><td><span class="key-sw" style="background:var(${cfg.cls[b.cls] || "--text-muted"})"></span>${esc(b.label || "Hospital stay")}</td>` +
             `<td class="n">${dates}</td><td>${esc(b.note || "")}${esc(holds)}${b.ctx ? `<br><span class="ctx">${esc(b.ctx)}</span>` : ""}</td></tr>`;
      }
      h += "</tbody></table>";
    }
    host.innerHTML = h;
  }

  function mount(cfg, hostId, opts = {}) {
    const host = document.getElementById(hostId); let range = cfg.defaultRange;
    const draw = () => render(host, cfg, range, opts);
    document.querySelectorAll(`[data-chart="${cfg.id}"] [data-range]`).forEach(b => b.addEventListener("click", () => {
      range = b.dataset.range; document.querySelectorAll(`[data-chart="${cfg.id}"] [data-range]`).forEach(o => o.setAttribute("aria-pressed", String(o === b))); draw();
    }));
    if (!opts.width) addEventListener("resize", draw);
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", draw);
    draw();
  }
  window.Timeline = { mount };
})();
