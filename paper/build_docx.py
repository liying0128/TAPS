#!/usr/bin/env python3
"""Build manuscript and SI Word drafts with embedded figures."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parent
FIG = ROOT / "figures"
OUT_MS = ROOT / "MOAS_manuscript_draft.docx"
OUT_SI = ROOT / "MOAS_supporting_information.docx"


def set_run_font(run, name="Times New Roman", size=11, bold=False, italic=False, color=None):
    run.bold = bold
    run.italic = italic
    run.font.name = name
    run.font.size = Pt(size)
    r = run._element
    rPr = r.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    rFonts.set(qn("w:eastAsia"), "SimSun")
    if color is not None:
        run.font.color.rgb = color


def add_p(doc, text, *, size=11, bold=False, italic=False, space_after=8, first_line=True, align="left", color=None):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_after = Pt(space_after)
    pf.space_before = Pt(0)
    pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    if first_line:
        pf.first_line_indent = Cm(0.74)
    if align == "center":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pf.first_line_indent = Cm(0)
    elif align == "justify":
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    run = p.add_run(text)
    set_run_font(run, size=size, bold=bold, italic=italic, color=color)
    return p


def add_h(doc, text, level=1):
    p = doc.add_heading(text, level=level)
    for run in p.runs:
        run.font.color.rgb = RGBColor(0x1A, 0x20, 0x2C)
        run.font.name = "Times New Roman"
        rPr = run._element.get_or_add_rPr()
        rFonts = rPr.get_or_add_rFonts()
        rFonts.set(qn("w:eastAsia"), "SimSun")
    return p


def add_caption(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.first_line_indent = Cm(0)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(12)
    p.paragraph_format.line_spacing = 1.15
    run = p.add_run(text)
    set_run_font(run, size=10, italic=False)
    run.bold = False
    # bold the "Figure X." / "Table X." prefix
    return p


def add_fig(doc, name, caption, width=16.2):
    path = FIG / name
    if not path.exists():
        add_p(doc, f"[Missing figure: {name}]", first_line=False, italic=True, color=RGBColor(0xC5, 0x30, 0x30))
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.first_line_indent = Cm(0)
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run()
    run.add_picture(str(path), width=Cm(width))
    add_caption(doc, caption)


def _m(tag):
    return OxmlElement(f"m:{tag}")


def _mt(text, sty="i"):
    r = _m("r")
    rPr = _m("rPr")
    st = _m("sty")
    st.set(qn("m:val"), sty)
    rPr.append(st)
    r.append(rPr)
    t = _m("t")
    t.set(qn("xml:space"), "preserve")
    t.text = str(text)
    r.append(t)
    return r


def _wrap(tag, *children):
    node = _m(tag)
    for c in children:
        if c is not None:
            node.append(c)
    return node


def _msub(base, sub):
    return _wrap("sSub", _wrap("e", base), _wrap("sub", sub))


def _msup(base, sup):
    return _wrap("sSup", _wrap("e", base), _wrap("sup", sup))


def _mfrac(num, den):
    return _wrap("f", _wrap("num", num), _wrap("den", den))


def _msqrt(*children):
    rad = _m("rad")
    radPr = _m("radPr")
    hide = _m("degHide")
    hide.set(qn("m:val"), "1")
    radPr.append(hide)
    rad.append(radPr)
    rad.append(_m("deg"))
    rad.append(_wrap("e", *children))
    return rad


def _nary_sum(sub, *body):
    nary = _m("nary")
    naryPr = _m("naryPr")
    ch = _m("chr")
    ch.set(qn("m:val"), "∑")
    naryPr.append(ch)
    limLoc = _m("limLoc")
    limLoc.set(qn("m:val"), "undOvr")
    naryPr.append(limLoc)
    nary.append(naryPr)
    nary.append(_wrap("sub", sub))
    nary.append(_m("sup"))
    nary.append(_wrap("e", *body))
    return nary


def _nil_table_borders(table):
    tblPr = table._tbl.tblPr
    old = tblPr.find(qn("w:tblBorders"))
    if old is not None:
        tblPr.remove(old)
    borders = OxmlElement("w:tblBorders")
    none = {"val": "nil", "sz": "0", "space": "0", "color": "auto"}
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        for k, v in none.items():
            el.set(qn(f"w:{k}"), v)
        borders.append(el)
    tblPr.append(borders)


def add_eq(doc, number, *parts):
    """Centered Word equation with a right-hand number, e.g. (1)."""
    table = doc.add_table(rows=1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _nil_table_borders(table)
    widths = (int(14.6 * 567), int(1.6 * 567))
    tbl = table._tbl
    grid = tbl.find(qn("w:tblGrid"))
    if grid is not None:
        tbl.remove(grid)
    grid = OxmlElement("w:tblGrid")
    for w in widths:
        gc = OxmlElement("w:gridCol")
        gc.set(qn("w:w"), str(w))
        grid.append(gc)
    tbl.insert(1, grid)
    c0, c1 = table.rows[0].cells
    for cell, w in zip((c0, c1), widths):
        tcPr = cell._tc.get_or_add_tcPr()
        tcW = OxmlElement("w:tcW")
        tcW.set(qn("w:w"), str(w))
        tcW.set(qn("w:type"), "dxa")
        old = tcPr.find(qn("w:tcW"))
        if old is not None:
            tcPr.remove(old)
        tcPr.append(tcW)
    p0 = c0.paragraphs[0]
    p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p0.paragraph_format.first_line_indent = Cm(0)
    oMathPara = _m("oMathPara")
    oMath = _m("oMath")
    for part in parts:
        oMath.append(part)
    oMathPara.append(oMath)
    p0._p.append(oMathPara)
    p1 = c1.paragraphs[0]
    p1.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p1.paragraph_format.first_line_indent = Cm(0)
    run = p1.add_run(f"({number})")
    set_run_font(run, size=11)
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(4)
    spacer.paragraph_format.space_before = Pt(0)
    spacer.paragraph_format.first_line_indent = Cm(0)
    return table


def _set_three_line_borders(table):
    """GB/T 7713 three-line table: 1.5 pt top and bottom, 1.0 pt under header, no verticals."""
    tbl = table._tbl
    tblPr = tbl.tblPr
    style_el = tblPr.find(qn("w:tblStyle"))
    if style_el is not None:
        tblPr.remove(style_el)
    old = tblPr.find(qn("w:tblBorders"))
    if old is not None:
        tblPr.remove(old)
    borders = OxmlElement("w:tblBorders")
    thick = {"val": "single", "sz": "12", "space": "0", "color": "000000"}  # 1.5 pt
    none = {"val": "nil", "sz": "0", "space": "0", "color": "auto"}
    for edge, spec in (
        ("top", thick),
        ("left", none),
        ("bottom", thick),
        ("right", none),
        ("insideH", none),
        ("insideV", none),
    ):
        el = OxmlElement(f"w:{edge}")
        for k, v in spec.items():
            el.set(qn(f"w:{k}"), v)
        borders.append(el)
    tblPr.append(borders)

    n = len(table.rows)
    mid = {"sz": "8", "val": "single", "color": "000000", "space": "0"}  # 1.0 pt header rule
    nil = {"sz": "0", "val": "nil", "color": "auto", "space": "0"}
    for r_i, row in enumerate(table.rows):
        for cell in row.cells:
            tc = cell._tc
            tcPr = tc.get_or_add_tcPr()
            old_b = tcPr.find(qn("w:tcBorders"))
            if old_b is not None:
                tcPr.remove(old_b)
            tcBorders = OxmlElement("w:tcBorders")
            specs = {
                "top": thick if r_i == 0 else nil,
                "left": nil,
                "bottom": mid if r_i == 0 else (thick if r_i == n - 1 else nil),
                "right": nil,
            }
            for edge, spec in specs.items():
                el = OxmlElement(f"w:{edge}")
                for k, v in spec.items():
                    el.set(qn(f"w:{k}"), v)
                tcBorders.append(el)
            tcPr.append(tcBorders)


def add_table(doc, headers, rows, col_cm=None):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    try:
        table.style = "Normal Table"
    except KeyError:
        pass
    hdr = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = ""
        p = hdr[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2)
        run = p.add_run(h)
        set_run_font(run, size=9, bold=True, color=RGBColor(0x1A, 0x20, 0x2C))
    for r_i, row in enumerate(rows):
        cells = table.rows[r_i + 1].cells
        for c_i, val in enumerate(row):
            cells[c_i].text = ""
            p = cells[c_i].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(1)
            run = p.add_run(str(val))
            set_run_font(run, size=9)
    _set_three_line_borders(table)
    doc.add_paragraph()
    return table


def setup(doc):
    sec = doc.sections[0]
    sec.page_width = Cm(21.0)
    sec.page_height = Cm(29.7)
    sec.left_margin = Cm(2.5)
    sec.right_margin = Cm(2.5)
    sec.top_margin = Cm(2.5)
    sec.bottom_margin = Cm(2.5)
    styles = doc.styles["Normal"]
    styles.font.name = "Times New Roman"
    styles.font.size = Pt(11)
    rPr = styles.element.get_or_add_rPr()
    rFonts = rPr.get_or_add_rFonts()
    rFonts.set(qn("w:eastAsia"), "SimSun")


def add_authors(doc):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.first_line_indent = Cm(0)
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    r = p.add_run("Yiru Wang")
    set_run_font(r, size=12)
    r = p.add_run("1,2")
    set_run_font(r, size=9)
    r.font.superscript = True
    r = p.add_run(" and Ying Li")
    set_run_font(r, size=12)
    r = p.add_run("1,2")
    set_run_font(r, size=9)
    r.font.superscript = True

    affs = [
        "Beijing Key Laboratory of Biomass Waste Resource Utilization, College of Biochemical Engineering, Beijing Union University, Beijing, 100023, China.",
        "Beijing Key Laboratory of Bioactive Substances and Functional Foods, College of Biochemical Engineering, Beijing Union University, Beijing, 100023, China.",
    ]
    for i, text in enumerate(affs):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Cm(0)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(2 if i == 0 else 14)
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
        r = p.add_run(f"{i + 1}  {text}")
        set_run_font(r, size=9, italic=True)


def add_acknowledgements(doc):
    add_h(doc, "Acknowledgements", 1)
    add_p(
        doc,
        "This work is financially supported by the Project of Cultivation for Young Top-notch "
        "Talents of Beijing Municipal Institutions (BPHR202203209).",
        align="justify",
    )


def build_manuscript():
    doc = Document()
    setup(doc)

    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    t.paragraph_format.space_after = Pt(6)
    r = t.add_run(
        "From Transient Encounters to Committed Sampling:\n"
        "A Multi-Objective Adaptive Sampling Strategy for Rare Protein Conformational States"
    )
    set_run_font(r, size=16, bold=True)

    add_authors(doc)

    add_h(doc, "Abstract", 1)
    add_p(
        doc,
        "Adaptive sampling is widely used to accelerate molecular dynamics of rare protein "
        "conformational changes. Success is still often scored by the first time a trajectory "
        "enters a predefined target window. That criterion is not sufficient: a simulation can "
        "graze the target, leave immediately, and never establish persistent sampling of the "
        "basin. We introduce MOAS, a multi-objective adaptive sampling strategy that ranks "
        "candidate seeds by novelty, boundary exploration, and target proximity, mixed by equal "
        "percentile ranks under a diversity constraint. The primary endpoints are a committed "
        "visit of the target window and the occupancy of that basin over the full simulation "
        "budget. We apply the method to chignolin folding, the open-to-closed transition of "
        "adenylate kinase, and domain closure of apo maltose-binding protein. MOAS established "
        "committed sampling in every replicate on every system, whereas random selection almost "
        "never committed and exploration-oriented methods often hit the window without remaining "
        "there. Occupancy of the target basin was substantially higher for MOAS than for the "
        "matched baselines. Ablation indicates that exploration and target-directed terms are "
        "complementary, and that no reduced mix reproduced the residence of the full method. "
        "The results support scoring adaptive sampling of target states by committed, persistent "
        "sampling rather than by first encounter alone.",
        first_line=True,
        align="justify",
    )

    add_h(doc, "1. Introduction", 1)
    add_p(
        doc,
        "Molecular dynamics (MD) can, in a single trajectory, supply the structural, "
        "thermodynamic, and kinetic information that a crystal structure does not: which basins "
        "are populated, how they interconvert, and along which coordinates. That combination is "
        "why MD is used for folding, domain motion, and ligand-linked conformational change. The "
        "limitation is timescale. Unbiased integration advances on a femtosecond step, whereas "
        "the protein transitions of interest often lie on microsecond-to-millisecond or longer "
        "scales, so extending one long trajectory is an inefficient way to spend a finite budget "
        "on a rare event. Adaptive sampling spends the same budget more productively: "
        "configurations are harvested from the visited ensemble, ranked, used as starting points "
        "(seeds) for short trajectories, and pooled, and the cycle repeats. The usual design "
        "question is where to sample next—which regions of collective-variable (CV) space are "
        "still empty, under-counted, or on the frontier of the cloud. That question is necessary, "
        "but it is not sufficient. The central question is not only where to sample next, but "
        "also how to define a successful sampling event.",
        align="justify",
    )
    add_p(
        doc,
        "How that event is defined depends on what a method is built to favor. Existing adaptive "
        "schemes are coherent once those aims are stated; they are not interchangeable, and they "
        "are not failures of one another’s objectives. Random selection provides unbiased, diverse "
        "restarts from the current pool. Least-counts directs seeds into under-sampled histogram "
        "bins. LAST drives the ensemble toward the frontier of the visited cloud. kNN-AS, a "
        "machine-learning frontier score, similarly emphasizes low-density or otherwise "
        "under-explored regions of CV space. By construction, all of these strategies tend to "
        "explore where the trajectory has not been. That is a well-posed objective for covering "
        "conformational space. It is not equivalent to remaining where the target state is. When "
        "success is recorded as first hit—the first time any frame enters a predefined target "
        "window—the two aims are quietly substituted for one another. A method can be excellent "
        "at pushing the cloud outward, record an early hit, and still never establish the target "
        "as a sampled basin. The gap this paper addresses is therefore not that exploration "
        "methods explore, but that first hit is not a committed visit.",
        align="justify",
    )
    add_p(
        doc,
        "The substitution is easier to see if campaign outcomes are ranked rather than collapsed "
        "into a single time. A run may never enter the target window; it may enter once (a first "
        "hit); it may remain inside the predefined target region continuously for a specified "
        "minimum duration (a committed visit); or it may spend a substantial fraction of the "
        "budget there (sustained target-basin occupancy). These are not interchangeable. First "
        "hit is a passage event, committed visit is a sojourn, and occupancy is a time-averaged "
        "residence, so a campaign can stop after a brief encounter. A trajectory can therefore "
        "have a short first-hit time but essentially zero useful target-state sampling—the "
        "premise of Figure 2, and the reason committed visit, not first hit, is the primary "
        "endpoint below.",
        align="justify",
    )
    add_p(
        doc,
        "In this work we introduce MOAS, a multi-objective adaptive sampling strategy that ranks "
        "candidate seeds by novelty (inverse local density), boundary exploration (LAST-style "
        "frontier), and target proximity, mixed by equal percentile ranks and subject to a "
        "diversity constraint. Campaigns are scored by committed visit and by occupancy, and "
        "MOAS is compared with Random, LAST, least-counts, and kNN-AS under matched initialization, "
        "short-MD length, and aggregate time on CLN025 folding, the adenylate kinase open-to-closed "
        "transition, and apo maltose-binding protein domain closure (n = 3). The sampling objective "
        "of each baseline is summarized in Table 1. The working hypothesis "
        "is that balancing exploration of poorly sampled regions with target-directed exploitation "
        "converts transient encounters into committed and persistent target-state sampling.",
        align="justify",
    )
    add_table(
        doc,
        ["Method", "Sampling objective"],
        [
            ["Random", "Unbiased restart from the current pool"],
            ["Least-counts", "Under-sampled regions of a CV histogram"],
            ["LAST", "Frontier of the visited ensemble"],
            ["kNN-AS", "Low-density regions of CV space"],
        ],
    )
    add_caption(
        doc,
        "Table 1. Optimization target of each exploration-oriented baseline. These methods "
        "are compared with MOAS under a matched budget in Results; they are not scored against "
        "aims they were not designed to serve.",
    )

    add_h(doc, "2. Materials and Methods", 1)

    add_h(doc, "2.1 Molecular dynamics protocol", 2)
    add_p(
        doc,
        "All production and adaptive segments were run in GROMACS with AMBER99SB-ILDN and TIP3P "
        "water at 300 K and 0.15 M NaCl. The time step was 2 fs with LINCS constraints on "
        "hydrogen-involving bonds, PME electrostatics, and a Verlet cutoff. Short adaptive "
        "trajectories used GPU update and PME. Initialization MD was unbiased and shared across "
        "methods within a system and replicate, so that differences arise only from seed "
        "selection. Box padding was 1.2 nm; MBP used a rhombic dodecahedron to limit solvent "
        "cost. Further MDP settings are in the Supporting Information (Table S1).",
        align="justify",
    )

    add_h(doc, "2.2 MOAS framework", 2)
    add_p(
        doc,
        "MOAS is an iterative adaptive-sampling loop (Figure 1). An unbiased initialization "
        "trajectory supplies the first pool of configurations. At every round, candidate windows "
        "are scored on three objectives (novelty, boundary, target proximity), ranks are mixed, "
        "and a diversity constraint selects six seeds. Each seed launches a short MD segment; "
        "the new frames are appended to the pool; and the cycle repeats until a fixed aggregate "
        "budget is reached. No method receives extra simulation time. The production method in "
        "this paper is the static equal-weight mix (MOAS-static). Dynamic and Pareto variants "
        "exist in the code base but are not used in the main comparison. The workflow is "
        "introduced with the evaluation criteria in Section 3.1.",
        align="justify",
    )

    add_h(doc, "2.3 Novelty score", 2)
    add_p(
        doc,
        "Novelty favors configurations in sparsely sampled regions of the two-dimensional CV "
        "space (Figure 1B). A 24 × 24 histogram is built from the pooled frames. For a candidate "
        "window q, let b(q) be the bin that contains q and let n_b(q) be that bin’s count. Local "
        "density and the novelty score are",
        align="justify",
    )
    add_eq(
        doc,
        1,
        _msub(_mt("ρ"), _mt("q")),
        _mt(" = ", "p"),
        _msub(_mt("n"), _mt("b(q)")),
        _mt(",  ", "p"),
        _msub(_mt("s"), _mt("nov")),
        _mt("("),
        _mt("q"),
        _mt(") = ", "p"),
        _mfrac(
            _mt("1", "p"),
            _wrap("e", _msub(_mt("ρ"), _mt("q")), _mt(" + ε", "p")),
        ),
    )
    add_p(
        doc,
        "with ε = 10⁻⁶. The score is then divided by its maximum over the current candidate list "
        "so that s_nov ∈ (0, 1]. High scores mark empty or rarely visited bins and discourage "
        "re-sampling of already dense regions. Least-counts uses s_nov alone.",
        align="justify",
    )

    add_h(doc, "2.4 Boundary score", 2)
    add_p(
        doc,
        "Boundary exploration follows a LAST-style frontier construction (Figure 1C). Occupied "
        "CV bins that have at least one empty 4-neighbor are labeled as the rim F of the visited "
        "cloud. CVs are scaled before binning (σ_x = 0.05 nm and σ_y = 4° on AdK/MBP; RMSD and Rg "
        "on CLN025) so that one axis does not dominate. Let r̂(q) be the Euclidean distance of q "
        "to the cloud centroid, divided by the maximum such distance, and let ρ̂(q) be the bin "
        "count at q divided by the maximum bin count. The boundary score is",
        align="justify",
    )
    add_eq(
        doc,
        2,
        _msub(_mt("s"), _mt("bnd")),
        _mt("("),
        _mt("q"),
        _mt(") = 1.5 ", "p"),
        _msub(_mt("1"), _mt("F")),
        _mt("("),
        _mt("q"),
        _mt(") + ", "p"),
        _mt("r̂"),
        _mt("("),
        _mt("q"),
        _mt(")", "p"),
        _mt(" [1 − 0.5 ", "p"),
        _mt("ρ̂"),
        _mt("("),
        _mt("q"),
        _mt(")]", "p"),
    )
    add_p(
        doc,
        "where 1_F(q) = 1 if q lies in a frontier bin and 0 otherwise. The first term places "
        "mass on the rim; the second prefers the outer, low-density edge of a thick frontier. "
        "This term expands coverage and does not encode the target basin. LAST uses s_bnd alone.",
        align="justify",
    )

    add_h(doc, "2.5 Target-proximity score", 2)
    add_p(
        doc,
        "Target proximity is the only objective that encodes where the scientifically relevant "
        "basin lies (Figure 1D). Let x* be the closed or folded reference in CV space. On AdK "
        "and MBP a scaled distance to that reference is",
        align="justify",
    )
    add_eq(
        doc,
        3,
        _msub(_mt("d"), _mt("*")),
        _mt("("),
        _mt("q"),
        _mt(") = ", "p"),
        _mt("∥", "p"),
        _mt("z"),
        _mt("("),
        _mt("q"),
        _mt(") − ", "p"),
        _msup(_mt("z"), _mt("*")),
        _mt("∥", "p"),
        _mt(",  ", "p"),
        _mt("z"),
        _mt(" = (", "p"),
        _mfrac(_mt("x"), _msub(_mt("σ"), _mt("x"))),
        _mt(", ", "p"),
        _mfrac(_mt("y"), _msub(_mt("σ"), _mt("y"))),
        _mt(")", "p"),
    )
    add_p(
        doc,
        "with the same (σ_x, σ_y) as in Section 2.4. The target score on AdK and MBP, and the "
        "CLN025 analogue using Cα-RMSD, are",
        align="justify",
    )
    add_eq(
        doc,
        4,
        _msub(_mt("s"), _mt("tgt")),
        _mt("("),
        _mt("q"),
        _mt(") = ", "p"),
        _mfrac(_wrap("e", _mt("1", "p")), _wrap("e", _msub(_mt("d"), _mt("*")), _mt("("), _mt("q"), _mt(") + 5", "p"))),
        _mt("  (AdK, MBP)", "p"),
    )
    add_eq(
        doc,
        5,
        _msub(_mt("s"), _mt("tgt")),
        _mt("("),
        _mt("q"),
        _mt(") = ", "p"),
        _mfrac(
            _wrap("e", _mt("1", "p")),
            _wrap(
                "e",
                _mt("max", "p"),
                _mt("("),
                _mt("RMSD", "p"),
                _mt(" − 0.25 nm, 0) + 0.05 nm", "p"),
            ),
        ),
        _mt("  (CLN025)", "p"),
    )
    add_p(
        doc,
        "so that s_tgt is large near the target and decays smoothly away from it. On CLN025, "
        "candidates already inside the folded cutoff RMSD < 0.25 nm are not further distinguished "
        "by this term.",
        align="justify",
    )

    add_h(doc, "2.6 Ranking, weighting, and diversity-constrained seed selection", 2)
    add_p(
        doc,
        "The three raw scores have incommensurate units. Each active score s_α is converted to "
        "a percentile rank over the N candidates of the current round (Figure 1E). If π_α(q) is "
        "the 0-based rank of s_α(q) after stable sorting,",
        align="justify",
    )
    add_eq(
        doc,
        6,
        _msub(_mt("r"), _mt("α")),
        _mt("("),
        _mt("q"),
        _mt(") = ", "p"),
        _mfrac(_wrap("e", _msub(_mt("π"), _mt("α")), _mt("("), _mt("q"), _mt(")")), _wrap("e", _mt("N − 1", "p"))),
        _mt(",  α ∈ {nov, bnd, tgt}", "p"),
    )
    add_p(
        doc,
        "Production MOAS uses equal weights on all three ranks. Ablation campaigns drop unused "
        "terms and average over the active subset A:",
        align="justify",
    )
    add_eq(
        doc,
        7,
        _mt("S"),
        _mt("("),
        _mt("q"),
        _mt(") = ", "p"),
        _mfrac(
            _wrap("e", _nary_sum(_mt("α ∈ A", "p"), _msub(_mt("r"), _mt("α")), _mt("("), _mt("q"), _mt(")"))),
            _wrap("e", _mt("|", "p"), _mt("A"), _mt("|", "p")),
        ),
        _mt("  ", "p"),
        _mt("A = {nov, bnd, tgt}", "p"),
        _mt("  for full MOAS", "p"),
    )
    add_p(
        doc,
        "Seeds are then accepted in order of decreasing S(q) subject to a diversity constraint "
        "in the same scaled CV coordinates z = (x/σ_x, y/σ_y) (Figure 1F). A candidate i is kept "
        "only if it is at least δ = 1 from every already chosen seed,",
        align="justify",
    )
    add_eq(
        doc,
        8,
        _mt("∥", "p"),
        _msub(_mt("z"), _mt("i")),
        _mt(" − ", "p"),
        _msub(_mt("z"), _mt("j")),
        _mt("∥ ≥ δ  for all chosen j", "p"),
    )
    add_p(
        doc,
        "The selected frames are dumped from the parent short trajectory and used as starting "
        "coordinates for the next round.",
        align="justify",
    )

    add_h(doc, "2.7 CLN025", 2)
    add_p(
        doc,
        "CLN025 is a 10-residue fast-folding mini-protein. Campaigns start from an unfolded "
        "structure in water. The CVs are Cα-RMSD to the native reference and radius of gyration. "
        "The target window is RMSD < 0.25 nm; a committed visit requires that this predicate hold "
        "contiguously for at least 40 ps. Each campaign uses a 10 ns unbiased initialization, "
        "then 12 rounds of 6 × 1 ns short trajectories (aggregate budget 82 ns).",
        align="justify",
    )

    add_h(doc, "2.8 Adenylate kinase", 2)
    add_p(
        doc,
        "Apo adenylate kinase (AdK) is scored on the LID–CORE and NMP–CORE angles. Campaigns "
        "start from the open apo conformation. The closed window is the side-aware cut between "
        "open and closed references: LID < 114.4° and NMP > 41.8°. A committed visit requires "
        "both angles to remain in that window for at least 200 ps. Each campaign uses a 20 ns "
        "open initialization, then 15 rounds of 6 × 2 ns short trajectories (aggregate budget "
        "200 ns).",
        align="justify",
    )

    add_h(doc, "2.9 Maltose-binding protein", 2)
    add_p(
        doc,
        "Apo maltose-binding protein (MBP) undergoes large-scale domain closure. Campaigns start "
        "from open apo 1OMP; the closed reference is 1ANF with maltose removed. The CVs are the "
        "CA center-of-mass distance between the N- and C-terminal domains (residues 1–109 + "
        "264–309 and 114–258 + 316–370) and a hinge angle at residues 109–114 / 258–264 / "
        "309–316. The closed window is distance < 2.885 nm and hinge < 115.9°. Commitment "
        "requires both CVs in that window for at least 200 ps. Each campaign uses a 20 ns open "
        "initialization, then 82 rounds of 6 × 2 ns short trajectories (aggregate budget 1 μs). "
        "The protocol is summarized with CLN025 and AdK in Table 2.",
        align="justify",
    )
    add_table(
        doc,
        ["System", "Transition", "CVs", "Init", "Short MD", "Budget", "Commit"],
        [
            ["CLN025", "folding (unfolded start)", "Cα-RMSD to native, Rg", "10 ns", "1 ns × 6 × 12", "82 ns", "RMSD < 0.25 nm for ≥ 40 ps"],
            ["AdK", "open → closed, apo", "LID–CORE and NMP–CORE angles", "20 ns", "2 ns × 6 × 15", "200 ns", "both angles in closed window ≥ 200 ps"],
            ["MBP", "domain closure, apo", "N/C-domain CA-COM distance, hinge angle", "20 ns", "2 ns × 6 × 82", "1 μs", "both CVs in closed window ≥ 200 ps"],
        ],
    )
    add_caption(
        doc,
        "Table 2. Simulation protocol. Closed windows for AdK and MBP are side-aware cuts "
        "between the open and closed reference structures. CLN025 starts unfolded; AdK and MBP "
        "start from the open apo crystal conformation.",
    )

    add_h(doc, "2.10 Baseline methods", 2)
    add_p(
        doc,
        "Every system was run with five methods under identical initialization, short-MD length, "
        "seed count, diversity rule, and budget. Random assigns uniform scores to eligible "
        "windows. LAST uses only the boundary score of Section 2.4. Least-counts uses only the "
        "inverse-density novelty score of Section 2.3. kNN-AS follows Rovers et al. (J. Chem. "
        "Theory Comput. 2025): the visited CV cloud is subsampled with probability P = 0.5 and "
        "each candidate is scored from its k = 5 nearest neighbors as",
        align="justify",
    )
    add_eq(
        doc,
        9,
        _msub(_mt("s"), _mt("knn")),
        _mt("("),
        _mt("q"),
        _mt(") = ", "p"),
        _mt("∥", "p"),
        _nary_sum(
            _mt("j"),
            _mt("("),
            _msub(_mt("z"), _mt("j")),
            _mt(" − ", "p"),
            _mt("q"),
            _mt(")"),
        ),
        _mt("∥", "p"),
    )
    add_p(
        doc,
        "Interior points cancel; boundary points retain a long resultant. There is no target "
        "term. MOAS-static is the three-objective mix of Section 2.6. TAPS, a target-aware "
        "predecessor used in earlier CLN025 work, is reported only in the Supporting Information "
        "and is not a main-text baseline. Independent replicates use random seeds 0, 1, and 2.",
        align="justify",
    )

    add_h(doc, "2.11 First hit", 2)
    add_p(
        doc,
        "Metrics are computed on the concatenated, time-ordered pool of each campaign. Let "
        "1_W(x_t) = 1 if frame x_t lies in the target window W (RMSD < 0.25 nm on CLN025; both "
        "closed-window CVs on AdK and MBP) and 0 otherwise. First hit is",
        align="justify",
    )
    add_eq(
        doc,
        10,
        _msub(_mt("t"), _mt("hit")),
        _mt(" = ", "p"),
        _mt("min", "p"),
        _mt(" { ", "p"),
        _msub(_mt("t"), _mt("i")),
        _mt("  |  ", "p"),
        _msub(_mt("1"), _mt("W")),
        _mt("("),
        _msub(_mt("x"), _mt("i")),
        _mt(") = 1 }", "p"),
    )
    add_p(
        doc,
        "It is reported for completeness. It is not the primary success criterion: a campaign "
        "may hit and still fail to remain in the basin.",
        align="justify",
    )

    add_h(doc, "2.12 Committed visit", 2)
    add_p(
        doc,
        "A committed visit is the primary endpoint. With frame spacing Δt, it is the first time "
        "a contiguous sojourn inside W reaches duration τ (τ = 40 ps on CLN025; 200 ps on AdK "
        "and MBP):",
        align="justify",
    )
    add_eq(
        doc,
        11,
        _msub(_mt("t"), _mt("com")),
        _mt(" = ", "p"),
        _mt("min", "p"),
        _mt(" { ", "p"),
        _msub(_mt("t"), _mt("i")),
        _mt("  |  ", "p"),
        _msub(_mt("1"), _mt("W")),
        _mt("("),
        _msub(_mt("x"), _mt("i−n+1")),
        _mt(") = ⋯ = ", "p"),
        _msub(_mt("1"), _mt("W")),
        _mt("("),
        _msub(_mt("x"), _mt("i")),
        _mt(") = 1,  nΔt ≥ τ }", "p"),
    )
    add_p(
        doc,
        "The clock is accumulated campaign time, not wall-clock time. A campaign that records a "
        "first hit but never meets this sojourn is classified as transient-only.",
        align="justify",
    )

    add_h(doc, "2.13 Target-basin occupancy", 2)
    add_p(
        doc,
        "Target-basin occupancy is the fraction of the N pooled frames that lie in W over the "
        "full budget,",
        align="justify",
    )
    add_eq(
        doc,
        12,
        _msub(_mt("f"), _mt("W")),
        _mt(" = ", "p"),
        _mfrac(_wrap("e", _mt("1", "p")), _wrap("e", _mt("N"))),
        _nary_sum(_mt("i = 1", "p"), _msub(_mt("1"), _mt("W")), _mt("("), _msub(_mt("x"), _mt("i")), _mt(")")),
    )
    add_p(
        doc,
        "It measures persistent sampling after—or in the absence of—commitment, and is the "
        "quantity that distinguishes a brief encounter from continued exploration of the target "
        "state. Coverage of the 24 × 24 CV histogram is stored as an exploration diagnostic and "
        "is not used as a success criterion.",
        align="justify",
    )

    add_h(doc, "2.14 Statistical analysis", 2)
    add_p(
        doc,
        "Main comparisons use n = 3 independent adaptive campaigns per method and system. We "
        "report replicate counts (for example 3/3 committed), per-replicate hit and commit times, "
        "and median occupancy with the interquartile range. Ablation of objective combinations "
        "is n = 1 on AdK and MBP. "
        "Kaplan–Meier curves and bootstrap confidence intervals on time-to-commit can be computed "
        "from the replicate table in the Supporting Information without additional MD.",
        align="justify",
    )

    add_h(doc, "3. Results", 1)

    add_h(doc, "3.1 First-hit detection does not establish successful target-state sampling", 2)
    add_p(
        doc,
        "The MOAS loop is summarized in Figure 1 so that later panels can be read against a "
        "single scoring diagram. An unbiased initialization fills the first pool. Each round "
        "scores candidate windows for novelty (inverse local density; Figure 1B), boundary "
        "(LAST-style frontier; Figure 1C), and target proximity (Figure 1D). The three scores "
        "are converted to percentile ranks and averaged (Figure 1E), and six seeds are accepted "
        "under a diversity constraint (Figure 1F). Short MD from those seeds updates the pool, "
        "and the cycle repeats to a fixed budget. The remainder of this subsection does not "
        "ask whether that mix already outperforms other methods. It asks whether first hit, "
        "as commonly reported, is a sufficient definition of success.",
        align="justify",
    )
    add_fig(
        doc,
        "fig1_workflow.png",
        "Figure 1. MOAS workflow. (A) Iterative adaptive cycle. (B) Novelty: inverse local "
        "density, favoring poorly sampled configurations. (C) Boundary: LAST-style frontier of "
        "the visited cloud. (D) Target proximity: candidates near the predefined target basin. "
        "(E) Equal-percentile mixing of the three ranks. (F) Diversity-constrained selection of "
        "multiple seeds per round.",
    )
    add_p(
        doc,
        "CLN025 and AdK trajectories show that entering the target window is not the same as "
        "sampling the target state. On CLN025, TAPS reached the folded RMSD window in all three "
        "replicates (first hits 30.5, 31.6, and 51.6 ns) but committed in only 1/3, with median "
        "occupancy 0.24%. Rolling occupancy of the folded window remains a brief spike for TAPS, "
        "whereas LAST and MOAS accumulate longer folded sojourns (Figure 2A). kNN-AS likewise "
        "hit in 3/3 CLN025 campaigns and committed in only 1/3 (median occupancy 0.14%). Random "
        "sampling recorded two CLN025 hits and zero commits.",
        align="justify",
    )
    add_p(
        doc,
        "The same dissociation is visible on AdK. Random seed 0 first entered the closed-angle "
        "window at 83.3 ns and never committed; rolling occupancy stayed near zero after that "
        "hit. MOAS on the same initialization established repeated closed-basin residence after "
        "commitment (Figure 2B). Across systems, an early first hit did not predict high occupancy: "
        "several LAST, least-counts, and kNN-AS campaigns hit and still finished below 1% occupancy "
        "(Figure 2C). Conversion of a hit into a committed visit was incomplete for those "
        "exploration-oriented runs and complete for MOAS among campaigns that hit (Figure 2D). "
        "A trajectory can therefore have a short first-hit time and essentially no useful "
        "target-state sampling. Subsequent sections score campaigns by committed visit and by "
        "target-basin occupancy, not by first hit alone.",
        align="justify",
    )
    add_fig(
        doc,
        "fig2_hit_vs_commit.png",
        "Figure 2. First-hit detection does not establish successful target-state sampling. "
        "(A) CLN025 rolling occupancy of the folded window (2 ns kernel) for TAPS, LAST, and "
        "MOAS (seed 0). (B) AdK rolling closed occupancy: Random hits at 83 ns and escapes; "
        "MOAS remains in the basin. (C) First-hit time versus occupancy for all n = 3 campaigns; "
        "open symbols did not hit. (D) Fraction of hits that later committed. TAPS is shown "
        "only for CLN025.",
    )

    add_h(doc, "3.2 MOAS enables committed sampling across distinct protein conformational transitions", 2)
    add_p(
        doc,
        "The evaluation criteria of Section 3.1 were applied to three conformational transitions "
        "of increasing scale: CLN025 folding from an unfolded start (82 ns budget; commit ≥ 40 ps "
        "in RMSD < 0.25 nm), apo AdK open-to-closed (200 ns; both LID/NMP angles in the closed "
        "window ≥ 200 ps), and apo MBP domain closure (1 μs; domain distance and hinge angle in "
        "the closed window ≥ 200 ps). Each method used the same initialization, short-MD length, "
        "six seeds per round, and n = 3 independent campaigns (Table 2).",
        align="justify",
    )
    add_p(
        doc,
        "Committed-replicate counts are summarized in Figure 3A–C. MOAS committed in 3/3 "
        "campaigns on every protein. Random committed in 0/9 campaigns. LAST committed in 3/3 "
        "CLN025 runs, 0/3 AdK runs, and 1/3 MBP runs. Least-counts committed in 3/3, 2/3, and "
        "1/3. kNN-AS committed in 1/3, 1/3, and 2/3. Per-replicate outcomes (committed, hit-only, "
        "or no hit) are shown in Figure 3F. The pattern is not that MOAS is always the first to "
        "hit, but that it is the only method that recorded a committed visit on every replicate "
        "of every transition.",
        align="justify",
    )
    add_p(
        doc,
        "Among campaigns that committed, median times to commitment were 36.1 ns for MOAS on "
        "CLN025 (LAST 46.4 ns; least-counts 68.6 ns), 105.7 ns on AdK, and 442.8 ns on MBP "
        "(Figure 3D). On MBP, kNN-AS committed later (median 705 ns) and LAST’s single success "
        "was at 320 ns. Target-basin occupancy for all replicates is shown in Figure 3E and is "
        "examined in Section 3.3; it is included here so that commitment and residence can be "
        "read on the same campaign set.",
        align="justify",
    )
    add_fig(
        doc,
        "fig3_benchmark.png",
        "Figure 3. MOAS enables committed sampling across distinct protein conformational "
        "transitions (n = 3). (A–C) Number of committed replicates on CLN025, AdK, and MBP. "
        "(D) Time to committed visit (log scale); × marks campaigns that never committed "
        "(plotted at the budget). (E) Target-basin occupancy. (F) Per-replicate outcome: "
        "C, committed; H, hit only; —, no hit.",
    )

    add_h(doc, "3.3 Committed visits are associated with sustained target-basin occupancy", 2)
    add_p(
        doc,
        "Section 3.2 established that a committed visit occurred. This section asks whether "
        "that visit is associated with more useful sampling of the target basin, as opposed to "
        "a single qualifying sojourn followed by escape. Occupancy is the fraction of the full "
        "budget spent inside the target window.",
        align="justify",
    )
    add_p(
        doc,
        "Median occupancies for MOAS were 5.25% on CLN025 (IQR 4.65–6.02), 14.85% on AdK "
        "(IQR 7.78–21.34), and 37.15% on MBP (IQR 32.78–39.63), with the three replicates shown "
        "as points in Figure 4A–C. The AdK MOAS replicate that committed only at 192 ns remained "
        "at 0.72% occupancy: commitment without large occupancy is possible, which is why the "
        "two quantities are reported separately. LAST’s CLN025 occupancy median was 1.66%; its "
        "MBP median was 0.02%, despite one replicate that reached 26% after committing. kNN-AS "
        "medians were 0.14%, ~0%, and 0.14% on the three systems.",
        align="justify",
    )
    add_p(
        doc,
        "CV densities show where that occupancy sits. On AdK, MOAS accumulates density inside "
        "the closed LID–NMP window, whereas LAST remains in the open cloud (Figure 4D). On MBP, "
        "MOAS occupies the closed domain-distance / hinge-angle basin; LAST density stays near "
        "the open reference (Figure 4E). Restricting the comparison to campaigns that recorded "
        "a first hit does not remove the occupancy gap (Figure 4F). Hitting the window is "
        "therefore not the event that distinguishes the methods; remaining in the basin is. "
        "We describe this as an association between committed visits and sustained occupancy, "
        "not as a claim that commitment causally produces occupancy in the absence of further "
        "analysis.",
        align="justify",
    )
    add_fig(
        doc,
        "fig4_occupancy.png",
        "Figure 4. Committed visits are associated with sustained target-basin occupancy. "
        "(A–C) Median occupancy (bars) with three independent replicates (points). (D) AdK "
        "LID–NMP density for LAST (blue) and MOAS (red); dashed lines mark the closed window. "
        "(E) Analogous MBP domain-distance / hinge-angle density. (F) Occupancy restricted to "
        "campaigns that recorded a first hit.",
    )

    add_h(doc, "3.4 Contribution of individual objectives to MOAS sampling behavior", 2)
    add_p(
        doc,
        "The preceding sections report full MOAS. Here the three scores are switched on or off "
        "under the same AdK and MBP budgets (n = 1) to describe their relative contribution, "
        "not to prove that every term is indispensable. Full MOAS is the already completed "
        "static campaign and was not rerun.",
        align="justify",
    )
    add_p(
        doc,
        "On AdK, novelty only and boundary only each hit the closed window (108 ns and 174 ns) "
        "and did not commit (occupancy 0.27% and 0.32%). Novelty+boundary never hit. Target only "
        "committed at 92 ns with 16.8% occupancy; novelty+target committed at 92 ns with 17.9%; "
        "boundary+target committed at 144 ns with 5.0%; full MOAS committed at 103 ns with 14.8% "
        "(Figure 5A, B). Target proximity is therefore strongly associated with commitment on "
        "this protein. Adding novelty or boundary to target changes occupancy more than it "
        "changes the binary commit call; novelty+target is slightly above full MOAS in occupancy "
        "in this single replicate, so equal three-term mixing is not claimed to be uniquely "
        "optimal.",
        align="justify",
    )
    add_p(
        doc,
        "On MBP, novelty only and novelty+boundary never hit. Boundary only committed (417 ns, "
        "6.0% occupancy). Target only committed late (731 ns, 3.8%). Novelty+target hit at "
        "561 ns and committed only at 964 ns, with 0.36% occupancy. Boundary+target hit at "
        "849 ns and did not commit (occupancy ~0%). Full MOAS committed at 443 ns with 28.4% "
        "occupancy (Figure 5C, D). No single- or two-term mix matches that occupancy. "
        "Exploration without a target term either fails to hit or, if it commits, occupies "
        "far less of the 1 μs budget than the three-term mix; a target term without the full "
        "exploration mix can convert an encounter into a late commit and still leave almost "
        "no ensemble in the closed basin. The two classes of term are complementary on this "
        "larger transition.",
        align="justify",
    )
    add_fig(
        doc,
        "fig5_ablation.png",
        "Figure 5. Contribution of individual MOAS objectives (n = 1). (A) AdK committed visit. "
        "(B) AdK time to commit and occupancy; × indicates no commit. (C–D) MBP commitment and "
        "occupancy.",
    )
    add_p(
        doc,
        "Seed locations versus round number on AdK show how that mix is used over time "
        "(Figure 6). Random and LAST seeds remain in the open LID–NMP cloud through late rounds. "
        "kNN-AS explores a wide frontier but does not concentrate in the closed window. MOAS "
        "seeds start in the open cloud (early rounds) and later rounds occupy the closed "
        "quadrant, coinciding with the rise in rolling occupancy in Figure 2B. The algorithm "
        "therefore spends early rounds on exploration and later rounds on target-directed "
        "sampling, rather than performing a pure first-passage search.",
        align="justify",
    )
    add_fig(
        doc,
        "fig6_seeds.png",
        "Figure 6. Seed selection in AdK CV space. Hexbin: sampled density. Points: selected "
        "seeds colored by round (blue early, red late). Dashed lines: closed window. Only MOAS "
        "migrates seeds into the closed basin in later rounds.",
    )

    add_h(doc, "3.5 Exploration coverage and target-state occupancy represent complementary sampling objectives", 2)
    add_p(
        doc,
        "Figure 7 places every n = 3 campaign on two axes: the filled fraction of a 24 × 24 CV "
        "histogram (coverage) and target-basin occupancy. LAST, kNN-AS, and least-counts occupy "
        "the high-coverage, low-occupancy region on AdK and MBP. MOAS occupies the high-occupancy "
        "side at comparable or slightly lower coverage. CLN025 coverage is compressed for all "
        "methods because the peptide fills few bins of the same 24 × 24 grid; occupancy still "
        "separates MOAS from the others. The two axes are different sampling objectives, not "
        "proxies for one another.",
        align="justify",
    )
    add_p(
        doc,
        "Exploration-oriented methods and MOAS can therefore be compared in one frame without "
        "treating either axis as a universal score. If the scientific question is whether new "
        "conformational space was visited, coverage and frontier scores remain appropriate. If "
        "the question is whether a predefined target state was established as a sampled basin, "
        "committed visit and occupancy are the relevant endpoints. Adaptive sampling should be "
        "evaluated not only by how much of conformational space is explored, but also by whether "
        "the intended target state is sampled in a committed and sustained manner.",
        align="justify",
    )
    add_fig(
        doc,
        "fig7_explore_vs_target.png",
        "Figure 7. Exploration coverage and target-state occupancy are complementary sampling "
        "objectives. Each point is one n = 3 campaign. Coverage is the filled fraction of a "
        "24 × 24 CV histogram. Occupancy is the target-window fraction. MOAS separates on the "
        "occupancy axis; LAST, kNN-AS, and least-counts separate on coverage for AdK and MBP.",
    )

    add_h(doc, "4. Discussion", 1)
    add_p(
        doc,
        "Adaptive sampling is usually discussed in terms of first-hit time, state discovery, "
        "and conformational coverage. Those quantities answer where a trajectory went and how "
        "soon it touched a labeled region. For protein transitions that terminate in a "
        "metastable basin, however, entering the target window once does not mean that the "
        "target state has been sampled. Figure 2 shows campaigns that reach the window early, "
        "leave it, and finish with essentially no target-basin occupancy. The useful distinction "
        "is therefore among an encounter, a commitment, and sustained occupancy. First-hit time "
        "is useful for characterizing target encounters, but it is insufficient as a standalone "
        "measure of successful target-state sampling. When the scientific aim is an ensemble of "
        "the target conformation, success has to include both whether the window was entered and "
        "whether sampling continued after that entry. That two-level reading is the evaluation "
        "framework used in this paper.",
        align="justify",
    )
    add_p(
        doc,
        "MOAS is designed to convert those transient encounters into committed sampling, not by "
        "searching more aggressively for the target, but by keeping three incommensurate aims in "
        "play at once (Figures 3–6). Novelty penalizes seeds that sit in already well-sampled "
        "regions. Boundary, in the LAST sense, pushes the trajectory cloud into new conformational "
        "territory. Target proximity keeps later rounds from remaining indefinitely far from the "
        "basin of interest. The three scores are not a union of three “high-score patches”: "
        "percentile normalization maps each raw scale onto a relative rank so that a dense-cloud "
        "term, a frontier term, and a distance-to-target term can be mixed without one unit "
        "dominating the others. Figure 6 shows how that mix is used over time. Early rounds "
        "place seeds where novelty and boundary are high and the cloud is still in the open or "
        "unfolded region. As configurations approach the target, the target-proximity rank of "
        "those candidates rises, and seed selection migrates toward the basin. The mechanism is "
        "therefore a dynamic balance between exploration and target-directed sampling. That "
        "balance also explains a pattern in the ablation: a target-only score can reach the "
        "window on some systems, and novelty plus target can convert a late MBP encounter into "
        "a commit, yet the full mix is associated with higher occupancy, because exploration "
        "terms continue to supply new approaches to the basin rather than locking onto the "
        "first contact.",
        align="justify",
    )
    add_p(
        doc,
        "The comparison with existing methods is then a comparison of sampling objectives, not "
        "a claim that MOAS supersedes them. Random supplies an unbiased restart baseline and "
        "carries no conformational preference. Least-counts prefers under-sampled histogram "
        "bins. LAST emphasizes the frontier of the visited cloud. kNN-AS uses local neighborhood "
        "structure in a low-density construction to the same exploratory end. All four implement "
        "exploration-oriented seed selection. They are well posed for the question “where has "
        "the trajectory not yet been?” The present results indicate that that question is not "
        "the same as “where is the target metastable basin?” An exploration objective is not a "
        "target-state sampling objective. MOAS adds a target-directed term while retaining "
        "novelty and boundary, so it does not abandon exploration. It extends exploration-oriented "
        "adaptive sampling toward target-state stabilization. Figure 7 makes the same point "
        "geometrically: coverage and occupancy separate campaigns along different axes and should "
        "be read as complementary metrics, not as interchangeable summaries of a single "
        "performance score.",
        align="justify",
    )
    add_p(
        doc,
        "Committed sampling is therefore offered as an evaluation framework, not only as a "
        "score on three proteins. It is aimed at problems in which a metastable ensemble is "
        "the object of interest: protein conformational transitions, ligand-induced shifts, "
        "enzyme open/closed cycles, functional states of membrane proteins, particular basins "
        "of intrinsically disordered proteins, and other rare-event settings where a labeled "
        "target state must be accumulated rather than merely touched. Target-state sampling "
        "should be evaluated at two levels: discovery and stabilization. Discovery corresponds "
        "to first hit; stabilization corresponds to a committed visit and to subsequent ensemble "
        "accumulation. The commitment time itself is not a universal constant. The 40 ps sojourn "
        "used for CLN025 and the 200 ps sojourn used for AdK and MBP are not a contradiction; "
        "they follow from the kinetic scale of each system. A commitment criterion should be "
        "system-specific and physically motivated, then held fixed across methods so that the "
        "comparison remains a comparison of sampling, not of thresholds.",
        align="justify",
    )
    add_p(
        doc,
        "Several limits follow directly from that framing. First, MOAS assumes a predefined "
        "target basin in CV space, so it is a target-directed method rather than a procedure for "
        "discovering unknown states. Automated recognition of metastable basins would widen its "
        "scope. Second, the CVs used here—Cα-RMSD and Rg for CLN025, LID/NMP angles for AdK, "
        "domain distance and hinge angle for MBP—are still chosen by the investigator. "
        "Performance may depend on whether those coordinates resolve the relevant transition. "
        "Learned representations (time-lagged or variational autoencoders, graph embeddings, "
        "Koopman or TICA-type features) are a natural next step. Third, equal one-third weights "
        "on novelty, boundary, and target are a transparent, reproducible baseline, not a claim "
        "of optimality across proteins. Adaptive weights that respond to sampling stage, "
        "uncertainty, target distance, occupancy, or redundancy among objectives remain open. "
        "Fourth, the study comprises three proteins, n = 3 campaigns per main-text method, and "
        "n = 1 ablation runs. That design is sufficient to show consistent behavior and "
        "methodological feasibility; it is not sufficient for a general statistical conclusion. "
        "Larger replicate sets, a broader range of protein classes, and a standardized committed-"
        "sampling benchmark would be required before the framework can be treated as universal.",
        align="justify",
    )

    add_h(doc, "5. Conclusions", 1)
    add_p(
        doc,
        "First hit should not be treated as sufficient evidence of successful adaptive sampling "
        "of a rare conformational state: a trajectory can encounter a target window and leave "
        "without establishing that basin as a sampled ensemble. MOAS addresses that gap by ranking "
        "seeds on novelty, boundary exploration, and target proximity, mixed by equal percentile "
        "ranks and subject to a diversity constraint, so that exploration of poorly sampled "
        "regions is kept in play while sampling is progressively directed toward the intended "
        "state. Across CLN025 folding, the AdK open-to-closed transition, and apo MBP domain "
        "closure, this mix converted transient encounters into committed visits in every "
        "replicate and was associated with higher target-basin occupancy than matched Random, "
        "LAST, least-counts, and kNN-AS campaigns. The practical implication is to score "
        "adaptive sampling of target states by committed residence and persistent occupancy, "
        "and to treat exploration and target-directed stabilization as complementary objectives "
        "rather than as a single performance number.",
        align="justify",
    )

    add_acknowledgements(doc)

    add_h(doc, "Notes for revision", 1)
    add_p(
        doc,
        "1. Figures now include the completed MBP Nov+Tgt ablation (commit 964 ns, occupancy "
        "0.36%). Re-run python3 paper/make_figures.py && python3 paper/build_docx.py after any "
        "further history edits.",
        first_line=False,
    )
    add_p(
        doc,
        "2. SI sensitivity (weights, number of seeds, diversity radius) still needs dedicated "
        "campaigns; they cannot be recovered from the present trajectories.",
        first_line=False,
    )
    add_p(
        doc,
        "3. Figures are matplotlib drafts. Replace Fig. 1 with a vector schematic before submission. "
        "Kaplan–Meier curves and bootstrap CIs on time-to-commit can be added from n3_metrics.csv "
        "without new MD.",
        first_line=False,
    )
    add_p(
        doc,
        "4. Do not mix the unrelated AdK 1000 ns run on lan55 (adk-r1, other paper) into these tables.",
        first_line=False,
    )

    add_h(doc, "Data locations", 1)
    add_p(
        doc,
        "Per-replicate numbers: paper/tables/n3_metrics.csv and ablation_metrics.csv. "
        "Campaign histories: taps-gromacs/analysis/cln025_unfolded/campaigns, "
        "moas-adk/analysis/adk_open/campaigns, moas-mbp/analysis/mbp_open/campaigns, "
        "plus copies of lan55 histories in paper/data/hist_55. Figure script: paper/make_figures.py.",
        first_line=False,
        align="justify",
    )

    doc.save(OUT_MS)
    print("wrote", OUT_MS)


def fmt_ns(v):
    if v is None or v == "":
        return "—"
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"{x:.2f}"


def fmt_pct(v, digits=3):
    if v is None or v == "":
        return "—"
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"{100 * x:.{digits}f}"


def build_si():
    import csv

    doc = Document()
    setup(doc)

    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = t.add_run(
        "Supporting Information\n"
        "From Transient Encounters to Committed Sampling:\n"
        "A Multi-Objective Adaptive Sampling Strategy for Rare Protein Conformational States"
    )
    set_run_font(r, size=14, bold=True)

    add_authors(doc)

    add_h(doc, "S1. Simulation parameters", 1)
    add_p(
        doc,
        "Force field: AMBER99SB-ILDN protein, TIP3P water. Temperature 300 K, pressure 1 bar "
        "(NPT production), 0.15 M NaCl. Box buffer 1.2 nm; rhombic dodecahedron for MBP, "
        "cubic/dodecahedral boxes as prepared for CLN025 and AdK. Integrator and constraints "
        "follow the repository MDP files (md_prod / md_short_1ns / md_short_2ns): 2 fs time step, "
        "LINCS on H-bonds, PME electrostatics, Verlet cutoff. Short adaptive segments use GPU "
        "update / PME. Initialization trajectories are shared across methods within a system "
        "and replicate: 10 ns unfolded cMD (CLN025) or 20 ns open apo cMD (AdK, MBP).",
        first_line=False,
        align="justify",
    )
    add_table(
        doc,
        ["Item", "CLN025", "AdK", "MBP"],
        [
            ["Start", "unfolded", "open apo (4AKE-like)", "open apo (1OMP)"],
            ["Target reference", "native 5AWL/2RVD", "closed 1AKE", "closed 1ANF, ligand removed"],
            ["CVs", "Cα-RMSD, Rg", "LID angle, NMP angle", "N–C CA-COM distance, hinge angle"],
            ["Target window", "RMSD < 0.25 nm", "LID < 114.4° and NMP > 41.8°", "dist < 2.885 nm and θ < 115.9°"],
            ["Commit duration", "≥ 40 ps", "≥ 200 ps", "≥ 200 ps"],
            ["Init unbiased MD", "10 ns", "20 ns", "20 ns"],
            ["Short MD", "1 ns", "2 ns", "2 ns"],
            ["Seeds / round", "6", "6", "6"],
            ["Rounds", "12", "15", "82"],
            ["Aggregate budget", "82 ns", "200 ns", "1000 ns"],
            ["Replicates", "seeds 0, 1, 2", "seeds 0, 1, 2", "seeds 0, 1, 2"],
        ],
    )
    add_caption(doc, "Table S1. Protocol details shared by Random, LAST, least-counts, kNN-AS, and MOAS.")

    add_p(
        doc,
        "MOAS mixing (production): percentile ranks of novelty, LAST boundary, and target "
        "proximity, averaged with equal weights. Ablation campaigns zero the unused ranks and "
        "renormalize over the active subset. kNN-AS: visited CV cloud subsampled with P = 0.5, "
        "k = 5 nearest neighbors, score ||Σ (z_j − q)||; no target term. Least-counts: inverse "
        "histogram count of the candidate’s CV bin. LAST: frontier / boundary score of the "
        "visited set. Random: uniform among eligible windows subject to the same diversity rule "
        "where implemented.",
        first_line=False,
        align="justify",
    )

    add_h(doc, "S2. Replicate-level outcomes", 1)
    add_p(
        doc,
        "Table S2 lists every main-text campaign. First hit and commit times are in nanoseconds "
        "of accumulated simulation time. Occupancy is the fraction of pooled frames inside the "
        "target window. Coverage is the filled fraction of a 24 × 24 CV histogram. Empty commit "
        "entries are campaigns that never satisfied the sojourn criterion.",
        first_line=False,
        align="justify",
    )

    rows = []
    with (ROOT / "tables" / "n3_metrics.csv").open(encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            if rec["method"] == "TAPS":
                continue
            rows.append(
                [
                    rec["system"],
                    rec["method"],
                    rec["rep"],
                    fmt_ns(rec["hit_ns"]),
                    fmt_ns(rec["commit_ns"]),
                    fmt_pct(rec["occupancy"]),
                    fmt_pct(rec["coverage"], 1),
                ]
            )
    add_table(
        doc,
        ["System", "Method", "Rep", "Hit (ns)", "Commit (ns)", "Occupancy (%)", "Coverage (%)"],
        rows,
    )
    add_caption(doc, "Table S2. Main-text n = 3 campaigns (TAPS omitted; see Table S6).")

    add_h(doc, "S3. First-hit data", 1)
    add_p(
        doc,
        "First hit is reported for completeness and is not the primary endpoint. Several "
        "campaigns hit and never committed (transient-only): CLN025 Random (2 hits / 0 commits), "
        "CLN025 kNN-AS (3/1), AdK Random (1/0), AdK LAST (1/0), AdK least-counts (3/2), "
        "MBP Random (1/0), MBP LAST (2/1), MBP least-counts (3/1), MBP kNN-AS (3/2). MOAS "
        "converted every hit into a commit on all three systems (9/9).",
        first_line=False,
        align="justify",
    )

    add_h(doc, "S4. Representative CV traces", 1)
    add_p(
        doc,
        "Figure 2 of the main text already shows rolling target occupancy for CLN025 (TAPS / "
        "LAST / MOAS) and AdK (Random / MOAS). Figure 4D–E shows the corresponding two-dimensional "
        "densities for AdK and MBP. Additional seed-level CV trajectories live in each campaign’s "
        "cvs.npz (keys: CLN025 t_ps, rmsd, rg; AdK t_ps, lid, nmp, closed; MBP t_ps, dist, theta, "
        "closed). They can be replotted without new MD.",
        first_line=False,
        align="justify",
    )
    add_fig(
        doc,
        "fig2_hit_vs_commit.png",
        "Figure S1. Same as main-text Figure 2, reproduced here so that SI readers have the "
        "first-hit versus occupancy comparison next to Tables S2–S6.",
    )

    add_h(doc, "S5. kNN-AS full results", 1)
    add_p(
        doc,
        "kNN-AS was run with the same CVs, commit protocol, initialization, short-MD length, and "
        "budget as the other four methods (Rovers et al., J. Chem. Theory Comput. 2025, "
        "10.1021/acs.jctc.5c00462). It is a frontier / low-support baseline and contains no "
        "target-proximity term. Table S3 isolates those nine campaigns.",
        first_line=False,
        align="justify",
    )
    knn_rows = [r for r in rows if r[1] == "kNN-AS"]
    add_table(
        doc,
        ["System", "Method", "Rep", "Hit (ns)", "Commit (ns)", "Occupancy (%)", "Coverage (%)"],
        knn_rows,
    )
    add_caption(
        doc,
        "Table S3. kNN-AS n = 3. Hits are common on CLN025 and MBP; commitment and occupancy "
        "remain low except AdK seed 1 (commit 96 ns, occupancy 7.3%) and MBP seeds 0–1 "
        "(occupancy 0.14% and 0.76%).",
    )

    add_h(doc, "S6. Ablation numerical table", 1)
    add_p(
        doc,
        "Objective switches: nov, novelty only; bnd, LAST boundary only; tgt, target proximity "
        "only; plus the three pairwise combinations; moas is the full equal mix (same trajectory "
        "as main-text seed 0).",
        first_line=False,
        align="justify",
    )
    ab_rows = []
    with (ROOT / "tables" / "ablation_metrics.csv").open(encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            ab_rows.append(
                [
                    rec["system"],
                    rec["combo"],
                    rec["tag"],
                    fmt_ns(rec["hit_ns"]),
                    fmt_ns(rec["commit_ns"]),
                    fmt_pct(rec["occupancy"]),
                    "yes" if rec["complete"] == "True" else "no",
                ]
            )
    add_table(
        doc,
        ["System", "Combination", "Tag", "Hit (ns)", "Commit (ns)", "Occupancy (%)", "Complete"],
        ab_rows,
    )
    add_caption(doc, "Table S4. Ablation campaigns (n = 1). All combinations completed the budget.")
    add_fig(
        doc,
        "fig5_ablation.png",
        "Figure S2. Ablation figure (same as main-text Figure 5).",
    )

    add_h(doc, "S7. Seed-selection mechanism (extra copy)", 1)
    add_p(
        doc,
        "Selected seeds store only the mixed score in seeds_round*.json, not the three raw "
        "objectives. Figure 6 therefore uses seed CV coordinates versus round index, which are "
        "sufficient to show late-round migration into the AdK closed window for MOAS only. "
        "The three raw ranks can be recomputed from cvs.npz if a future revision needs an "
        "objective-space plot.",
        first_line=False,
        align="justify",
    )
    add_fig(
        doc,
        "fig6_seeds.png",
        "Figure S3. AdK seed locations versus round (same as main-text Figure 6).",
    )
    add_fig(
        doc,
        "fig7_explore_vs_target.png",
        "Figure S4. Coverage versus target occupancy (same as main-text Figure 7). Exploration "
        "methods and MOAS occupy different quadrants.",
    )

    add_h(doc, "S8. Parameter sensitivity (not yet run)", 1)
    add_p(
        doc,
        "The outline lists SI figures for objective-weight sensitivity, seed-number sensitivity, "
        "and diversity-constraint sensitivity. Those campaigns have not been launched. They "
        "require new adaptive MD, not post-processing. Until they exist, this section is a "
        "placeholder: default weights are equal percentiles; default seeds per round are 6; "
        "diversity is the greedy exclusion radius used in stage_*_discover.py.",
        first_line=False,
        align="justify",
    )

    add_h(doc, "S9. TAPS on CLN025 (additional comparison)", 1)
    add_p(
        doc,
        "TAPS is a target-aware adaptive method used in earlier CLN025 work in this repository. "
        "It is not a main-text baseline. Under the same 82 ns folded-discovery protocol it hit "
        "the RMSD < 0.25 nm window in 3/3 replicates and committed in 1/3 (seed 1 at 80.2 ns). "
        "Occupancies were 0.24%, 0.67%, and 0.09%. This is the canonical transient-encounter "
        "example in Figure 2A: a fast first hit that does not become persistent folded sampling. "
        "MOAS on the same protein committed in 3/3 with occupancy 4.0–6.8%.",
        first_line=False,
        align="justify",
    )
    taps_rows = []
    with (ROOT / "tables" / "n3_metrics.csv").open(encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            if rec["method"] != "TAPS":
                continue
            taps_rows.append(
                [
                    rec["tag"],
                    rec["rep"],
                    fmt_ns(rec["hit_ns"]),
                    fmt_ns(rec["commit_ns"]),
                    fmt_pct(rec["occupancy"]),
                ]
            )
    add_table(
        doc,
        ["Tag", "Rep", "Hit (ns)", "Commit (ns)", "Occupancy (%)"],
        taps_rows,
    )
    add_caption(doc, "Table S5. CLN025 TAPS replicates (supplementary only).")

    add_h(doc, "S10. Occupancy densities", 1)
    add_fig(
        doc,
        "fig4_occupancy.png",
        "Figure S5. Occupancy bars and CV densities (same as main-text Figure 4).",
    )
    add_fig(
        doc,
        "fig3_benchmark.png",
        "Figure S6. Cross-system committed-success matrix (same as main-text Figure 3).",
    )
    add_fig(
        doc,
        "fig1_workflow.png",
        "Figure S7. MOAS workflow schematic (same as main-text Figure 1), included so the SI "
        "can be read on its own.",
    )

    add_h(doc, "S11. Campaign tags", 1)
    add_p(
        doc,
        "CLN025 Random: moas_random, moas_s1_random, moas_s2_random. LAST: discover_last, "
        "discover_s1_last, discover_s2_last. Least-counts: discover_lc, discover_s1_lc, "
        "discover_s2_lc. kNN-AS: discover_knn, discover_s1_knn, discover_s2_knn. MOAS: "
        "moas_static, moas_s1_static, moas_s2_static. TAPS: discover_taps, discover_s1_taps, "
        "discover_s2_taps.",
        first_line=False,
        align="justify",
    )
    add_p(
        doc,
        "AdK seed 0: adk_random, adk_last, adk_lc, adk_knn, adk_static. Seed 1: adk_s1_*. "
        "Seed 2: adk_s2_*. Ablation: adk_nov, adk_bnd, adk_tgt, adk_novbnd, adk_novtgt, adk_bndtgt.",
        first_line=False,
        align="justify",
    )
    add_p(
        doc,
        "MBP analogously mbp_*, mbp_s1_*, mbp_s2_*. Ablation: mbp_nov, mbp_bnd, mbp_tgt, "
        "mbp_novbnd, mbp_novtgt, mbp_bndtgt. Histories for campaigns that lived on "
        "lan55 are copied under paper/data/hist_55.",
        first_line=False,
        align="justify",
    )

    add_h(doc, "S12. What is deliberately excluded", 1)
    add_p(
        doc,
        "The lan55 AdK 1000 ns production tagged adk-r1 belongs to another manuscript and is "
        "not included in any table or figure here. CLN025 moas_dynamic / moas_pareto / seed-3 "
        "LAST-LC-TAPS campaigns exist on disk but are not part of the n = 3 main comparison. "
        "Alanine dipeptide work in taps-gromacs is unrelated.",
        first_line=False,
        align="justify",
    )

    doc.save(OUT_SI)
    print("wrote", OUT_SI)


if __name__ == "__main__":
    build_manuscript()
    build_si()
