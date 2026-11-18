"""Build the Stage 2 deck on the course template (L16 HCR Roboto Origin guide).

  python slides/build_deck.py

Reads the evidence produced by:
  python run_trial.py --video --gif --out runs/demo-assisted
  python run_eval.py --out runs/eval-assisted
  python tools/diagnose.py
and writes slides/SantaBot_Stage2_Simulation_Review.pptx.

The template's master, theme and fonts are kept; its slides are removed and
new ones are drawn in its exact styles (Space Grotesk titles, DM Sans body,
#0F172A / #0284C7 / #EA580C palette, label column + body column grid).
"""

from __future__ import annotations

import copy
import csv
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "L16 HCR Roboto Origin - Three-stage project guide and rubrics.pptx"
OUT = ROOT / "slides" / "SantaBot_Stage2_Simulation_Review.pptx"
DEMO = ROOT / "runs" / "demo-assisted"
EVAL = ROOT / "runs" / "eval-assisted"
DIAG = ROOT / "runs" / "diagnosis"

INK = RGBColor(0x0F, 0x17, 0x2A)
PAPER = RGBColor(0xF8, 0xFA, 0xFC)
SKY = RGBColor(0x38, 0xBD, 0xF8)
BLUE = RGBColor(0x02, 0x84, 0xC7)
ORANGE = RGBColor(0xEA, 0x58, 0x0C)
MUTED = RGBColor(0x47, 0x55, 0x69)
SOFT = RGBColor(0xCB, 0xD5, 0xE1)
LINE = RGBColor(0xE2, 0xE8, 0xF0)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
HEAD = "Space Grotesk"
BODY = "DM Sans"


# ---------------------------------------------------------------------------
def clear_slides(prs):
    sld_ids = prs.slides._sldIdLst
    for sld_id in list(sld_ids):
        prs.part.drop_rel(sld_id.rId)
        sld_ids.remove(sld_id)


def new_slide(prs, dark=False):
    s = prs.slides.add_slide(prs.slide_layouts[6])  # Blank
    for ph in list(s.placeholders):
        ph._element.getparent().remove(ph._element)
    bg = s.background.fill
    bg.solid()
    bg.fore_color.rgb = INK if dark else PAPER
    return s


def text(slide, x, y, w, h, runs, size=18, color=INK, font=BODY, bold=False, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, wrap=True, spacing=None, name=None):  # fmt: skip
    """`runs` is a str, or a list of paragraphs; a paragraph is a str or a list of (text, overrides)."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = wrap
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    paras = runs if isinstance(runs, list) else [runs]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if spacing:
            p.space_after = Pt(spacing)
        parts = para if isinstance(para, list) else [(para, {})]
        for t, o in parts:
            r = p.add_run()
            r.text = t
            f = r.font
            f.name = o.get("font", font)
            f.size = Pt(o.get("size", size))
            f.bold = o.get("bold", bold)
            f.italic = o.get("italic", False)
            f.color.rgb = o.get("color", color)
    return tb


def title(slide, t):
    text(slide, 0.67, 0.55, 12.0, 0.8, t, size=31.5, font=HEAD, bold=True, wrap=False, name="Title")


def footer(slide, note, page):
    text(slide, 0.67, 6.62, 11.15, 0.3, note, size=15, color=BLUE, bold=True)
    text(slide, 12.19, 6.98, 0.47, 0.21, str(page), size=12, color=MUTED, align=PP_ALIGN.RIGHT)


def label_rows(slide, rows, y0=1.75, gap=0.25, label_w=3.23, body_size=18, line_h=0.34):
    """The template's label-column + body-column rows."""
    y = y0
    for label, body in rows:
        text(slide, 0.67, y, label_w, 0.36, label, size=18.75, color=BLUE, bold=True)
        n = body.count("\n") + 1
        h = line_h * n + 0.1
        text(slide, 4.17, y, 8.42, h, body.split("\n"), size=body_size)
        y += max(h, 0.4) + gap
    return y


def rect(slide, x, y, w, h, fill=WHITE, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(1)
    s.shadow.inherit = False
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    s.text_frame.margin_left = s.text_frame.margin_right = Inches(0.12)
    return s


def table(slide, x, y, w, col_w, rows, size=14, header_size=14, row_h=0.36):
    nr, nc = len(rows), len(rows[0])
    gt = slide.shapes.add_table(nr, nc, Inches(x), Inches(y), Inches(w), Inches(row_h * nr))
    tbl = gt.table
    tblPr = tbl._tbl.tblPr
    for attr in ("firstRow", "bandRow"):
        tblPr.set(attr, "0")
    style = tblPr.find(qn("a:tableStyleId"))
    if style is not None:
        tblPr.remove(style)
    for j, cw in enumerate(col_w):
        tbl.columns[j].width = Inches(cw)
    for i in range(nr):
        tbl.rows[i].height = Inches(row_h)
        for j in range(nc):
            c = tbl.cell(i, j)
            c.margin_left = c.margin_right = Inches(0.1)
            c.margin_top = Inches(0.05)
            c.margin_bottom = Inches(0.04)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            c.fill.solid()
            c.fill.fore_color.rgb = INK if i == 0 else (WHITE if i % 2 else PAPER)
            val = rows[i][j]
            color = WHITE if i == 0 else INK
            bold = i == 0
            if isinstance(val, tuple):
                val, opts = val
                color = opts.get("color", color)
                bold = opts.get("bold", bold)
            tf = c.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            r = p.add_run()
            r.text = str(val)
            r.font.name = BODY
            r.font.size = Pt(header_size if i == 0 else size)
            r.font.bold = bold
            r.font.color.rgb = color
            _borders(c)
    return gt


def _borders(cell):
    """Thin #E2E8F0 rules like the template's tables. a:lnX must precede the fill."""
    tcPr = cell._tc.get_or_add_tcPr()
    for i, tag in enumerate(("a:lnL", "a:lnR", "a:lnT", "a:lnB")):
        for old in tcPr.findall(qn(tag)):
            tcPr.remove(old)
        ln = tcPr.makeelement(qn(tag), {"w": "5715"})
        sf = ln.makeelement(qn("a:solidFill"), {})
        sf.append(sf.makeelement(qn("a:srgbClr"), {"val": "E2E8F0"}))
        ln.append(sf)
        tcPr.insert(i, ln)


def pill(slide, x, y, w, t, fill=ORANGE, color=WHITE, size=12):
    s = rect(slide, x, y, w, 0.34, fill=fill, line=None, radius=0.5)
    tf = s.text_frame
    tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = t
    r.font.name, r.font.size, r.font.bold, r.font.color.rgb = BODY, Pt(size), True, color
    return s


def box_text(shape, lines, size=14, color=INK, bold_first=True, align=PP_ALIGN.LEFT):
    tf = shape.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run()
        r.text = ln
        r.font.name = BODY
        r.font.size = Pt(size if i else size + 1)
        r.font.bold = bold_first and i == 0
        r.font.color.rgb = BLUE if (bold_first and i == 0) else color


def arrow(slide, x1, y1, x2, y2, label=None, color=MUTED):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = color
    c.line.width = Pt(1.75)
    ln = c.line._get_or_add_ln()
    tail = ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"})
    ln.append(tail)
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        text(slide, mx - 1.0, my - 0.42, 2.0, 0.3, label, size=12, color=MUTED, align=PP_ALIGN.CENTER)
    return c


def notes(slide, t):
    slide.notes_slide.notes_text_frame.text = t


# ---------------------------------------------------------------------------
def load_metrics():
    with open(EVAL / "metrics.csv", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def build():
    prs = Presentation(str(TEMPLATE))
    clear_slides(prs)
    metrics = load_metrics()
    n_ok = sum(r["success"] == "True" for r in metrics)
    page = 1  # the title slide is page 1, unnumbered, as in the template

    # 1 -- title -------------------------------------------------------------
    s = new_slide(prs, dark=True)
    text(s, 0.83, 1.86, 11.77, 0.35, "STAGE 2 — SIMULATION REVIEW", size=14.25, color=SKY, bold=True, wrap=False)
    text(s, 0.79, 2.46, 11.77, 0.8, "SantaBot", size=48, color=PAPER, font=HEAD, bold=True)
    text(s, 0.79, 3.16, 11.77, 0.8, "A Roboto Origin gift-transfer display", size=48, color=PAPER, font=HEAD, bold=True)
    text(s, 0.83, 4.2, 11.25, 0.45, "Walk, squeeze, carry and place two gifts across a holiday table, then return home",
         size=21, color=SOFT)  # fmt: skip
    r = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.83), Inches(5.06), Inches(0.75), Inches(0.04))
    r.fill.solid()
    r.fill.fore_color.rgb = ORANGE
    r.line.fill.background()
    text(s, 0.83, 5.45, 11.46, 0.34, "Team SantaBot  /  Thursday, November 19, 2026  /  locomotion policy not yet trained",
         size=17.25, color=SOFT)  # fmt: skip
    notes(s, "Four-minute slot. Lead with the status: the controller, scene and policy hand-off are built and "
             "evaluated; the walking policy itself has not been trained, so every rollout shown is ASSISTED.")  # fmt: skip

    # 2 -- status ------------------------------------------------------------
    page += 1
    s = new_slide(prs)
    title(s, "Where SantaBot stands today")
    pill(s, 10.35, 0.66, 2.3, "NOT TRAINED YET")
    label_rows(
        s,
        [
            ("Built and tested", "Scene, high-level controller, forearm-squeeze IK, ONNX policy adapter,\n"
                                 "evaluation and diagnosis tools. 4/4 unit tests pass."),
            ("Not yet trained", "The walking policy. The task is ready in the TA's LearningRL pipeline;\n"
                                "the GPU run has not happened, so there is no policy.onnx yet."),
            ("What you will see", "An ASSISTED rollout: a soft weld carries the pelvis along the path the\n"
                                  "controller commands and the legs follow a scripted stepping pattern."),
            ("What is real physics", "Arm PD control, forearm-to-gift contact and friction, gift mass and\n"
                                     "dynamics, tables and tree collisions, at a 5 ms MuJoCo step."),
        ],
        body_size=18,
    )  # fmt: skip
    footer(s, "Every frame, number and plot in this deck comes from an assisted rollout, labelled as such.", page)
    notes(s, "Be explicit: the teacher's guide says a prescribed animation is not evidence of dynamic walking. "
             "Here the pelvis IS assisted, but the grasp and carry are dynamic. When the policy arrives, the "
             "assist is switched off with one flag.")  # fmt: skip

    # 3 -- animation -----------------------------------------------------------
    page += 1
    s = new_slide(prs)
    title(s, "The full display, end to end (assisted)")
    gif = DEMO / "trial.gif"
    pic = s.shapes.add_picture(str(gif), Inches(0.67), Inches(1.55), width=Inches(8.0))
    pic.name = "Animation: assisted SantaBot rollout"
    pic._element.nvPicPr.cNvPr.set("descr", "Animated MuJoCo rollout: the Origin moves both gifts to the mirrored spots.")
    x = 8.95
    text(s, x, 1.55, 3.7, 0.36, "Sequence, 100 s of sim time", size=18.75, color=BLUE, bold=True)
    steps = [
        "Activate at home",
        "Approach, raise arms, step in",
        "Reach, squeeze, lift 4 cm",
        "Reverse 30 cm, turn, carry",
        "Step in, lower, release, back off",
        "Repeat for the 12 in gift",
        "Return home and deactivate",
    ]
    for i, st in enumerate(steps):
        yy = 2.05 + i * 0.52
        c = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(yy), Inches(0.36), Inches(0.36))
        c.fill.solid()
        c.fill.fore_color.rgb = INK
        c.line.fill.background()
        tf = c.text_frame
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = str(i + 1)
        r.font.name, r.font.size, r.font.bold, r.font.color.rgb = BODY, Pt(12), True, WHITE
        text(s, x + 0.5, yy + 0.03, 3.25, 0.36, st, size=15)
    footer(s, "Never side-steps: lateral velocity command is 0 at every step. Turns happen in place.", page)
    notes(s, "The GIF plays automatically in slideshow mode. Full-resolution video: runs/demo-assisted/trial.mp4. "
             "Point out the reverse-then-turn after each pick, and that the gift is held only by forearm friction.")  # fmt: skip

    # 4 -- scene ---------------------------------------------------------------
    page += 1
    s = new_slide(prs)
    title(s, "Behavior contract and scene")
    s.shapes.add_picture(str(EVAL / "nominal1_topview.png"), Inches(0.67), Inches(1.75), width=Inches(6.4))
    rows = [
        ["Element", "From the brief", "In simulation"],
        ["Tables", "2 × 60 × 24 in, touching", "End to end, seam x = 0"],
        ["Height", "Origin waist level", "29.5 in (pelvis 0.75 m)"],
        ["Gifts", "8 in and 12 in, empty", "0.20 kg and 0.45 kg"],
        ["Small gift", "6 in from closest side", "6 in from the seam"],
        ["Large gift", "6 in left of the small", "6 in gap, further left"],
        ["Home", "1 ft from seam edges", "12 in, facing tables"],
        ["Success", "Both mirrored, home", "≤ 5 cm, upright"],
    ]
    table(s, 7.3, 1.6, 5.36, [1.15, 2.0, 2.21], rows, size=12, header_size=12.5, row_h=0.5)
    text(s, 0.67, 4.75, 6.3, 1.0,
         "To confirm: the brief does not give gift depth. Front faces sit 2 in from the table edge, because at "
         "6 in the 8 in gift's centre is beyond the Origin's ~0.43 m arm reach.",
         size=14, color=MUTED)  # fmt: skip
    footer(s, "Every dimension lives in config/santabot.yaml, in inches, as the brief states it.", page)

    # 5 -- architecture --------------------------------------------------------
    page += 1
    s = new_slide(prs)
    title(s, "Controller: one mission layer over a swappable walking policy")
    y, bw, bh = 1.8, 3.0, 1.5
    xs = (0.67, 5.17, 9.67)
    b1 = rect(s, xs[0], y, bw, bh)
    box_text(b1, ["Mission controller", "GoTo · ArmMove · Hold", "pose estimate + layout"], size=13)
    b2 = rect(s, xs[1], y, bw, bh)
    box_text(b2, ["Locomotion policy", "policy.onnx (LearningRL)", "obs/actions: LearningRLsim"], size=13)
    b3 = rect(s, xs[2], y, bw, bh)
    box_text(b3, ["PD → MuJoCo / Origin", "23 joint targets", "gains + limits from export"], size=13)
    mid = y + bh / 2
    arrow(s, xs[0] + bw, mid, xs[1], mid)
    text(s, xs[0] + bw, mid - 0.62, 1.5, 0.55, ["vx, wz", "vy = 0"], size=12, color=MUTED, align=PP_ALIGN.CENTER)
    arrow(s, xs[1] + bw, mid, xs[2], mid)
    text(s, xs[1] + bw, mid - 0.62, 1.5, 0.55, ["legs +", "torso"], size=12, color=MUTED, align=PP_ALIGN.CENTER)
    y2 = 4.0
    b4 = rect(s, xs[0], y2, bw, 1.2)
    box_text(b4, ["Forearm-squeeze IK", "wrist + elbow, multi-start"], size=13)
    arrow(s, xs[0] + bw / 2, y + bh, xs[0] + bw / 2, y2)
    # orange override path: IK box -> right, under the policy box -> up into the PD box
    ox = xs[2] + 0.6
    seg = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(xs[0] + bw), Inches(y2 + 0.6), Inches(ox), Inches(y2 + 0.6))
    seg.line.color.rgb = ORANGE
    seg.line.width = Pt(1.75)
    arrow(s, ox, y2 + 0.6, ox, y + bh, color=ORANGE)
    text(s, xs[1], y2 + 0.68, 4.2, 0.3, "10 arm targets override the policy's arms", size=12, color=ORANGE, bold=True)
    b5 = rect(s, xs[2] + 1.2, y2, bw - 1.2, 1.2, fill=PAPER, line=SOFT)
    box_text(b5, ["Until trained", "pelvis weld +", "scripted legs"], size=12)
    text(s, 0.67, 5.55, 12.0, 0.7,
         "Navigation is a unicycle: turn in place above 0.35 rad of heading error, otherwise walk or reverse with "
         "heading feedback, then turn to the final yaw. It reverses when the goal is behind and closer than 0.6 m.",
         size=14, color=MUTED)  # fmt: skip
    footer(s, "Inputs are only the pelvis pose and the table layout. No object sensing is assumed.", page)

    # 6 -- hand-off contract ---------------------------------------------------
    page += 1
    s = new_slide(prs)
    title(s, "When the ONNX file arrives: drop in, no code changes")
    rows = [
        ["Item", "Contract"],
        ["Files", "exports/<name>/ config.yaml + policy.onnx + policy.onnx.data (run dir as exported)"],
        ["Loader", "The TA's LearningRLsim: same observation assembly and action terms as learningrl-sim"],
        ["Observation", "78: ang vel, gravity, base_velocity, joint pos/vel, last action (+2 phase_clock)"],
        ["Command fed", "base_velocity = (vx ≤ 0.25 fwd / 0.12 rev, 0, wz ≤ 0.45 rad/s)"],
        ["Train", "LearningRL-RPO-FlatWalk-v0 (needs reverse + turn); ForwardWalk-v0 cannot"],
        ["Bring-up", "--assist full (policy legs, pelvis held)  →  unassisted  →  run_eval.py"],
    ]
    table(s, 0.67, 1.6, 12.0, [2.2, 9.8], rows, size=14, header_size=14, row_h=0.52)
    text(s, 0.67, 5.45, 12.0, 0.7,
         ["Verified today with a stand-in export in the same format (zero-output MLP, 80-dim observation with the",
          "alternating-gait clock): loads, runs at 50 Hz, completes the mission assisted and stands unassisted."],
         size=14, color=MUTED)  # fmt: skip
    footer(s, "python run_trial.py --policy exports/<name>   is the whole integration step.", page)

    # 7 -- physics evidence ----------------------------------------------------
    page += 1
    s = new_slide(prs)
    title(s, "Evidence that the physics is working")
    rows7 = [
        ("Robot and scene", ["rpo_description @ 37aac9c (the TA's pin): 23 hinge joints, 33.8 kg,",
                             "5 ms step. Forearm capsule pads μ 1.2; free gift boxes μ 0.9."]),
        ("Executed control", ["τ = clip(Kp(q* − q) − Kd q̇), RoboParty RPO_CFG gains, 50 Hz targets.",
                              "Declared support: the pelvis soft weld (solref 0.02) to the path."]),
        ("Measured outcome", ["≥ 9.9 N squeeze while carrying; gifts ride 6–7 cm above the table;",
                              "zero torque saturation and no falls in 10 trials."]),
    ]  # fmt: skip
    yy = 1.65
    for lab, body in rows7:
        text(s, 0.67, yy, 6.9, 0.36, lab, size=18.75, color=BLUE, bold=True)
        text(s, 0.67, yy + 0.42, 6.9, 0.75, body, size=15)
        yy += 1.5
    s.shapes.add_picture(str(DEMO / "squeeze_closeup.png"), Inches(8.0), Inches(1.6), width=Inches(4.67))
    text(s, 8.0, 5.2, 4.67, 0.6, "Large gift held by forearm friction alone, t = 60.6 s", size=12, color=MUTED)
    footer(s, "Traces saved per trial: reference, measured joints, torques, gift poses, grip force (.npz).", page)
    notes(s, "Teacher's guide: a fixed base or support fixture must be declared. Ours is the assist weld. "
             "The grasp is not scripted: gifts move only through contact with the forearm pads.")  # fmt: skip

    # 8 -- evaluation ------------------------------------------------------------
    page += 1
    s = new_slide(prs)
    title(s, f"Evaluation: {n_ok} of {len(metrics)} assisted trials place both gifts")
    rows = [["Trial", "Gift start offset (cm)", "Small err", "Large err", "Carry grip", "Result"]]
    for r in metrics:
        off = r["perturb_cm"].replace('"small_gift": ', "S ").replace('"large_gift": ', "L ").strip("{}") or "nominal"
        rows.append([
            r["trial"], off, f"{float(r['small_gift_err_cm']):.2f} cm", f"{float(r['large_gift_err_cm']):.2f} cm",
            f"≥ {float(r['min_carry_grip_N']):.1f} N",
            ("pass", {"color": RGBColor(0x1B, 0x6E, 0x3A), "bold": True}) if r["success"] == "True"
            else ("fail", {"color": RGBColor(0xB3, 0x26, 0x1E), "bold": True}),
        ])  # fmt: skip
    table(s, 0.67, 1.5, 7.75, [1.15, 2.6, 0.95, 0.95, 1.1, 1.0], rows, size=11.5, header_size=12, row_h=0.4)
    s.shapes.add_picture(str(EVAL / "nominal1_grip.png"), Inches(8.6), Inches(1.5), width=Inches(4.1))
    text(s, 8.6, 4.35, 4.1, 1.6,
         ["Nominal resets are deterministic, so the five variation trials move each gift's start by up to ±2 cm "
          "without telling the controller. The squeeze self-centres the gift: error stays under 1 cm."],
         size=13, color=MUTED)  # fmt: skip
    footer(s, "Pass = both gifts within 5 cm of the mirrored spot, upright, on the table; robot home and stopped.", page)

    # 9 -- diagnosis -------------------------------------------------------------
    page += 1
    s = new_slide(prs)
    title(s, "Diagnosis: two failures, one change each")
    s.shapes.add_picture(str(DIAG / "diagnosis.png"), Inches(1.07), Inches(1.4), width=Inches(11.2))
    y = 5.25
    text(s, 0.67, y, 5.9, 0.36, "E1  Large gift sank through the grip", size=17, color=BLUE, bold=True)
    text(s, 0.67, y + 0.42, 5.9, 0.9,
         ["Default pyramidal friction (impratio 1) let the squeeze creep.",
          "Elliptic cone, impratio 10: sink 10.6 → 1.2 cm, error 20.7 → 0.3 cm."],
         size=13.5)  # fmt: skip
    text(s, 6.77, y, 5.9, 0.36, "E2  Small gift never left the table", size=17, color=BLUE, bold=True)
    text(s, 6.77, y + 0.42, 5.9, 0.9,
         ["Parallel forearms touched only the gift's front edge.",
          "2 cm wrist toe-in: lifted 7 cm and placed; error 51.2 → 0.2 cm."],
         size=13.5)  # fmt: skip
    footer(s, "Earlier fix: IK local minimum (arm yaw 2.6 rad) cured by stance-relative targets + multi-start.", page)
    notes(s, "Both are reproduced by tools/diagnose.py: same initial condition, one config value changed, same "
             "metrics. E1's fix is a simulator setting that also affects foot contacts; flag it for sim-to-real.")  # fmt: skip

    # 10 -- readiness + gantt ------------------------------------------------------
    page += 1
    s = new_slide(prs)
    title(s, "Deployment readiness and revised plan")
    rows = [
        ["Task", "Owner", "Nov 13–19", "Nov 20–22", "Nov 23–29", "Nov 30–Dec 3"],
        ["Controller, scene, evaluation", "Team", ("Done", {"bold": True}), "", "", ""],
        ["Train FlatWalk policy (GPU)", "TA", "Request", "Train", "", ""],
        ["Unassisted sim + tuning", "Team", "", "Start", "Work", ""],
        ["Loaded-walk check / retrain", "Yuki", "", "", "Work", ""],
        ["Pelvis pose estimate on Origin", "Team", "", "Check", "Work", ""],
        ["Supervised hardware trials", "Team", "", "", "", "Finish"],
        ["Demo + handoff", "All", "", "", "", ("Due Dec 3", {"bold": True})],
    ]
    table(s, 0.67, 1.5, 7.7, [2.75, 0.85, 1.0, 1.0, 1.0, 1.1], rows, size=11.5, header_size=12, row_h=0.46)
    gaps = [
        ("Interface gaps", "Arm override is untested on a real\npolicy; carrying load was never trained."),
        ("State estimate", "Sim uses true pelvis pose; hardware\nneeds odometry or external tracking."),
        ("Stop + reset", "Deactivate = zero command, arms\nhome; map to Origin's damping mode."),
    ]
    yy = 1.5
    for lab, body in gaps:
        text(s, 8.65, yy, 4.0, 0.34, lab, size=16, color=BLUE, bold=True)
        text(s, 8.65, yy + 0.38, 4.0, 0.7, body.split("\n"), size=13)
        yy += 1.35
    footer(s, "Owners are placeholders to confirm in class. Simulation gains need instructor review for hardware.", page)

    prs.save(str(OUT))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    build()
