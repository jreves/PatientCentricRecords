// Editable Word version of the emergency / travel medical summary. Content comes from the JSON written by emergency.py (from the
// case file's ``emergency:`` section); fill-in cells are left empty for the family to type into.
// Usage: node emergency_docx.js emergency_card.json     (needs `npm install` in reports/, which installs the docx package)
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle, AlignmentType,
  Footer, PageNumber, PageBreak, TableLayoutType, VerticalAlign,
} = require("docx");

const data = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const FONT = "Calibri";
const W = 12240 - 2 * 864;           // Letter width minus 0.6" margins, in DXA
const GRID = "BFBFBF", FILL = "F3F2EE", HOT = "C2410C", INK = "1F2937", MUTED = "6B7280";
const border = { style: BorderStyle.SINGLE, size: 4, color: GRID };
const borders = { top: border, bottom: border, left: border, right: border };

const run = (text, o = {}) => new TextRun({ text, font: FONT, size: o.size || 18, bold: o.bold, color: o.color || INK, italics: o.italics });
const para = (children, o = {}) => new Paragraph({ children: Array.isArray(children) ? children : [children], spacing: { before: o.before || 0, after: o.after ?? 60 },
  alignment: o.align, shading: o.shade ? { type: ShadingType.CLEAR, fill: o.shade, color: "auto" } : undefined, keepNext: o.keepNext });
const heading = (text) => new Paragraph({ children: [run(text, { size: 21, bold: true })], spacing: { before: 160, after: 60 }, keepNext: true,
  border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: GRID, space: 2 } } });

function cell(content, width, o = {}) {
  const kids = (Array.isArray(content) ? content : [content]).map((c) => (c instanceof Paragraph ? c : para(typeof c === "string" ? run(c, o) : c, { after: 0 })));
  return new TableCell({ children: kids, width: { size: width, type: WidthType.DXA }, borders, verticalAlign: o.valign || VerticalAlign.TOP,
    shading: o.fill ? { type: ShadingType.CLEAR, fill: o.fill, color: "auto" } : undefined, margins: { top: 30, bottom: 30, left: 80, right: 80 } });
}
function table(widths, rows, o = {}) {
  return new Table({ width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA }, columnWidths: widths, layout: TableLayoutType.FIXED,
    rows: rows.map((r, i) => new TableRow({ tableHeader: o.header && i === 0, cantSplit: true,
      height: o.rowHeight ? { value: o.rowHeight, rule: "atLeast" } : undefined,
      children: r.map((c, j) => cell(c.text ?? c, widths[j], { ...c, fill: c.fill ?? (o.header && i === 0 ? FILL : undefined),
        bold: c.bold ?? (o.header && i === 0), size: c.size ?? (o.header && i === 0 ? 16 : o.size), color: c.color })) })) });
}
const label = (t) => ({ text: t, bold: true, fill: FILL, size: 17 });
const blank = { text: "" };
const value = (v) => (v ? { text: v, bold: true } : blank);

// --- page 1 ---------------------------------------------------------------------------------------------------------
const body = [];
body.push(para([run("Medical summary for emergencies and travel", { size: 30, bold: true })], { after: 20 }));
body.push(para([run(data.subtitle, { size: 16, color: MUTED })], { after: 100 }));

const half = W / 2, lw = 2300;
body.push(table([lw, half - lw, lw, half - lw], data.fill.map(([a, av, b, bv]) => [label(a), value(av), label(b), value(bv)]), { rowHeight: 300 }));
body.push(para(run(""), { after: 60 }));
const iw = [2300, (W - 2300) / 2, (W - 2300) / 2];
body.push(table(iw, [
  [{ text: "Insurance", bold: true, fill: FILL }, { text: "Primary", bold: true, fill: FILL }, { text: "Secondary", bold: true, fill: FILL }],
  [label("Company / plan"), blank, blank],
  [label("Member / subscriber ID"), blank, blank],
  [label("Group number"), blank, blank],
  [label("Policy holder"), blank, blank],
  [label("Plan phone"), blank, blank],
], { rowHeight: 270 }));

body.push(para(data.dx_runs.map(([t, bold, size]) => run(t, { bold: bold || undefined, size: size || undefined })), { before: 120, after: 60, shade: FILL }));

body.push(heading("Important for emergency care"));
body.push(table([2700, W - 2700], data.risks.map(([t, x], i) => [{ text: t, bold: true, color: i < data.hot ? HOT : INK }, { text: x }]), { size: 17 }));

body.push(heading("Latest values and treatment history"));
const lv = table([2300, 1700, 1100], [["", "Value", "Date"], ...data.labs], { header: true, size: 16 });
const past = para(run(data.past, { size: 17 }));
// latest values and the short treatment history side by side, to keep page 1 to one page
body.push(new Table({ width: { size: W, type: WidthType.DXA }, columnWidths: [5200, W - 5200], layout: TableLayoutType.FIXED,
  borders: { top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE }, left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE },
             insideHorizontal: { style: BorderStyle.NONE }, insideVertical: { style: BorderStyle.NONE } },
  rows: [new TableRow({ cantSplit: true, children: [
    new TableCell({ width: { size: 5200, type: WidthType.DXA }, children: [lv], borders: { top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE },
      left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE } }, margins: { right: 200 } }),
    new TableCell({ width: { size: W - 5200, type: WidthType.DXA }, children: [para(run("Past cancer treatment (short)", { bold: true, size: 19 })), past],
      borders: { top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE }, left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE } } }),
  ] })] }));

// --- page 2 ---------------------------------------------------------------------------------------------------------
body.push(new Paragraph({ children: [new PageBreak()] }));
body.push(heading("Current medicines"));
body.push(para(run(data.meds_note, { size: 16, color: MUTED })));
body.push(table([3700, 2900, 1600, W - 8200], [["Medicine", "Dose / how", "For", "Prescriber"],
  ...data.meds.map(([m, dose, f, src]) => [{ text: m, bold: true }, dose, f, { text: src, color: MUTED }]),
  [blank, blank, blank, blank]], { header: true, size: 15 }));
body.push(heading("Care team"));
body.push(table([2200, 2600, 3200, W - 8000], [["Role", "Clinician", "Practice", "Phone"],
  ...data.team.map(([r, n, p]) => [r, { text: n, bold: true }, p, { text: "", fill: "FFFFFF" }]),
  [blank, blank, blank, blank]], { header: true, size: 16, rowHeight: 280 }));
if (data.vaccines.length) {
  body.push(heading(data.vaccines_title));
  body.push(table([4200, 2000], [["Vaccine", "Date"], ...data.vaccines.map(([v, d]) => [{ text: v, bold: true }, d])], { header: true, size: 16 }));
}
body.push(para([run(data.hospitals_label + " ", { bold: true, size: 17 }), run(data.hospitals, { size: 17 })], { before: 100 }));
body.push(para(run(data.foot, { size: 15, color: MUTED })));

const footer = new Footer({ children: [
  new Paragraph({ children: [run(data.disclaimer, { size: 13, color: MUTED })], spacing: { after: 0 } }),
  new Paragraph({ alignment: AlignmentType.RIGHT, children: [
    run("Emergency medical summary · page ", { size: 13, color: MUTED }),
    new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 13, color: MUTED }),
    run(" of ", { size: 13, color: MUTED }),
    new TextRun({ children: [PageNumber.TOTAL_PAGES], font: FONT, size: 13, color: MUTED })] }),
] });

const doc = new Document({
  creator: data.creator || "Family", title: "Emergency medical summary", description: "Medical summary for emergencies and travel",
  styles: { default: { document: { run: { font: FONT, size: 18 } } } },
  sections: [{ properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 720, bottom: 720, left: 864, right: 864, footer: 360 } } },
    footers: { default: footer }, children: body }],
});
Packer.toBuffer(doc).then((buf) => fs.writeFileSync(data.out, buf));
