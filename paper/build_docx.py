#!/usr/bin/env python3
"""Build manuscript and SI Word drafts with embedded figures."""

from __future__ import annotations

import csv
import os
import tempfile
import time
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


def save_watched(doc, path: Path) -> None:
    """Atomic save so Cursor's Office Viewer file watcher reloads the open tab."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".docx", dir=path.parent)
    os.close(fd)
    tmp_path = Path(tmp)
    try:
        doc.save(str(tmp_path))
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    time.sleep(0.25)
    os.utime(path, None)


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


def add_p_markup(doc, text, *, size=11, space_after=8, first_line=True, align="left"):
    """Justified body paragraph; **...** becomes bold."""
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_after = Pt(space_after)
    pf.space_before = Pt(0)
    pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    if first_line:
        pf.first_line_indent = Cm(0.74)
    if align == "justify":
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    elif align == "center":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pf.first_line_indent = Cm(0)
    for i, part in enumerate(text.split("**")):
        if not part:
            continue
        run = p.add_run(part)
        set_run_font(run, size=size, bold=(i % 2 == 1))
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
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_after = Pt(8)
    pf.space_before = Pt(0)
    pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    pf.first_line_indent = Cm(0.74)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    chunks = [
        (
            "Adaptive sampling is widely used to accelerate molecular dynamics simulations of "
            "rare protein conformational changes, yet its success is often evaluated by the first "
            "time a trajectory enters a predefined target window. A first encounter, however, "
            "does not establish that the target state has been sampled: a trajectory may briefly "
            "enter the target region and rapidly leave it. We therefore distinguish ",
            False,
        ),
        ("first hit", True),
        (", ", False),
        ("committed visit", True),
        (", and ", False),
        ("target-basin occupancy", True),
        (
            " as measures of encounter, stabilization, and persistent sampling, respectively. "
            "We introduce ",
            False,
        ),
        ("multi-objective adaptive sampling (MOAS)", True),
        (
            ", which ranks candidate seeds according to novelty, boundary exploration, and "
            "target proximity using equal percentile ranks with a diversity constraint. MOAS was "
            "evaluated against matched Random, LAST, least-counts, and kNN-AS campaigns on "
            "chignolin folding, adenylate kinase open-to-closed transition, and apo "
            "maltose-binding protein domain closure. Across these systems, evaluating campaigns "
            "by committed visits and target-basin occupancy revealed differences that were not "
            "captured by first-hit times alone. MOAS achieved committed sampling in all three "
            "independent replicates for each benchmark system and generally produced sustained "
            "target-basin occupancy, while exploration-oriented methods could achieve early "
            "target encounters without establishing persistent sampling. Importantly, LAST also "
            "performed well on specific systems, including complete commitment across the "
            "chignolin replicates and high occupancy in one MBP campaign. These results support "
            "a broader evaluation framework in which adaptive sampling of target states is "
            "assessed by committed and persistent sampling rather than first encounter alone.",
            False,
        ),
    ]
    for text, bold in chunks:
        run = p.add_run(text)
        set_run_font(run, size=11, bold=bold)

    add_h(doc, "1. Introduction", 1)
    add_p_markup(
        doc,
        "Molecular dynamics (MD) simulations provide structural, thermodynamic, and kinetic "
        "information that is difficult to obtain from static structures, but biologically "
        "relevant conformational transitions often occur on timescales far beyond those "
        "accessible to a single unbiased trajectory. Adaptive sampling addresses this limitation "
        "by repeatedly harvesting configurations from previously visited trajectories, ranking "
        "candidate configurations, and launching short simulations from selected seeds. Most "
        "adaptive strategies therefore focus on **where to sample next**—for example, poorly "
        "explored, low-density, or frontier regions of conformational space. However, for "
        "target-state sampling, where a simulation campaign aims to establish a particular "
        "conformational state rather than merely discover new regions, the definition of a "
        "successful sampling event is equally important.",
        align="justify",
    )
    add_p_markup(
        doc,
        "A first encounter with a target region does not necessarily indicate that the target "
        "state has been sampled. We distinguish three progressively stronger outcomes: "
        "**first hit**, the first entry into a predefined target window; **committed visit**, "
        "continuous residence within that window for a specified minimum duration; and "
        "**target-basin occupancy**, the fraction of the total simulation budget spent in the "
        "target region. First hit measures discovery, whereas commitment and occupancy measure "
        "stabilization and sustained sampling. An exploration-oriented strategy can therefore "
        "achieve an early first hit or high conformational coverage while contributing little "
        "persistent sampling of the target state. We argue that these quantities should be "
        "treated as complementary campaign outcomes rather than collapsed into a single measure "
        "of adaptive-sampling efficiency.",
        align="justify",
    )
    add_p_markup(
        doc,
        "This distinction also defines the scope of the present benchmark. We compare methods "
        "that share the same seed-selection framework—an initial unbiased ensemble, short "
        "trajectories, pooling of visited configurations, and ranking of candidate "
        "seeds—including Random, least-counts, LAST, and kNN-AS. These methods emphasize "
        "unbiased restarting, under-sampled regions, frontier exploration, or low-density "
        "exploration, respectively. Other rare-event approaches, including weighted-ensemble "
        "methods, adaptive Markov-state-model schemes, reinforcement-learning approaches, and "
        "enhanced-sampling or path-based methods, address related rare-event problems but alter "
        "the sampling architecture or introduce additional statistical or biasing machinery; "
        "they are therefore not treated as matched seed-selection baselines here.",
        align="justify",
    )
    add_p_markup(
        doc,
        "Here we introduce **multi-objective adaptive sampling (MOAS)**, which combines novelty, "
        "LAST-style boundary exploration, and target proximity through equal percentile ranks "
        "with a diversity constraint. Rather than optimizing first-hit time alone, we evaluate "
        "adaptive campaigns using committed visits and target-basin occupancy as the primary "
        "endpoints, with first hit and conformational coverage retained as discovery diagnostics. "
        "MOAS is benchmarked against Random, LAST, least-counts, and kNN-AS under matched "
        "simulation budgets on CLN025 folding, adenylate kinase open-to-closed transition, and "
        "apo maltose-binding protein domain closure (n = 3). Our working hypothesis is that "
        "combining continued exploration with explicit target proximity can convert transient "
        "target encounters into committed and persistent target-state sampling, without assuming "
        "that any single adaptive strategy is universally optimal across different sampling "
        "objectives.",
        align="justify",
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
        "The protocol is summarized with CLN025 and AdK in Table 1.",
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
        "Table 1. Simulation protocol. Closed windows for AdK and MBP are side-aware cuts "
        "between the open and closed reference structures. CLN025 starts unfolded; AdK and MBP "
        "start from the open apo crystal conformation.",
    )

    add_h(doc, "2.10 Baseline methods", 2)
    add_p(
        doc,
        "Every system was run with five methods under identical initialization, short-MD length, "
        "seed count, diversity rule, and budget. The inclusion criterion is that a method can "
        "replace only the ranking function inside the protocol of Sections 2.2–2.9; weighted "
        "ensemble, adaptive MSM, and reinforcement-learning samplers change the engine and are "
        "not used as matched controls. Random assigns uniform scores to eligible "
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
        "may hit and still fail to remain in the basin. First hit answers whether the window was "
        "encountered. It does not answer whether the target state was sampled.",
        align="justify",
    )

    add_h(doc, "2.12 Committed visit", 2)
    add_p(
        doc,
        "A committed visit is the primary endpoint. With frame spacing Δt, it is the first time "
        "a contiguous sojourn inside W reaches duration τ (τ = 40 ps on CLN025; 200 ps on AdK "
        "and MBP). Equivalently, a committed visit occurs when the longest contiguous sojourn "
        "in W is at least τ:",
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
        "first hit but never meets this sojourn is classified as transient-only. The production "
        "values of τ are system-specific and are not treated as universal constants. To test "
        "whether ranking by committed sampling depends on that choice, the same pooled "
        "trajectories were re-scored at neighboring thresholds without additional MD (CLN025: "
        "20, 40, 60, and 80 ps; AdK and MBP: 100, 200, 300, and 500 ps). Committed fraction, "
        "time-to-commit, and occupancy at each τ are reported in Supporting Information "
        "Figure S1 and Table S6. Occupancy is independent of τ by construction.",
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
        "state. Occupancy is a time average of 1_W and therefore depends on both how often a "
        "trajectory enters W and how long it remains. To examine the same trajectories without "
        "choosing τ, each contiguous sojourn inside W is retained as a residence time T, using "
        "the production duration definition of Section 2.12. The empirical survival P(T ≥ t) is "
        "averaged over the n = 3 campaigns (a campaign with no visit contributes 0), and the "
        "longest sojourn of each campaign is reported (Supporting Information Figure S2A–F and "
        "Table S7). A committed visit is the event that the longest sojourn is at least τ, so "
        "commitment is one slice of the residence-time distribution rather than a separate "
        "success definition. Separately, occupancy is recomputed under neighboring definitions "
        "of W—CLN025 RMSD cutoffs 0.15–0.40 nm, AdK LID/NMP margins of ±4° and ±8° about the "
        "production rectangle, and MBP tighter and looser domain-distance / hinge-angle "
        "windows—to test whether the occupancy ranking is an artifact of the production window "
        "(Figure S2G–I and Table S8). Coverage of the 24 × 24 CV histogram is stored as an "
        "exploration diagnostic and is not used as a success criterion.",
        align="justify",
    )

    add_h(doc, "2.14 Statistical analysis", 2)
    add_p(
        doc,
        "Main comparisons use n = 3 independent adaptive campaigns per method and system. We "
        "report replicate counts (for example 3/3 committed), per-replicate hit and commit times, "
        "and median occupancy with the interquartile range. Time to committed visit is summarized "
        "with Kaplan–Meier estimators of the probability of not yet committing; campaigns that "
        "never committed are right-censored at the campaign budget. Uncertainty on the Kaplan–Meier "
        "median time-to-commit, the commitment probability, and the median occupancy is reported "
        "as 95% percentile bootstrap intervals from 10,000 resamples of the n = 3 campaigns. "
        "When fewer than half of the campaigns in a sample committed, the Kaplan–Meier median is "
        "not reached. With n = 3 the bootstrap interval for a 0/3 or 3/3 proportion is degenerate "
        "at 0 or 1, and the interval for a 1/3 or 2/3 proportion spans [0, 1]; occupancy and "
        "Kaplan–Meier medians remain informative. Ablation of objective combinations is n = 1 "
        "on AdK and MBP.",
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
        "(Figure 2C). Conversion of a hit into a committed visit was complete for LAST and "
        "least-counts on CLN025, and for MOAS on every system; it was incomplete for several "
        "LAST, least-counts, and kNN-AS campaigns on AdK and MBP (Figure 2D). "
        "A trajectory can therefore have a short first-hit time and essentially no useful "
        "target-state sampling. Subsequent sections do not ask which method is fastest. They "
        "ask how campaigns read once success is defined as a committed visit and as "
        "target-basin occupancy, not as first hit alone.",
        align="justify",
    )
    add_fig(
        doc,
        "fig2_hit_vs_commit.png",
        "Figure 2. First-hit detection does not establish successful target-state sampling. "
        "(A) CLN025 rolling occupancy of the folded window (2 ns kernel) for TAPS, LAST, and "
        "MOAS (seed 0); filled area is the same trace, diamonds mark committed visits. "
        "(B) AdK rolling closed occupancy: Random hits at 83 ns and escapes; MOAS remains in "
        "the basin. (C) First-hit time versus occupancy on each protein; open symbols did not "
        "hit (plotted at the budget). (D) Fraction of hits that later committed; × marks "
        "method–protein pairs with no first hit. TAPS is shown only for CLN025.",
    )

    add_h(doc, "3.2 Committed sampling across three conformational transitions", 2)
    add_p(
        doc,
        "The evaluation criteria of Section 3.1 were applied to three conformational transitions "
        "of increasing scale: CLN025 folding from an unfolded start (82 ns budget; commit ≥ 40 ps "
        "in RMSD < 0.25 nm), apo AdK open-to-closed (200 ns; both LID/NMP angles in the closed "
        "window ≥ 200 ps), and apo MBP domain closure (1 μs; domain distance and hinge angle in "
        "the closed window ≥ 200 ps). Each method used the same initialization, short-MD length, "
        "six seeds per round, and n = 3 independent campaigns (Table 1).",
        align="justify",
    )
    add_p(
        doc,
        "Committed-replicate counts are summarized in Figure 4A–C. MOAS committed in 3/3 "
        "campaigns on every protein. Random committed in 0/9 campaigns. LAST committed in 3/3 "
        "CLN025 runs, 0/3 AdK runs, and 1/3 MBP runs. Least-counts committed in 3/3, 2/3, and "
        "1/3. kNN-AS committed in 1/3, 1/3, and 2/3. Per-replicate outcomes are classified in "
        "Figure 4F as no hit, hit only, or committed: the three levels of the evaluation "
        "framework (no encounter, encounter without stabilization, and committed sampling). "
        "The pattern is not that MOAS is always the first to hit, and it is not that LAST failed. "
        "LAST and least-counts also committed in 3/3 CLN025 campaigns. What differs across "
        "proteins is whether a frontier or least-counts objective, built for discovery, also "
        "yields a committed visit. MOAS, which mixes those exploration ranks with target "
        "proximity, recorded a committed visit on every replicate of every transition. That is "
        "a statement about the sampling objective, not a ranking of methods by speed.",
        align="justify",
    )
    add_p(
        doc,
        "Time-to-commit is shown as Kaplan–Meier curves of the probability of not yet committing "
        "(Figure 3). Crosses mark campaigns that reached the budget without a committed visit "
        "and are right-censored there. On CLN025, both LAST and MOAS fall to zero: all three "
        "replicates of each method committed. Random remains at one on every protein. LAST stays "
        "high on AdK and MBP, where it did not reach three commits. Least-counts and kNN-AS "
        "occupy intermediate paths that depend on the system. Table 2 reports the Kaplan–Meier "
        "median time-to-commit, the commitment probability, and the median occupancy, each with "
        "a 95% bootstrap interval. MOAS medians are 36.1 ns on CLN025 [34.1, 40.1], 105.7 ns on "
        "AdK [103.4, 192.3], and 442.8 ns on MBP [216.8, 503.5]. Occupancy intervals for MOAS do "
        "not overlap those of Random on any system. Those intervals are not a claim that MOAS "
        "is uniformly faster than LAST. Where fewer than two of three campaigns committed, the "
        "Kaplan–Meier median is not reached.",
        align="justify",
    )
    add_fig(
        doc,
        "fig3_km.png",
        "Figure 3. Kaplan–Meier estimates of the probability of not yet committing (n = 3). "
        "(A) CLN025, (B) AdK, (C) MBP. Crosses are campaigns that never committed, censored at "
        "the budget. The dotted line is S(t) = 0.5.",
    )
    boot_rows = []
    with (ROOT / "tables" / "bootstrap_metrics.csv").open(encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            med = rec["median_ttc"]
            if med in ("", None):
                med_s = "n.r."
            else:
                med_s = f"{float(med):.1f} [{float(rec['median_lo']):.1f}, {float(rec['median_hi']):.1f}]"
            boot_rows.append(
                [
                    rec["system"],
                    rec["method"],
                    med_s,
                    f"{float(rec['p_commit']):.2f} [{float(rec['p_lo']):.2f}, {float(rec['p_hi']):.2f}]",
                    f"{float(rec['occupancy']):.2f} [{float(rec['occ_lo']):.2f}, {float(rec['occ_hi']):.2f}]",
                ]
            )
    add_table(
        doc,
        [
            "System",
            "Method",
            "KM median ttc (ns)",
            "P(commit)",
            "Occupancy (%)",
        ],
        boot_rows,
    )
    add_caption(
        doc,
        "Table 2. Bootstrap 95% percentile intervals (10,000 resamples of n = 3). "
        "KM median ttc is the Kaplan–Meier median time-to-commit; n.r., not reached "
        "(S(t) never falls to 0.5). Occupancy is the median across replicates. With n = 3, "
        "bootstrap intervals for a 0/3 or 3/3 proportion are degenerate.",
    )
    add_p(
        doc,
        "Among campaigns that committed, the corresponding point estimates match Figure 4D. On "
        "CLN025 the three methods that committed in 3/3 did so at 36.1 ns (MOAS), 46.4 ns (LAST), "
        "and 68.6 ns (least-counts). Those times are not ranked: MOAS is not claimed to be faster "
        "than LAST. On MBP, LAST’s single success was at 320 ns, earlier than the MOAS median of "
        "442.8 ns, so LAST’s Kaplan–Meier median is not reached. kNN-AS on MBP committed later "
        "(Kaplan–Meier median 837 ns). Target-basin occupancy for all replicates is shown in "
        "Figure 4E and is examined in Section 3.3.",
        align="justify",
    )
    add_fig(
        doc,
        "fig4_benchmark.png",
        "Figure 4. Committed sampling across three conformational transitions (n = 3). "
        "(A–C) Committed replicates out of three on CLN025, AdK, and MBP. The filled marker is "
        "the observed count; the open marker is complete success (3/3), so the gap is campaigns "
        "that did not commit. "
        "(D) Time to committed visit (log scale); × marks campaigns that never committed "
        "(plotted at the budget). (E) Target-basin occupancy. (F) Per-replicate classification: "
        "no hit, hit only, or committed (no encounter, encounter, and stabilization).",
    )
    add_p(
        doc,
        "Because τ is a protocol choice, the same trajectories were re-scored at neighboring "
        "sojourn thresholds (Supporting Information Figure S1 and Table S6). No additional MD "
        "was run. On CLN025, MOAS remained 3/3 committed from 20 to 80 ps. LAST and least-counts "
        "were 3/3 at 20–40 ps and dropped to 2/3 and 1/3 at 60–80 ps; kNN-AS fell from 2/3 at "
        "20 ps to 1/3 at the production 40 ps and 0/3 at 60–80 ps; TAPS was 3/3 only at 20 ps "
        "(1/3 thereafter); Random never committed. On AdK, MOAS was 3/3 at 100–300 ps and 2/3 "
        "at 500 ps; LAST was 0/3 at every τ; least-counts was 2/3 until 300 ps and 1/3 at 500 ps; "
        "kNN-AS was 1/3 throughout; Random committed in 1/3 only at 100 ps. On MBP, MOAS was 3/3 "
        "from 100 to 500 ps; LAST was 2/3 at 100 ps and 1/3 thereafter; least-counts 1/3; kNN-AS "
        "2/3 until 300 ps and 1/3 at 500 ps; Random 1/3 only at 100 ps. Median time-to-commit for "
        "MOAS moved little except a modest delay on CLN025 at 60–80 ps (36.1 to 40.1 ns) and on "
        "AdK at 500 ps (105.7 to 121.8 ns among the two remaining commits). Occupancy does not "
        "depend on τ: MOAS medians remained 5.25% (CLN025), 14.85% (AdK), and 37.15% (MBP), above "
        "the exploration methods at every threshold. Thus the ranking of MOAS versus Random, "
        "LAST, least-counts, and kNN-AS is not an artifact of the production 40 ps / 200 ps "
        "choice.",
        align="justify",
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
        "as shown in Figure 5A–C. The AdK MOAS replicate that committed only at 192 ns remained "
        "at 0.72% occupancy: commitment without large occupancy is possible, which is why the "
        "two quantities are reported separately. LAST’s CLN025 occupancy median was 1.66%, "
        "against 5.25% for MOAS, with both methods committing in 3/3. LAST’s MBP median was "
        "0.02%, despite one replicate that reached 26% after committing at 320 ns. That "
        "replicate shows that LAST is capable of substantial occupancy when a frontier trajectory "
        "enters and remains in the basin; it is not a failed method. Median occupancy still "
        "differs because the other LAST MBP campaigns did not occupy the closed window. kNN-AS "
        "medians were 0.14%, ~0%, and 0.14% on the three systems. Bootstrap 95% intervals on "
        "these occupancy medians are in Table 2.",
        align="justify",
    )
    add_p(
        doc,
        "CV densities show where that occupancy sits. On AdK, where LAST did not commit, density "
        "remains in the open LID–NMP cloud, whereas MOAS accumulates inside the closed window "
        "(Figure 5D). On MBP, pooled LAST density stays near the open reference even though one "
        "replicate occupied the closed basin at 26% (Figure 5E), because the other two campaigns "
        "did not. Restricting the comparison to campaigns that recorded "
        "a first hit does not remove the occupancy gap (Figure 5F). Hitting the window is "
        "therefore not the event that distinguishes the methods; remaining in the basin is. "
        "We describe this as an association between committed visits and sustained occupancy, "
        "not as a claim that commitment causally produces occupancy in the absence of further "
        "analysis, and not as a claim that LAST cannot occupy the target.",
        align="justify",
    )
    add_fig(
        doc,
        "fig5_occupancy.png",
        "Figure 5. Committed visits are associated with sustained target-basin occupancy. "
        "(A–C) Occupancy of three independent replicates (circles), with the median (diamond) and min–max range. (D) AdK "
        "LID–NMP density for LAST (blue) and MOAS (red); dashed lines mark the closed window. "
        "(E) Analogous MBP domain-distance / hinge-angle density. (F) Occupancy restricted to "
        "campaigns that recorded a first hit.",
    )
    add_p(
        doc,
        "Occupancy is the time average of the indicator of W. It therefore mixes how often a "
        "trajectory enters the window with how long it stays. The latter is the residence-time "
        "distribution of contiguous sojourns (Supporting Information Figure S2A–C). A committed "
        "visit is the event that at least one sojourn exceeds τ, equivalently that the longest "
        "sojourn exceeds τ (Figure S2D–F). Typical visits remain short for every method (median "
        "sojourn 2–20 ps); the distinction is the tail. The median longest sojourn was 0.34 ns "
        "for MOAS on CLN025, against 0.15 ns for LAST, 0.05 ns for least-counts, 0.02 ns for "
        "kNN-AS, 0.03 ns for TAPS, and <0.01 ns for Random (Table 3). On AdK the corresponding "
        "medians were 1.82 ns (MOAS) and 0.33 ns (least-counts); Random, LAST, and kNN-AS had "
        "median longest sojourns of 0 because at least two of three campaigns never entered or "
        "never stayed (one kNN-AS replicate reached 9.8 ns). On MBP they were 36.5 ns (MOAS), "
        "0.33 ns (kNN-AS), 0.12 ns (LAST), 0.07 ns (least-counts), and 0 (Random). The production "
        "threshold is one horizontal cut through Figure S2D–F; the ranking of longest sojourns "
        "does not require choosing that cut.",
        align="justify",
    )
    add_p(
        doc,
        "The same occupancy ranking is recovered under neighboring definitions of W "
        "(Figure S2G–I). Tightening the CLN025 RMSD cutoff from 0.25 to 0.20 nm lowers every "
        "occupancy but leaves MOAS highest (0.79% versus 0.01% for LAST). Widening to 0.30 or "
        "0.40 nm does likewise (MOAS 12.4% and 31.9%; LAST 6.0% and 16.5%). On AdK, expanding "
        "or shrinking the LID/NMP rectangle by 4–8° does not produce a ranking in which an "
        "exploration method overtakes MOAS at the production window or looser; at −8° the "
        "window is empty for all methods. On MBP, a tighter closed window still retains 17.1% "
        "MOAS occupancy against ≤0.02% for the other methods. Occupancy is therefore not an "
        "artifact of the particular production rectangle.",
        align="justify",
    )
    res_rows = []
    with (ROOT / "tables" / "residence_time_summary.csv").open(encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            if rec["method"] == "TAPS":
                continue
            mx = rec["median_max_rt"]
            if mx in ("", None):
                longest = "—"
            else:
                x = float(mx) / 1000.0
                longest = f"{x:.3f}" if x < 0.1 else f"{x:.2f}"
            res_rows.append(
                [
                    rec["system"],
                    rec["method"],
                    longest,
                    f"{float(rec['median_occupancy']):.2f}",
                ]
            )
    add_table(
        doc,
        ["System", "Method", "Median longest residence (ns)", "Occupancy (%)"],
        res_rows,
    )
    add_caption(
        doc,
        "Table 3. Threshold-free residence and occupancy (n = 3). Median longest residence is "
        "the median, over three campaigns, of each campaign’s longest contiguous sojourn in the "
        "production window W (0 if the campaign never entered). Occupancy is the production "
        "f_W of Section 2.13. Full sojourn survivals and neighboring-window occupancies are "
        "Supporting Information Figure S2 and Tables S7–S8.",
    )

    add_h(doc, "3.4 Seed selection reallocates from exploration to target-state sampling", 2)
    add_p(
        doc,
        "Seed selection is the policy that implements the sampling objective. Figure 6 asks how "
        "that policy is used over time on AdK, not which method is fastest. Each map is the same "
        "LID–NMP plane. The shaded region is the closed-state target window (LID < 114.4°, "
        "NMP > 41.8°). Selected seeds are colored by adaptive round, from early (blue) to late "
        "(red). Random, LAST, and MOAS are seed-0 campaigns; kNN-AS is the AdK campaign for which "
        "per-round seed coordinates were archived (replicate 2).",
        align="justify",
    )
    add_p(
        doc,
        "Random seeds remain in the open cloud through late rounds (Figure 6A). LAST seeds track "
        "the expanding frontier of the visited ensemble (Figure 6B, dashed contour of the sampled "
        "cloud). kNN-AS spreads into low-density regions and does not concentrate in the closed "
        "window (Figure 6C). MOAS seeds begin in the open cloud in rounds 1–5, approach the window "
        "in rounds 6–10, and enrich the closed basin in rounds 11–15 (Figure 6D). The dark line in "
        "D is the centroid of the six seeds selected in each round: exploration, then transition, "
        "then target-directed sampling, rather than a jump of points from left to right.",
        align="justify",
    )
    add_p(
        doc,
        "That sequence is quantified in Figure 6E–F. The fraction of selected seeds inside the "
        "target window is not itself the objective: a target-only rule would raise it immediately. "
        "The complementary coordinate is the median Euclidean distance, in LID–NMP space, from "
        "the six seeds to the closed reference. MOAS distance decreases over rounds while the "
        "in-window fraction rises late. Random, LAST, and kNN-AS do not show that reallocation. "
        "The policy therefore shifts from exploration toward target-state sampling; it does not "
        "dump seeds into the window from the first round. Figure 6G reconstructs the mean "
        "novelty, boundary, and target percentile ranks of those six MOAS seeds relative to "
        "the candidate pool of each round. The mixing weights never change. Novelty percentile "
        "of selected seeds remains near one in every round, so exploration is not switched off. "
        "Target percentile is already high in the transition, when the closed basin is still "
        "rare among candidates, and then declines as the pool itself occupies that basin. A "
        "relative rank cannot stay exclusive once many windows sit near the target. "
        "Reallocation is therefore a change in the pool, not a change in the weights.",
        align="justify",
    )
    add_fig(
        doc,
        "fig6_seeds.png",
        "Figure 6. Temporal evolution of seed selection on AdK: from exploration to "
        "target-state sampling. (A–D) LID–NMP maps for Random, LAST, kNN-AS (replicate 2), and "
        "MOAS. Grey hexbin: sampled density. Points: selected seeds colored by adaptive round "
        "(early → late). Shaded rectangle: closed-state target window (LID < 114.4°, NMP > 41.8°). "
        "LAST (B) includes a dashed contour of the visited cloud. MOAS (D) includes the centroid "
        "trajectory of the six seeds in each round. (E) Fraction of selected seeds inside the "
        "target window versus round. (F) Median target distance of those seeds versus round. "
        "(G) Mean novelty, boundary, and target percentile ranks of the six MOAS seeds, "
        "recomputed from that round’s candidate pool; the dotted line is the equal-weight mix. "
        "Shaded bands mark exploration (R1–R5), transition (R6–R10), and target-directed sampling "
        "(R11–R15). A late rise in (E) with a gradual drop in (F) indicates reallocation toward "
        "the basin. (G) shows that this is not a change of weights: novelty rank stays high, "
        "and target rank falls once the pool is itself near the basin.",
    )

    add_h(doc, "3.5 Contribution of individual objectives to MOAS sampling behavior", 2)
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
        "(Figure 7A, C). Occupancy-versus-time traces show that the target-containing mixes "
        "accumulate closed-window frames after commitment, whereas novelty and boundary remain "
        "near 1% after a first hit. Restricting occupancy to frames after the committed visit "
        "gives 28.6% (target), 30.0% (novelty+target), 27.5% (full MOAS), and 15.4% "
        "(boundary+target). Target proximity is therefore strongly associated with commitment on "
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
        "occupancy (Figure 7B–D). No single- or two-term mix matches that occupancy. After "
        "commitment, full MOAS spends 49.9% of remaining frames in the closed basin, compared "
        "with 9.9% (boundary), 13.5% (target), and 2.9% (novelty+target); the hit-to-commit "
        "interval is 107 ns for full MOAS versus 404 ns for novelty+target, which converts "
        "late and still does not occupy the basin. Exploration without a target term either "
        "fails to hit or, if it commits, occupies far less of the 1 μs budget than the "
        "three-term mix; a target term without the full exploration mix can convert an "
        "encounter into a late commit and still leave almost no ensemble in the closed basin. "
        "The two classes of term are complementary on this larger transition.",
        align="justify",
    )
    add_fig(
        doc,
        "fig7_ablation.png",
        "Figure 7. Contribution of individual MOAS objectives (n = 1). (A, B) Cumulative "
        "target-basin occupancy versus simulation time on AdK and MBP; diamonds mark the "
        "committed visit. Dashed lines are single-term mixes, dash-dot two-term mixes, and "
        "the solid red line is full MOAS. (C) Occupancy versus time to commit as a fraction "
        "of the budget (open markers did not commit). (D) The same campaigns on the "
        "three-objective simplex (Novelty–Boundary–Target); marker area is proportional to "
        "occupancy, filled markers committed (circles, AdK; diamonds, MBP).",
    )

    add_h(doc, "3.6 Exploration coverage and target-state occupancy represent complementary sampling objectives", 2)
    add_p(
        doc,
        "Figure 8A–C place every n = 3 campaign on two axes: the filled fraction of a 24 × 24 CV "
        "histogram (coverage) and target-basin occupancy. LAST, kNN-AS, and least-counts occupy "
        "the high-coverage, low-occupancy region on AdK and MBP. That placement is consistent "
        "with an exploration objective: those methods visit more histogram bins. MOAS occupies "
        "the high-occupancy side at comparable or slightly lower coverage. CLN025 coverage is "
        "compressed for all methods because the peptide fills few bins of the same 24 × 24 grid; "
        "occupancy still ranks MOAS above LAST (medians 5.25% versus 1.66%), while LAST itself "
        "is well above Random and kNN-AS. The two axes are different sampling objectives, not "
        "proxies for one another.",
        align="justify",
    )
    add_p(
        doc,
        "Exploration-oriented methods and MOAS can therefore be compared in one frame without "
        "treating either axis as a universal score. If the scientific question is whether new "
        "conformational space was visited, coverage and frontier scores remain appropriate. If "
        "the question is whether a predefined target state was established as a sampled basin, "
        "committed visit and occupancy are the relevant endpoints. The two questions are two "
        "definitions of success. Changing the definition changes which method looks successful. "
        "Adaptive sampling should be evaluated not only by how much of conformational space is "
        "explored, but also by whether the intended target state is sampled in a committed and "
        "sustained manner.",
        align="justify",
    )
    add_fig(
        doc,
        "fig8_explore_vs_target.png",
        "Figure 8. Exploration coverage and target-state occupancy are complementary sampling "
        "objectives. Each panel is one protein; each point is one n = 3 campaign. Lines join "
        "each campaign to the method median (diamond). Coverage is the filled "
        "fraction of a 24 × 24 CV histogram. Occupancy is the target-window fraction. MOAS "
        "separates on the occupancy axis; LAST, kNN-AS, and least-counts separate on coverage "
        "for AdK and MBP.",
    )

    add_h(doc, "4. Discussion", 1)
    add_p_markup(
        doc,
        "The central result of this study is not that MOAS universally accelerates adaptive "
        "sampling, but that **first-hit time alone does not adequately define successful sampling "
        "of a target conformational state**. A trajectory can enter a predefined target window "
        "early, leave it rapidly, and contribute almost no subsequent sampling to that state. "
        "The distinction among first hit, committed visit, and target-basin occupancy therefore "
        "separates three different levels of outcome: encounter, stabilization, and sustained "
        "sampling. Figure 2 illustrates why these quantities should not be collapsed into a "
        "single measure. First-hit time remains useful for describing how rapidly a target "
        "region is encountered, but when the scientific objective is to obtain an ensemble of a "
        "metastable target state, successful sampling must also account for whether the "
        "trajectory remains in that state and accumulates meaningful residence time. This "
        "distinction provides the basis for the evaluation framework used throughout this study.",
        align="justify",
    )
    add_p_markup(
        doc,
        "MOAS was designed to align seed selection with this definition of success while "
        "retaining the exploratory behavior of adaptive sampling. Its three components—novelty, "
        "LAST-style boundary exploration, and target proximity—address complementary aspects of "
        "the sampling problem. Novelty and boundary scores promote exploration of poorly "
        "represented or frontier regions, whereas target proximity provides an explicit mechanism "
        "for directing sampling toward the basin of interest. Equal percentile normalization "
        "places these otherwise incommensurate scores on a common relative scale, while the "
        "diversity constraint prevents the selected seeds from collapsing onto a single local "
        "region. Importantly, the apparent shift from exploration toward target-directed "
        "sampling does not require time-dependent weights. As the sampled ensemble evolves, the "
        "relative ranks of candidate configurations change, and configurations near the target "
        "can become increasingly competitive with frontier configurations. Figure 6 illustrates "
        "this behavior: early selection remains distributed across the open-state ensemble, "
        "whereas later rounds become progressively enriched near the target basin. Thus, the "
        "balance between exploration and target-directed sampling emerges from the evolving "
        "candidate pool rather than from an explicitly scheduled change in objective weights. "
        "The ablation results further suggest that target proximity is important for achieving "
        "commitment, whereas retaining exploratory objectives can improve the accumulation of "
        "target-basin occupancy.",
        align="justify",
    )
    add_p_markup(
        doc,
        "The comparison with existing adaptive strategies should therefore be interpreted as a "
        "comparison of **sampling objectives rather than a universal performance ranking**. LAST, "
        "in particular, was not uniformly inferior to MOAS: it achieved commitment in all "
        "CLN025 replicates and produced high occupancy in one MBP campaign. These results are "
        "consistent with the fact that frontier exploration can, depending on the underlying "
        "landscape, naturally lead into and remain within a target basin. Random provides an "
        "unbiased restart reference, least-counts emphasizes under-sampled regions, and both "
        "LAST and kNN-AS favor exploration of poorly represented regions of conformational "
        "space. These strategies are appropriate when the principal question is where the "
        "trajectory has not yet explored. The present results instead address the complementary "
        "question of whether a predefined target state has been sufficiently sampled. MOAS "
        "extends this exploratory framework by adding target proximity, rather than replacing "
        "exploration with purely target-directed selection. The separation between coverage and "
        "occupancy in Figure 8 further emphasizes that exploration and target-state accumulation "
        "are related but distinct objectives.",
        align="justify",
    )
    add_p_markup(
        doc,
        "This distinction also motivates the broader use of **committed sampling as an "
        "evaluation framework**. The framework is applicable whenever the scientific objective "
        "is to accumulate sampling within a defined metastable state rather than merely detect "
        "its existence. Under this framework, first hit represents discovery, whereas a "
        "committed visit and subsequent occupancy represent stabilization and ensemble "
        "accumulation. The commitment threshold should not be regarded as a universal constant. "
        "In the present study, 40 ps was used for CLN025 and 200 ps for AdK and MBP to reflect "
        "differences in the characteristic timescales of the systems; critically, the same "
        "criterion was applied to all methods within each system. Re-scoring the same "
        "trajectories over a neighborhood of τ (Supporting Information Figure S1 and Table S6) "
        "left the ranking of MOAS versus the exploration methods unchanged. MOAS remained the "
        "only method with 3/3 committed replicates on all three proteins at the production "
        "thresholds, and it retained that count at every neighboring τ except AdK at 500 ps "
        "(2/3). Occupancy, which does not depend on τ, preserved the same order. Commitment is "
        "one slice of the residence-time distribution: a committed visit occurs when the longest "
        "sojourn exceeds τ, while occupancy is the time average of those sojourns (Supporting "
        "Information Figure S2A–F and Table 3). Recomputing occupancy under neighboring "
        "definitions of W (Figure S2G–I) left MOAS highest at the production window and at "
        "every looser or moderately tighter cutoff that is still populated. More broadly, "
        "a physically motivated, system-specific commitment criterion can be incorporated into "
        "benchmarks of protein conformational transitions, ligand-linked state changes, enzyme "
        "open/closed dynamics, membrane-protein conformational switching, and other rare-event "
        "problems in which persistence within a target state is scientifically meaningful.",
        align="justify",
    )
    add_p_markup(
        doc,
        "Several limitations define the current scope of the method. First, MOAS assumes a "
        "predefined target basin in CV space and is therefore a target-directed sampler rather "
        "than a method for discovering unknown metastable states. Second, the CVs used here were "
        "selected a priori: Cα-RMSD and Rg for CLN025, LID/NMP angles for AdK, and domain "
        "distance and hinge angle for MBP. The effectiveness of target-directed sampling may "
        "therefore depend on whether these coordinates adequately resolve the relevant "
        "conformational transition. Integration with learned representations, such as "
        "time-lagged or variational embeddings, graph-based features, or Koopman/TICA-type "
        "coordinates, could reduce this dependence. Third, the equal weighting of the three "
        "MOAS objectives is intended as a transparent and reproducible baseline rather than an "
        "optimized universal choice; adaptive weighting based on sampling stage, uncertainty, "
        "target distance, occupancy, or objective redundancy remains to be explored. Finally, "
        "the present benchmark contains three protein systems with three independent campaigns "
        "per main-text method, while the ablation analysis uses single campaigns. These data "
        "establish consistent behavior across the tested systems but do not justify universal "
        "claims about MOAS performance. Larger replicate sets, broader protein classes, and "
        "standardized committed-sampling benchmarks will be needed to determine the generality "
        "and statistical robustness of this framework.",
        align="justify",
    )

    add_h(doc, "5. Conclusions", 1)
    add_p(
        doc,
        "The contribution of this work is a change in what success means for adaptive sampling "
        "of a rare conformational state. First hit records an encounter and is not sufficient "
        "evidence that the target basin has been sampled. A committed visit and persistent "
        "occupancy record whether that basin was established as an ensemble. MOAS operationalizes "
        "that definition by ranking seeds on novelty, boundary exploration, and target proximity, "
        "mixed by equal percentile ranks and subject to a diversity constraint, so that exploration "
        "of poorly sampled regions is kept in play while sampling is progressively directed toward "
        "the intended state. Across CLN025 folding, the AdK open-to-closed transition, and apo MBP "
        "domain closure, this mix was associated with a committed visit in every replicate. LAST "
        "and least-counts achieved the same commit count on CLN025; LAST also produced a "
        "high-occupancy MBP campaign. Those results are not a demonstration that MOAS is faster, "
        "or that it supersedes LAST. They show that an exploration objective and a target-state "
        "sampling objective are different questions, and that the ranking of methods depends on "
        "which question is asked. The same ranking is recovered from the full residence-time "
        "distribution and from occupancy recomputed under neighboring definitions of W. The "
        "practical implication is to score adaptive sampling of "
        "target states by committed residence and persistent occupancy, and to treat exploration "
        "and target-directed stabilization as complementary objectives rather than as a single "
        "performance number.",
        align="justify",
    )

    add_h(doc, "Associated Content", 1)
    add_h(doc, "Supporting Information", 2)
    add_p(
        doc,
        "Simulation parameters (Table S1); replicate-level hit, commit, occupancy, and coverage "
        "(Tables S2–S5); ablation numerics (Table S4); commitment-threshold robustness "
        "(Figure S1, Table S6); residence-time distributions and neighboring-window occupancy "
        "(Figure S2, Tables S7–S8); campaign tags (S11). Ranking code, CV JSON, and commitment "
        "functions corresponding to this article are at https://github.com/liying0128/TAPS "
        "(directory paper/protocol/).",
        first_line=False,
        align="justify",
    )

    add_h(doc, "Data and Software Availability", 1)
    add_p(
        doc,
        "The data underlying this study are available in the published article, the Supporting "
        "Information, and at https://github.com/liying0128/TAPS. The scripts and code used to "
        "generate and analyze the results are in the same repository. Ranking (novelty, LAST "
        "frontier, target proximity, equal-percentile mixing, diversity-constrained seed "
        "selection), CV window definitions, and commitment / occupancy / residence-time "
        "functions are deposited in paper/protocol/. Production adaptive loops are "
        "taps-gromacs/stage13_cln025_discover.py (CLN025), moas-adk/stage_adk_discover.py "
        "(AdK), and moas-mbp/stage_mbp_discover.py (MBP). Machine-readable numerical tables "
        "underlying Figures 2–8 and S1–S2 are in paper/tables/. Custom code is released under "
        "the MIT license. MD was run with open-source GROMACS 2024.3 (production GPUs) and "
        "checked with GROMACS 2025.1, AMBER99SB-ILDN and TIP3P. Python 3 with NumPy was used "
        "for ranking and CV evaluation. Full GROMACS trajectories and checkpoints are not "
        "stored on GitHub (hundreds of GB); they are available from the corresponding author "
        "upon request. Campaign tags are listed in Supporting Information section S11.",
        align="justify",
    )

    add_acknowledgements(doc)

    save_watched(doc, OUT_MS)
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


def fmt_tau_cell(rec):
    n_c, n = int(rec["n_commit"]), int(rec["n"])
    ttc = rec.get("median_ttc")
    if ttc in ("", None):
        return f"{n_c}/{n}"
    return f"{n_c}/{n} ({float(ttc):.1f})"


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
        "where implemented. Ranking code, CV JSON (AdK LID/NMP and MBP domain/hinge windows), "
        "and commitment functions are deposited at https://github.com/liying0128/TAPS in "
        "paper/protocol/ (MIT license).",
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
    add_caption(doc, "Table S2. Main-text n = 3 campaigns (TAPS omitted; see Table S5).")

    add_h(doc, "S3. First-hit data", 1)
    add_p(
        doc,
        "First hit is reported for completeness and is not the primary endpoint. Several "
        "campaigns hit and never committed (transient-only): CLN025 Random (2 hits / 0 commits), "
        "CLN025 kNN-AS (3/1), AdK Random (1/0), AdK LAST (1/0), AdK least-counts (3/2), "
        "MBP Random (1/0), MBP LAST (2/1), MBP least-counts (3/1), MBP kNN-AS (3/2). LAST and "
        "least-counts converted every CLN025 hit into a commit (3/3). MOAS converted every hit "
        "into a commit on all three systems (9/9). Those counts are reported as conversion under "
        "each objective, not as a ranking in which LAST is the losing method.",
        first_line=False,
        align="justify",
    )

    add_h(doc, "S4. Representative CV traces", 1)
    add_p(
        doc,
        "Rolling target occupancy for CLN025 (TAPS / LAST / MOAS) and AdK (Random / MOAS) is "
        "Figure 2 of the main text. Two-dimensional CV densities for AdK and MBP are Figure 5D–E. "
        "Additional seed-level CV trajectories live in each campaign’s cvs.npz (keys: CLN025 "
        "t_ps, rmsd, rg; AdK t_ps, lid, nmp, closed; MBP t_ps, dist, theta, closed). They can be "
        "replotted without new MD.",
        first_line=False,
        align="justify",
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
                    fmt_ns(rec["hit_ns"]),
                    fmt_ns(rec["commit_ns"]),
                    fmt_ns(rec.get("lag_ns")),
                    fmt_pct(rec["occupancy"]),
                    fmt_pct(rec.get("post_commit_occ")),
                    fmt_pct(rec.get("late_occ")),
                ]
            )
    add_table(
        doc,
        [
            "System",
            "Combination",
            "Hit (ns)",
            "Commit (ns)",
            "Hit→commit (ns)",
            "Occupancy (%)",
            "After commit (%)",
            "Last 25% (%)",
        ],
        ab_rows,
    )
    add_caption(
        doc,
        "Table S4. Ablation campaigns (n = 1). All combinations completed the budget. "
        "After commit is the closed-window fraction of frames after the committed visit. "
        "Last 25% is the occupancy of new frames in the final quarter of the budget. Occupancy "
        "trajectories and the three-objective simplex are Figure 7 of the main text.",
    )

    add_h(doc, "S7. Seed-selection mechanism", 1)
    add_p(
        doc,
        "Selected seeds store the mixed score in the per-round seed records, not the three raw "
        "objectives. Figure 6 of the main text shows the AdK seed maps, target-window seed "
        "fraction, target distance, and the novelty / boundary / target percentile ranks "
        "recomputed from each round’s candidate pool, matching the production windowing "
        "(50 ps windows, 10 ps stride) and the same scoring functions used in the AdK discover "
        "loop. Window indices in seeds_round*.json match the rebuilt candidate arrays in every "
        "round. Coverage versus occupancy for the n = 3 campaigns is Figure 8 of the main text.",
        first_line=False,
        align="justify",
    )

    add_h(doc, "S8. TAPS on CLN025 (additional comparison)", 1)
    add_p(
        doc,
        "TAPS is a target-aware adaptive method previously applied to CLN025. "
        "It is not a main-text baseline. Under the same 82 ns folded-discovery protocol it hit "
        "the RMSD < 0.25 nm window in 3/3 replicates and committed in 1/3 (seed 1 at 80.2 ns). "
        "Occupancies were 0.24%, 0.67%, and 0.09%. This is the canonical transient-encounter "
        "example in Figure 2A: a fast first hit that does not become persistent folded sampling. "
        "On the same protein LAST also committed in 3/3 (occupancy median 1.66%). MOAS committed "
        "in 3/3 with occupancy 4.0–6.8%. The SI comparison is therefore TAPS as a same-loop "
        "target-aware control, not a claim that MOAS supersedes LAST.",
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

    add_h(doc, "S9. Commitment-threshold robustness", 1)
    add_p(
        doc,
        "The production commitment thresholds (τ = 40 ps on CLN025; 200 ps on AdK and MBP) are "
        "system-specific protocol choices, not universal constants. To test whether ranking by "
        "committed sampling depends on that choice, every finished n = 3 campaign was re-scored "
        "from its existing cvs.npz trajectory at neighboring sojourns. No additional MD was run. "
        "CLN025 used 20, 40, 60, and 80 ps. AdK and MBP used 100, 200, 300, and 500 ps. "
        "CLN025 commitment is a contiguous sojourn whose duration t_end − t_start + Δt ≥ τ, "
        "matching the main text. AdK and MBP use the production implementation: at least "
        "round(τ/Δt) consecutive frames inside W, with Δt = 2 ps. Occupancy is the fraction of "
        "pooled frames inside W and does not depend on τ.",
        first_line=False,
        align="justify",
    )
    add_p(
        doc,
        "Figure S1 reports committed fraction, median time-to-commit among campaigns that "
        "committed, and median occupancy versus τ. The dotted vertical line is the production "
        "threshold. Table S6 lists the same numbers: each cell is committed replicates out of "
        "three, with the median time-to-commit (ns) in parentheses when at least one campaign "
        "committed. Columns τ₁–τ₄ are 20/40/60/80 ps for CLN025 and 100/200/300/500 ps for AdK "
        "and MBP; the production threshold is τ₂. MOAS remained 3/3 on CLN025 at every τ, 3/3 "
        "on AdK except 2/3 at 500 ps, and 3/3 on MBP at every τ. Exploration methods either "
        "matched MOAS only at the milder CLN025 thresholds (LAST and least-counts at 20–40 ps) "
        "or remained below 3/3. Occupancy ranking is unchanged because occupancy does not depend "
        "on τ (MOAS medians 5.25%, 14.85%, and 37.15%). The conclusion that MOAS converts "
        "encounters into committed sampling more consistently than Random, LAST, least-counts, "
        "or kNN-AS is therefore not manufactured by the production 40 ps / 200 ps choice.",
        first_line=False,
        align="justify",
    )
    add_fig(
        doc,
        "figS1_commit_threshold.png",
        "Figure S1. Commitment-threshold robustness from existing trajectories (no new MD). "
        "(A–C) Committed fraction versus τ on CLN025, AdK, and MBP (n = 3). (D–F) Median "
        "time-to-commit among campaigns that committed (log scale); a method is omitted at a "
        "threshold where no replicate committed. (G–I) Median target-basin occupancy, which is "
        "independent of τ by construction (values ≤ 0.001% are plotted at 0.001%). The dotted "
        "vertical line is the production threshold (40 ps on CLN025; 200 ps on AdK and MBP). "
        "TAPS is shown only for CLN025.",
        width=16.2,
    )
    tau_map = {}
    with (ROOT / "tables" / "commit_threshold_summary.csv").open(encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            tau_map[(rec["system"], rec["method"], rec["tau_ps"])] = rec
    tau_rows = []
    tau_order = {
        "CLN025": ["20.0", "40.0", "60.0", "80.0"],
        "AdK": ["100.0", "200.0", "300.0", "500.0"],
        "MBP": ["100.0", "200.0", "300.0", "500.0"],
    }
    for sys in ("CLN025", "AdK", "MBP"):
        methods = ["Random", "LAST", "Least-counts", "kNN-AS", "MOAS"] + (["TAPS"] if sys == "CLN025" else [])
        for m in methods:
            recs = [tau_map[(sys, m, t)] for t in tau_order[sys]]
            occ = recs[0]["median_occupancy"]
            tau_rows.append(
                [sys, m]
                + [fmt_tau_cell(r) for r in recs]
                + [f"{float(occ):.2f}"]
            )
    add_table(
        doc,
        ["System", "Method", "τ₁", "τ₂", "τ₃", "τ₄", "Occupancy (%)"],
        tau_rows,
    )
    add_caption(
        doc,
        "Table S6. Commitment versus sojourn threshold. Each cell is committed replicates / 3 "
        "(median time-to-commit in ns among campaigns that committed). τ₁–τ₄ are 20, 40, 60, "
        "and 80 ps for CLN025 and 100, 200, 300, and 500 ps for AdK and MBP. Production "
        "thresholds are τ₂. Occupancy is independent of τ.",
    )

    add_h(doc, "S10. Residence times and neighboring windows", 1)
    add_p(
        doc,
        "Occupancy f_W is the fraction of frames inside the production target window. A reviewer "
        "may ask whether that window, or the commitment threshold τ, manufactures the result. "
        "This section reuses the same cvs.npz trajectories with no additional MD. Each contiguous "
        "sojourn inside the production W is a residence time T, scored with the production "
        "duration definition (CLN025: t_end − t_start + Δt; AdK/MBP: n_frames × 2 ps). "
        "Figure S2A–C shows the empirical survival P(T ≥ t), averaged over the three campaigns "
        "(a campaign with no visit contributes 0, so each replicate has equal weight). "
        "Figure S2D–F shows the longest sojourn of each campaign; the dotted line is the "
        "production τ. A committed visit is the event that this longest sojourn is ≥ τ, so "
        "commitment is one horizontal cut through D–F rather than a separate endpoint. "
        "Typical sojourns are short for every method (median 2–20 ps). What differs is the "
        "tail: the median longest sojourn is 342 ps (MOAS), 152 ps (LAST), and 2 ps (Random) "
        "on CLN025; 1.82 ns, 0.33 ns, and 0 on AdK; 36.5 ns, 0.12 ns, and 0 on MBP "
        "(Table S7; main-text Table 3).",
        first_line=False,
        align="justify",
    )
    add_p(
        doc,
        "Figure S2G–I recomputes occupancy under neighboring definitions of W. CLN025 uses "
        "RMSD cutoffs 0.15, 0.20, 0.25 (production), 0.30, and 0.40 nm. AdK expands or shrinks "
        "the closed LID/NMP rectangle by Δ = −8, −4, 0, +4, +8 degrees. MBP uses paired shifts "
        "of the domain-distance and hinge-angle thresholds "
        "(−0.06 nm/−6°, −0.03 nm/−3°, production, +0.03 nm/+3°, +0.06 nm/+6°), labeled −2 to +2. "
        "MOAS remains the highest occupancy at the production window and at every looser or "
        "moderately tighter cutoff that is still populated. At the tightest CLN025 (0.15 nm) and "
        "AdK (−8°) settings the window is empty for all methods.",
        first_line=False,
        align="justify",
    )
    add_fig(
        doc,
        "figS2_residence.png",
        "Figure S2. Residence times and neighboring-window occupancy (existing trajectories; "
        "no new MD). (A–C) Mean of three campaign-wise empirical survivals P(T ≥ t) of contiguous "
        "sojourns in the production window W; campaigns with no visit contribute 0. The dotted "
        "vertical line is the production commitment threshold τ. (D–F) Longest sojourn of each "
        "replicate (circles) and the median of those three values (diamond); zeros are plotted "
        "at 1 ps. The dotted horizontal line is τ. (G–I) Median occupancy under neighboring "
        "definitions of W; the dotted vertical line is the production window. TAPS is shown "
        "only for CLN025. Values ≤ 0.001% are plotted at 0.001%.",
        width=16.2,
    )
    res_si = []
    with (ROOT / "tables" / "residence_time_summary.csv").open(encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            def _num(key, scale=1.0, digits=1):
                v = rec[key]
                if v in ("", None):
                    return "—"
                return f"{float(v) * scale:.{digits}f}"

            p = rec["p_sojourn_ge_tau"]
            p_s = "—" if p in ("", None) else f"{float(p):.3f}"
            res_si.append(
                [
                    rec["system"],
                    rec["method"],
                    rec["n_sojourns"],
                    _num("median_n_sojourns", digits=0),
                    _num("median_rt"),
                    _num("mean_rt"),
                    _num("median_max_rt"),
                    p_s,
                    f"{float(rec['median_occupancy']):.2f}",
                ]
            )
    add_table(
        doc,
        [
            "System",
            "Method",
            "Visits",
            "Med. n",
            "Med. T (ps)",
            "Mean T (ps)",
            "Med. max (ps)",
            "P(T≥τ)",
            "Occ. (%)",
        ],
        res_si,
    )
    add_caption(
        doc,
        "Table S7. Sojourn statistics in the production window W. Visits is the total number of "
        "contiguous sojourns across n = 3 campaigns. Med. n is the median number of sojourns per "
        "campaign. Med. T and mean T are medians, over campaigns that entered W, of that "
        "campaign’s median and mean sojourn. Med. max is the median of the three longest "
        "sojourns, including 0 for campaigns that never entered. P(T≥τ) is the mean over "
        "campaigns of the fraction of sojourns that meet the production τ (empty campaigns "
        "contribute 0). Occ. is production occupancy.",
    )
    win_rows = []
    win_map = {}
    with (ROOT / "tables" / "window_occupancy_summary.csv").open(encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            win_map[(rec["system"], rec["method"], rec["x"])] = rec["median_occupancy"]
    win_x = {
        "CLN025": ["0.15", "0.2", "0.25", "0.3", "0.4"],
        "AdK": ["-8.0", "-4.0", "0.0", "4.0", "8.0"],
        "MBP": ["-2.0", "-1.0", "0.0", "1.0", "2.0"],
    }
    for sys in ("CLN025", "AdK", "MBP"):
        methods = ["Random", "LAST", "Least-counts", "kNN-AS", "MOAS"] + (["TAPS"] if sys == "CLN025" else [])
        for m in methods:
            cells = []
            for x in win_x[sys]:
                v = win_map.get((sys, m, x))
                if v in ("", None):
                    cells.append("—")
                else:
                    cells.append(f"{float(v):.2f}")
            win_rows.append([sys, m] + cells)
    add_table(
        doc,
        ["System", "Method", "w−2", "w−1", "w₀", "w+1", "w+2"],
        win_rows,
    )
    add_caption(
        doc,
        "Table S8. Median occupancy (%) under neighboring definitions of W. Columns w−2…w+2 "
        "are RMSD cutoffs 0.15, 0.20, 0.25, 0.30, 0.40 nm for CLN025; LID/NMP margins −8, −4, "
        "0, +4, +8 degrees for AdK; and MBP window expansions −2…+2 as defined in the text. "
        "Production windows are w₀.",
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
        "mbp_novbnd, mbp_novtgt, mbp_bndtgt.",
        first_line=False,
        align="justify",
    )

    save_watched(doc, OUT_SI)
    print("wrote", OUT_SI)


if __name__ == "__main__":
    build_manuscript()
    build_si()
