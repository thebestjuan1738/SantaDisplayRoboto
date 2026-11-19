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


def area(slide, name):
    """Small label above the title naming which of the professor's five areas a slide covers."""
    text(slide, 0.67, 0.2, 9.0, 0.3, name.upper(), size=12, color=BLUE, bold=True, wrap=False)


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
    text(s, 0.83, 5.45, 11.46, 0.34, "Cody, Sergio and Yuki  /  Thursday, November 19, 2026  /  whole-body policy training now",
         size=17.25, color=SOFT)  # fmt: skip
    notes(s, "Four-minute slot. Lead with the status: the controller, scene and policy hand-off are built and "
             "evaluated; the whole-body policy is training now (export expected by end of week, tuned over break), so every "
             "rollout shown is ASSISTED.")  # fmt: skip

    # 1b -- the brief (grammar-corrected) -----------------------------------------
    page += 1
    s = new_slide(prs)
    title(s, "The brief")
    blocks = [
        ("The task", "We are building a locomanipulation display with the Roboto Origin humanoid, dubbed "
                     "SantaBot. It starts from a home position, walks up to a table holding two presents, "
                     "grabs one and moves it to the mirrored position on the adjacent table. It then returns "
                     "for the second present, repeats the task, returns home and deactivates."),
        ("The scene", "Two 60 × 24 in tables stand at the Origin's waist height. The gifts are empty 8 in and "
                      "12 in cubes. The small gift starts 6 in from the closest side of the table, with the "
                      "large gift 6 in to its left. Home is 1 ft from the edges where the tables touch. For "
                      "festivity, a tree stands between the mirrored positions of the presents."),
        ("Motion and grasp", "Movement should look natural: the robot grabs a gift, reverses and turns as "
                             "needed, with no side-stepping. The Origin has no end effectors, so each present "
                             "is squeezed between the wrists, which are placed slightly inside the gift's "
                             "faces to apply adequate pressure."),
        ("Policy and controller", "We are adapting the TA's G1 reinforcement-learning pipeline. Training access "
                                  "may be limited, so the exported ONNX policy must integrate easily. A "
                                  "high-level controller interfaces with that ONNX file, and the trial runs in "
                                  "MuJoCo so the controller can be tuned."),
    ]  # fmt: skip
    for k, (lab, body) in enumerate(blocks):
        x = 0.67 + (k % 2) * 6.2
        y = 1.6 + (k // 2) * 2.45
        text(s, x, y, 5.8, 0.36, lab, size=18.75, color=BLUE, bold=True)
        text(s, x, y + 0.45, 5.8, 1.9, body, size=14.5)
    footer(s, "The official prompt, edited for grammar only. Interpretations are on the scene slide.", page)
    notes(s, "Wording corrected for grammar and clarity; no requirement was added or removed.")

    # 2 -- status ------------------------------------------------------------
    page += 1
    s = new_slide(prs)
    title(s, "Where SantaBot stands today")
    area(s, "Status")
    pill(s, 10.35, 0.66, 2.3, "TRAINING NOW")
    label_rows(
        s,
        [
            ("Built and tested", "Scene, high-level controller, forearm-squeeze IK, ONNX policy adapter,\n"
                                 "evaluation and diagnosis tools. 5/5 unit tests pass."),
            ("Training now", "The whole-body policy (legs and arms) is training on the TA's GPU. We\n"
                             "expect the export by the end of this week, so it can be tuned over break."),
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

    # 3b -- agenda: the professor's five areas -------------------------------------
    page += 1
    s = new_slide(prs)
    title(s, "What we're presenting")
    rows = [["Area", "Slides", "What you'll see"]] + [
        [(a, {"bold": True}), n, w] for a, n, w in [('Prompting pipeline', '5', 'How Claude Code built and checked the work, and where we steered it'), ('Retargeting and control', '6–8', "The TA's G1 task ported to the Origin; controller; ONNX hand-off"), ('Simulation technical details', '9–10', 'Scene from the brief; model, timing, contacts, actuation'), ('Videos and evaluation', '11–12', 'End-to-end rollout; 5 nominal + 5 variation trials'), ('Diagnosis and Stage 3 readiness', '13–14', 'Two diagnosed failures; hardware gaps and revised plan')]
    ]
    table(s, 0.67, 1.6, 12.0, [3.6, 1.1, 7.3], rows, size=15, header_size=15, row_h=0.62)
    footer(s, "Organised around the five areas requested for today's progress review.", page)

    # 3c -- prompting pipeline ----------------------------------------------------
    page += 1
    s = new_slide(prs)
    title(s, "Prompting pipeline: grounded prompts, measured results")
    area(s, "Prompting pipeline")
    steps = [
        ("1  Ground it", "The official brief, the TA's LearningRL repo, the pinned Origin model and the course guide"),
        ("2  Plan, flag", "Interpretations the brief leaves open (gift depth, reach) flagged for us to confirm"),
        ("3  Build + run", "Claude Code writes the code, runs MuJoCo and the tests, renders stills to check"),
        ("4  Measure", "Every claim backed by a run: metrics, plots, one-change before/after experiments"),
        ("5  Review, steer", "We redirected it to whole-body locomanipulation; a pre-run review caught a crash"),
    ]
    bw, gap = 2.22, 0.225
    for k, (head, body) in enumerate(steps):
        x = 0.67 + k * (bw + gap)
        b = rect(s, x, 1.7, bw, 2.5)
        box_text(b, [head, body], size=12.5)
        b.text_frame.vertical_anchor = MSO_ANCHOR.TOP
        b.text_frame.margin_top = Inches(0.2)
        if k < len(steps) - 1:
            arrow(s, x + bw, 2.95, x + bw + gap, 2.95)
    label_rows(
        s,
        [
            ("Model", "Claude Opus 5.5 in Claude Code, from planning through implementation."),
            ("Record", "docs/EXPERIMENT_LOG.md: goal, change, command, observation, decision."),
        ],
        y0=4.6,
        gap=0.15,
        body_size=16,
    )
    footer(s, "Outputs were accepted only with a run behind them; we reviewed plots and frames, not claims.", page)
    notes(s, "Concrete steering examples: we rejected the walk-only training plan in favour of one locomanipulation "
             "policy for arms and legs; a code review before Mark's run found that the hand command's class_type "
             "string would not resolve in Isaac Lab and would have crashed the env build.")  # fmt: skip

    # 4b -- retargeting --------------------------------------------------------------
    page += 1
    s = new_slide(prs)
    title(s, "Retargeting the TA's G1 locomanipulation task to the Origin")
    area(s, "Retargeting and control")
    rows = [
        ["", "TA's G1 task", "Our Origin task (student/cody-rpo-locomanip)"],
        ["Robot", "Unitree G1, 29 DoF, implicit PD", "RoboParty Origin, 23 DoF, delayed PD (RPO_CFG)"],
        ["Hand point", "wrist_yaw_link origin", "0.135 m along each forearm: the Origin has no hands"],
        ["Hand targets", "x 0–0.40, |y| 0–0.45, z 0–0.60 m", "x 0–0.40, |y| 0–0.35, z −0.15–0.35 m"],
        ["Joint terms", "hip_*, waist_*, wrist_*", "thigh_*, torso_joint, arm_* / elbow_*"],
        ["Heights", "base 0.78 m, swing foot 0.10 m", "base 0.75 m, swing foot 0.11 m"],
        ["Load", "none", "+0–0.3 kg on each forearm"],
        ["Unchanged", "rewards, hand-tracking ramp, PPO, terminations", "same, with the shared swap_in_rpo()"],
    ]
    table(s, 0.67, 1.55, 12.0, [1.8, 4.3, 5.9], rows, size=13, header_size=13.5, row_h=0.5)
    text(s, 0.67, 5.75, 12.0, 0.6,
         "No motion-capture retargeting is needed: the controller derives wrist targets from the gift geometry, "
         "and the policy learns to reach them with the Origin's 5-DoF arms while walking.",
         size=14, color=MUTED)  # fmt: skip
    footer(s, "One policy, legs and arms: base_velocity + hand_track in, 23 joint targets out.", page)

    # 5 -- architecture --------------------------------------------------------
    page += 1
    s = new_slide(prs)
    title(s, "Controller: one mission layer over one whole-body policy")
    area(s, "Retargeting and control")
    y, bw, bh = 1.8, 3.0, 1.5
    xs = (0.67, 5.17, 9.67)
    b1 = rect(s, xs[0], y, bw, bh)
    box_text(b1, ["Mission controller", "GoTo · ArmMove · Hold", "pose estimate + layout"], size=13)
    b2 = rect(s, xs[1], y, bw, bh)
    box_text(b2, ["Whole-body policy", "policy.onnx: legs + arms", "RPO-LocoManipulation-v0"], size=13)
    b3 = rect(s, xs[2], y, bw, bh)
    box_text(b3, ["PD → MuJoCo / Origin", "23 joint targets", "gains + limits from export"], size=13)
    mid = y + bh / 2
    arrow(s, xs[0] + bw, mid, xs[1], mid)
    text(s, xs[0] + bw, mid - 0.62, 1.5, 0.55, ["vx, wz", "vy = 0"], size=12, color=MUTED, align=PP_ALIGN.CENTER)
    arrow(s, xs[1] + bw, mid, xs[2], mid)
    text(s, xs[1] + bw, mid - 0.62, 1.5, 0.55, ["all 23", "joints"], size=12, color=MUTED, align=PP_ALIGN.CENTER)
    y2 = 4.0
    b4 = rect(s, xs[0], y2, bw, 1.2)
    box_text(b4, ["Wrist planner", "gift geometry → wrist points"], size=13)
    arrow(s, xs[0] + bw / 2, y + bh, xs[0] + bw / 2, y2)
    # orange hand-command path: wrist planner -> right -> up into the policy box
    ox = xs[1] + bw / 2
    seg = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(xs[0] + bw), Inches(y2 + 0.6), Inches(ox), Inches(y2 + 0.6))
    seg.line.color.rgb = ORANGE
    seg.line.width = Pt(1.75)
    arrow(s, ox, y2 + 0.6, ox, y + bh, color=ORANGE)
    text(s, xs[0] + bw + 0.1, y2 + 0.68, 4.2, 0.3, "hand_track: wrist targets", size=12, color=ORANGE, bold=True)
    b5 = rect(s, xs[2] + 0.4, y2, bw - 0.4, 1.2, fill=PAPER, line=SOFT)
    box_text(b5, ["Until trained", "weld + scripted legs;", "IK arms (assisted only)"], size=12)
    text(s, 0.67, 5.55, 12.0, 0.7,
         "Navigation is a unicycle: turn in place above 0.35 rad of heading error, otherwise walk or reverse with "
         "heading feedback, then turn to the final yaw. It reverses when the goal is behind and closer than 0.6 m.",
         size=14, color=MUTED)  # fmt: skip
    footer(s, "Inputs are only the pelvis pose and the table layout. No object sensing is assumed.", page)

    # 6 -- hand-off contract ---------------------------------------------------
    page += 1
    s = new_slide(prs)
    title(s, "When the ONNX file arrives: drop in, no code changes")
    area(s, "Retargeting and control")
    rows = [
        ["Item", "Contract"],
        ["Files", "exports/<name>/ config.yaml + policy.onnx + policy.onnx.data (run dir as exported)"],
        ["Loader", "The TA's LearningRLsim: same observation assembly and action terms as learningrl-sim"],
        ["Observation", "86: ang vel, gravity, base_velocity, joint pos/vel, last action + 8 hand_track"],
        ["Commands fed", "base_velocity (vx, 0, wz) + hand_track (both wrists, pelvis frame)"],
        ["Train", "LearningRL-RPO-LocoManipulation-v0, branch student/cody-rpo-locomanip"],
        ["Bring-up", "--assist full (policy limbs, pelvis held)  →  unassisted  →  run_eval.py"],
    ]
    table(s, 0.67, 1.6, 12.0, [2.2, 9.8], rows, size=14, header_size=14, row_h=0.52)
    text(s, 0.67, 5.45, 12.0, 0.7,
         ["Verified with a stand-in export in the same format (zero-output MLP, 86 inputs): it loads, the hand",
          "command carries the controller's planned wrist points, all inside the task's training ranges."],
         size=14, color=MUTED)  # fmt: skip
    footer(s, "python run_trial.py --policy exports/<name>   is the whole integration step.", page)

    # 4 -- scene ---------------------------------------------------------------
    page += 1
    s = new_slide(prs)
    title(s, "Behavior contract and scene")
    area(s, "Simulation technical details")
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

    # 7 -- simulation technical details -------------------------------------------
    page += 1
    s = new_slide(prs)
    title(s, "Simulation technical details")
    area(s, "Simulation technical details")
    rows = [
        ["Item", "Setting"],
        ["Simulator", "MuJoCo 4.0.1 on CPU; the model the TA's LearningRLsim replays"],
        ["Robot", "rpo_description @ 37aac9c: 23 hinge joints, 33.8 kg"],
        ["Timing", "5 ms physics step, 50 Hz control (decimation 4), PGS solver"],
        ["Contacts", "Elliptic friction cone, impratio 10; forearm pads μ 1.2; gifts μ 0.9"],
        ["Actuation", "τ = clip(Kp(q* − q) − Kd q̇), RPO_CFG gains, 120 / 27 N·m limits"],
        ["Objects", "Free gifts 0.20 / 0.45 kg; 29.5 in tables; tree collider"],
        ["Support", "Declared: pelvis soft weld (solref 0.02) until the policy is in"],
        ["Logged", "Joints, targets, torques, gift poses, grip force, hand targets"],
    ]
    table(s, 0.67, 1.5, 7.55, [1.45, 6.1], rows, size=12, header_size=12.5, row_h=0.5)
    s.shapes.add_picture(str(DEMO / "squeeze_closeup.png"), Inches(8.45), Inches(1.5), width=Inches(4.2))
    text(s, 8.45, 4.75, 4.2, 0.9,
         ["Large gift held by forearm friction alone (t = 60.6 s): ≥ 9.9 N squeeze while carrying, "
          "zero torque saturation in 10 trials."],
         size=12.5, color=MUTED)  # fmt: skip
    footer(s, "One .npz trace per trial, saved beside the video, so every plot can be regenerated.", page)
    notes(s, "Teacher's guide: a fixed base or support fixture must be declared. Ours is the assist weld. "
             "The grasp is not scripted: gifts move only through contact with the forearm pads.")  # fmt: skip

    # 3 -- animation -----------------------------------------------------------
    page += 1
    s = new_slide(prs)
    title(s, "The full display, end to end (assisted)")
    area(s, "Videos and evaluation")
    gif = DEMO / "trial.gif"
    pic = s.shapes.add_picture(str(gif), Inches(0.67), Inches(1.55), width=Inches(8.0))
    pic.name = "Animation: assisted SantaBot rollout"
    pic._element.nvPicPr.cNvPr.set(
        "descr", "Animated MuJoCo rollout: the Origin moves both gifts; green dots mark the wrist targets (hand_track)."
    )
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
    # marker key: the green dots in the animation are the new hand_track command
    dot = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x + 0.1), Inches(5.83), Inches(0.18), Inches(0.18))
    dot.fill.solid()
    dot.fill.fore_color.rgb = RGBColor(0x1A, 0xD9, 0x41)
    dot.line.fill.background()
    text(s, x + 0.5, 5.74, 3.25, 0.7,
         "Green: wrist targets sent to the policy (hand_track)",
         size=13, color=MUTED)  # fmt: skip
    footer(s, "Never side-steps: lateral velocity command is 0 at every step. Turns happen in place.", page)
    notes(s, "The GIF plays automatically in slideshow mode. Full-resolution video: runs/demo-assisted/trial.mp4. "
             "Point out the reverse-then-turn after each pick, and that the gift is held only by forearm friction. "
             "The green dots are the hand_track wrist targets the trained policy will receive; until it is trained, "
             "the arms are driven to them by IK, so a blue dot (actual wrist) appears only where the wrist is "
             "held off its target, during the squeeze.")  # fmt: skip

    # 8 -- evaluation ------------------------------------------------------------
    page += 1
    s = new_slide(prs)
    title(s, f"Evaluation: {n_ok} of {len(metrics)} assisted trials place both gifts")
    area(s, "Videos and evaluation")
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
    area(s, "Diagnosis and Stage 3 readiness")
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
    title(s, "Stage 3 readiness and revised plan")
    area(s, "Diagnosis and Stage 3 readiness")
    rows = [
        ["Task", "Owner", "Nov 13–19", "Nov 20–22", "Nov 23–29", "Nov 30–Dec 3"],
        ["Controller, scene, evaluation", "Cody", ("Done", {"bold": True}), "", "", ""],
        ["Train locomanip policy (GPU)", "TA", ("Training", {"bold": True}), "Export EOW", "", ""],
        ["Unassisted sim + tuning", "Cody, Sergio", "", "Start", "Tune (break)", ""],
        ["Squeeze tuning with policy", "Yuki", "", "", "Tune (break)", ""],
        ["Pelvis pose estimate on Origin", "Sergio", "", "Check", "Work", ""],
        ["Supervised hardware trials", "All", "", "", "", "Finish"],
        ["Demo + handoff", "All", "", "", "", ("Due Dec 3", {"bold": True})],
    ]
    table(s, 0.67, 1.5, 7.7, [2.35, 0.95, 1.05, 1.1, 1.15, 1.1], rows, size=11.5, header_size=12, row_h=0.46)
    gaps = [
        ("Interface gaps", "Training rewards wrist position, not\ngrip force; tune the squeeze inset."),
        ("State estimate", "Sim uses true pelvis pose; hardware\nneeds odometry or external tracking."),
        ("Stop + reset", "Deactivate = zero command, arms\nhome; map to Origin's damping mode."),
    ]
    yy = 1.5
    for lab, body in gaps:
        text(s, 8.65, yy, 4.0, 0.34, lab, size=16, color=BLUE, bold=True)
        text(s, 8.65, yy + 0.38, 4.0, 0.7, body.split("\n"), size=13)
        yy += 1.35
    footer(s, "Policy export expected by end of week; tuning runs over break. Gains need instructor review.", page)

    prs.save(str(OUT))
    print(f"wrote {OUT}")
    export_single(OUT, CONTROLLER_SLIDE, OUT.with_name("SantaBot_controller_slide.pptx"))


CONTROLLER_SLIDE = 7  # "Controller: one mission layer over one whole-body policy"


def export_single(deck: Path, number: int, out: Path) -> None:
    """Save slide `number` (1-based) of `deck` on its own, for pasting into another deck.

    The slide-number text box is dropped: the slide will sit at a different
    position in the shared deck, whose own numbering applies.
    """
    prs = Presentation(str(deck))
    ids = prs.slides._sldIdLst
    keep = list(ids)[number - 1]
    for sld_id in list(ids):
        if sld_id is not keep:
            prs.part.drop_rel(sld_id.rId)
            ids.remove(sld_id)
    slide = prs.slides[0]
    for shape in list(slide.shapes):
        if shape.has_text_frame and shape.text_frame.text.strip() == str(number) and shape.left > Inches(12):
            shape._element.getparent().remove(shape._element)
    prs.save(str(out))
    print(f"wrote {out}")


if __name__ == "__main__":
    build()
