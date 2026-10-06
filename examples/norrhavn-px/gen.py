"""Generate the Norrhavn PX datasheet (fictional product) as LaTeX.

One source of numbers: the SIZES table below. Every table, the dimension
letters and the flow-chart curves are derived from it, so the sheet stays
consistent when a value changes.
"""
from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).with_name("norrhavn-px.tex")

# size, Qmax m3/h at 2900 rpm, shut-off head m, mass kg, max inlet kPa
# Heads do not grow with size: a family mixes narrow high-head impellers with
# wide low-head ones, so the curves cross as they do in a real catalogue.
SIZES = [
    (5, 12, 24, 29, 600),
    (10, 25, 40, 41, 1000),
    (15, 40, 36, 48, 1000),
    (20, 60, 58, 62, 1000),
    (30, 90, 46, 84, 1000),
    (42, 130, 72, 112, 1000),
    (55, 180, 62, 158, 1000),
    (70, 240, 100, 215, 1000),
    (85, 320, 84, 290, 500),
    (100, 420, 48, 380, 500),
]
NAMES = [f"PX-{s}" for s, *_ in SIZES]

# Pump-specific dimensions, letters as on the drawing. PX-42 is the anchor
# (the values of the PX-42 outline drawing); other sizes scale with size.
PX42 = {"A": 170, "B": 160, "C": 375, "D": 260, "E": 300, "F": 180, "G": 240, "H": 140}
DIM_TEXT = {
    "A": "Suction flange face to discharge axis",
    "B": "Shaft centre height above base",
    "C": "Discharge flange face above base",
    "D": "Casing outer diameter",
    "E": "Baseplate length",
    "F": "Baseplate width",
    "G": "Foot bolt spacing, length",
    "H": "Foot bolt spacing, width",
}
MOTOR_KEY = [
    ("J", "Motor length, flange to fan cover"),
    ("K", "Motor height over shaft centre"),
    ("N", "Overall length, suction flange face to fan cover"),
]


def scale(size: int) -> float:
    return (size / 42) ** 0.36


def dims(size: int) -> dict[str, int]:
    return {k: int(round(v * scale(size) / 5.0) * 5) for k, v in PX42.items()}


# Motor frames (IEC), kW at 2 poles, and motor-specific measures J, K, (L unused).
MOTORS = [
    ("IEC80", "0.75/1.1", 262, 125, 250),
    ("IEC90", "1.5/2.2", 262, 157, 288),
    ("IEC100", "3.0", 282, 185, 325),
    ("IEC112", "4.0", 285, 198, 359),
    ("IEC132", "5.5/7.5", 304, 196, 383),
    ("IEC160", "11/15/18.5", 332, 262, 485),
    ("IEC180", "22", 352, 286, 533),
    ("IEC200", "30/37/45", 372, 399, 670),
    ("IEC250", "55/75", 446, 394, 738),
    ("IEC280", "90/110", 496, 584, 960),
]
# Motor range per size (first, last frame index)
MOTOR_RANGE = [(0, 1), (1, 3), (1, 4), (2, 5), (2, 6), (3, 7), (4, 8), (5, 8), (6, 9), (7, 9)]


def overall_length(size_i: int, motor_i: int) -> int:
    base = 330 + 55 * size_i
    _, _, _, _, h = MOTORS[motor_i]
    return int(round((base + h * 0.9) / 5) * 5)


# Connections: nominal inlet / outlet (DN) per size group, and M1/M2 per standard.
CONN_GROUPS = [
    ("PX-5", [0]),
    ("PX-10\\\\PX-15", [1, 2]),
    ("PX-20\\\\PX-30", [3, 4]),
    ("PX-42\\\\PX-55", [5, 6]),
    ("PX-70", [7]),
    ("PX-85\\\\PX-100", [8, 9]),
]
DN = [("DN40", "DN32"), ("DN65", "DN50"), ("DN80", "DN65"), ("DN100", "DN80"), ("DN125", "DN100"), ("DN150", "DN125")]
CONN_STD = [
    ("Clamp ISO 2852", [(21, 21), (21, 21), (21, 21), (21, 21), (21, 21), ("--", "--")]),
    ("Union SMS 1145", [(20, 20), (24, 20), (24, 24), (35, 24), (35, 35), ("--", "--")]),
    ("Union DIN 11851", [(22, 22), (25, 22), (30, 25), (30, 30), (30, 30), (50, 50)]),
    ("Flange EN 1092-1 PN16", [("--", "--"), ("--", "--"), (18, 18), (18, 18), (20, 20), (22, 22)]),
]


def curve(size_i: int) -> list[tuple[float, float]]:
    _, qmax, h0, _, _ = SIZES[size_i]
    pts = []
    for k in range(0, 21):
        q = qmax * k / 20
        x = q / qmax
        h = h0 * (1 + 0.04 * x - 0.52 * x**2 - 0.08 * x**4)
        pts.append((round(q, 1), round(h, 1)))
    return pts


def row(cells: list[str]) -> str:
    return " & ".join(cells) + " \\\\"


def wide(size: str, cols: str, header: list[str]) -> list[str]:
    """A full-width zebra table: bold header over an accent rule, striped rows."""
    return [f"\\begin{{wide}}{{{size}}}{{{cols}}}", "\\hdr " + row([f"\\textbf{{{h}}}" for h in header]), "\\ghl"]


def pump_measures_table() -> str:
    lines = wide("\\small", "l" + "C" * len(SIZES), ["Pump model"] + NAMES)
    for letter in "ABCDEFGH":
        lines.append(row([f"\\textbf{{{letter}}}"] + [str(dims(s)[letter]) for s, *_ in SIZES]))
    lines.append(row(["\\textbf{Mass (kg)}\\footnotemark[2]"] + [str(m) for _, _, _, m, _ in SIZES]))
    lines.append("\\end{wide}")
    return "\n".join(lines)


def motor_measures_table() -> str:
    lines = wide("\\footnotesize", "l" + "C" * len(MOTORS), ["Motor frame"] + [m[0] for m in MOTORS])
    lines.append(row(["\\textbf{Motor kW}"] + [m[1] for m in MOTORS]))
    lines.append(row(["\\textbf{J}"] + [str(m[2]) for m in MOTORS]))
    lines.append(row(["\\textbf{K}"] + [str(m[3]) for m in MOTORS]))
    groups = [("PX-5 -- -15", [0, 1, 2]), ("PX-20 -- -55", [3, 4, 5, 6]), ("PX-70 -- -100", [7, 8, 9])]
    for label, sizes in groups:
        cells = []
        for mi in range(len(MOTORS)):
            fits = [si for si in sizes if MOTOR_RANGE[si][0] <= mi <= MOTOR_RANGE[si][1]]
            cells.append(str(overall_length(max(fits), mi)) if fits else "--")
        lines.append(row([f"\\textbf{{N}} ({label})"] + cells))
    lines.append("\\end{wide}")
    return "\n".join(lines)


def motor_overview_table() -> str:
    lines = wide("\\small", "l" + "C" * len(SIZES), ["Pump model"] + NAMES)
    cells = [f"{MOTORS[a][0]}--\\\\{MOTORS[b][0]}" for a, b in MOTOR_RANGE]
    cells = [f"\\begin{{tabular}}[t]{{@{{}}c@{{}}}}{c}\\end{{tabular}}" for c in cells]
    lines.append(row(["\\textbf{Motor range (IEC)}"] + cells))
    lines.append("\\end{wide}")
    return "\n".join(lines)


def connections_table() -> str:
    heads = ["\\begin{tabular}[b]{@{}c@{}}\\bfseries " + g.replace("\\\\", " \\\\ \\bfseries ") + "\\end{tabular}" for g, _ in CONN_GROUPS]
    lines = [f"\\begin{{wide}}{{\\small}}{{ll{'C' * len(CONN_GROUPS)}}}", "\\hdr " + row(["\\textbf{Pump model}", ""] + heads), "\\ghl"]
    for std, vals in CONN_STD:
        lines.append(row([f"\\textbf{{{std}}}", "M1"] + [str(v[0]) for v in vals]))
        lines.append(row(["", "M2"] + [str(v[1]) for v in vals]))
    lines.append(row(["\\textbf{Inlet}\\footnotemark[1]", "N1"] + [d[0] for d in DN]))
    lines.append(row(["\\textbf{Outlet}\\footnotemark[1]", "N2"] + [d[1] for d in DN]))
    lines.append("\\end{wide}")
    return "\n".join(lines)


def glance_table() -> str:
    lines = wide("\\small", "l" + "C" * len(SIZES), ["Pump model"] + NAMES)
    lines.append(row(["\\textbf{Max flow (m\\textsuperscript{3}/h)}"] + [str(q) for _, q, *_ in SIZES]))
    lines.append(row(["\\textbf{Max head (m)}"] + [str(h) for _, _, h, *_ in SIZES]))
    lines.append(row(["\\textbf{Motor range (kW)}"] + [f"{MOTORS[a][1].split('/')[0]}--{MOTORS[b][1].split('/')[-1]}" for a, b in MOTOR_RANGE]))
    groups = [next(i for i, (_, members) in enumerate(CONN_GROUPS) if si in members) for si in range(len(SIZES))]
    lines.append(row(["\\textbf{Inlet}"] + [DN[g][0] for g in groups]))
    lines.append(row(["\\textbf{Outlet}"] + [DN[g][1] for g in groups]))
    lines.append("\\end{wide}")
    return "\n".join(lines)


def flow_chart() -> str:
    """Curves labelled with the model name at their end; one colour ramp, no legend."""
    plots = []
    n = len(SIZES)
    for si in range(n):
        pts = curve(si)
        coords = " ".join(f"({q},{h})" for q, h in pts)
        qe, he = pts[-1]
        mix = int(round(100 * si / (n - 1)))  # charcoal for small sizes, accent for large
        # The five small curves end close together: stagger their labels above and below.
        anchor = {0: "north west", 1: "south west", 2: "north west", 3: "south west", 4: "north west"}.get(si, "west")
        font = "\\tiny" if si < 5 else "\\scriptsize"
        plots.append(
            f"\\addplot[color=accent!{mix}!ink,line width=1.3pt,smooth] coordinates {{{coords}}};\n"
            f"\\node[anchor={anchor},font={font}\\bfseries,text=ink,inner sep=1pt] at (axis cs:{qe},{he}) {{{NAMES[si]}}};"
        )
    return (
        "\\begin{tikzpicture}\n"
        "\\begin{axis}[scale only axis,width=104mm,height=70mm,"
        "xlabel={Flow Q (m\\textsuperscript{3}/h)},ylabel={Head H (m)},"
        "xmin=0,xmax=470,ymin=0,ymax=115,ymajorgrids,"
        "grid style={rule},axis lines=left,axis line style={rule,line width=0.5pt},"
        "tick style={draw=none},tick label style={font=\\scriptsize,text=mute},"
        "label style={font=\\scriptsize,text=mute},xtick={0,100,...,400},ytick={0,25,...,100},"
        "clip=false]\n" + "\n".join(plots) + "\n\\end{axis}\n\\end{tikzpicture}"
    )


def key_rows() -> str:
    pump_key = list(DIM_TEXT.items())
    rows = []
    for i, (k, v) in enumerate(pump_key):
        mk, mv = MOTOR_KEY[i] if i < len(MOTOR_KEY) else ("", "")
        rows.append(f"{k} & {v} & {mk} & {mv} \\\\")
    return "\n".join(rows)


def main() -> None:
    body = TEMPLATE
    body = body.replace("@@PUMP_MEASURES@@", pump_measures_table())
    body = body.replace("@@MOTOR_MEASURES@@", motor_measures_table())
    body = body.replace("@@MOTOR_OVERVIEW@@", motor_overview_table())
    body = body.replace("@@CONNECTIONS@@", connections_table())
    body = body.replace("@@FLOW_CHART@@", flow_chart())
    body = body.replace("@@GLANCE@@", glance_table())
    one = "\n".join(f"{k} & {v} \\\\" for k, v in list(DIM_TEXT.items()) + MOTOR_KEY)
    body = body.replace("@@DIM_KEY_ONE@@", one)
    OUT.write_text(body)
    print("wrote", OUT)


TEMPLATE = r"""
\documentclass[9.5pt,a4paper]{article}
\usepackage[margin=16mm,top=16mm,bottom=20mm]{geometry}
\usepackage[T1]{fontenc}
\usepackage[default]{lato}
\usepackage[table]{xcolor}
\usepackage{tabularx,booktabs,array,multicol,enumitem,fancyhdr,tikz,pgfplots,graphicx}
\pgfplotsset{compat=1.18}
\usetikzlibrary{calc,positioning}
\usepackage[hidelinks]{hyperref}

\definecolor{ink}{HTML}{2B2D2F}
\definecolor{accent}{HTML}{D9622B}
\definecolor{sand}{HTML}{F4F1EC}
\definecolor{rule}{HTML}{D2CDC5}
\definecolor{mute}{HTML}{6E6A64}
\definecolor{photo}{HTML}{ECE9E4}

\color{ink}
\setlength{\parindent}{0pt}
\setlength{\parskip}{4pt}
\setlength{\columnsep}{7mm}
\renewcommand{\arraystretch}{1.3}
\arrayrulecolor{rule}
\setlength{\tabcolsep}{3pt}
\setlist[itemize]{leftmargin=4mm,itemsep=0pt,parsep=1pt,topsep=1pt,label=\textcolor{accent}{\rule[0.5ex]{1.2mm}{1.2mm}}}
\setlist[enumerate]{leftmargin=5mm,itemsep=0pt,parsep=1pt,topsep=1pt,label=\textcolor{accent}{\bfseries\arabic*}}

% Numbered section: accent number, charcoal heading, hairline below.
\newcommand{\sect}[2]{\par\vspace{4mm}%
  {\fontsize{13}{15}\selectfont{\color{accent}\bfseries #1}\hspace{2mm}{\bfseries #2}}\par
  \vspace{1.2mm}{\color{rule}\hrule height 0.5pt}\vspace{2mm}}
\newcommand{\sub}[1]{\par\vspace{1mm}{\color{ink}\bfseries #1}\par\vspace{0.6mm}}
\newcommand{\hdr}{}
\newcommand{\ghl}{\arrayrulecolor{accent}\specialrule{0.8pt}{0pt}{1pt}\arrayrulecolor{rule}}
% Key/value table: a bold caption, an accent hairline, then rows separated by light rules.
\newenvironment{kv}[1]{%
  \par\vspace{2mm}%
  \tabularx{\linewidth}{@{}p{0.5\linewidth}X@{}}%
  \multicolumn{2}{@{}l}{\textbf{#1}} \\ \ghl
}{\endtabularx\par}
\newcommand{\kvr}[2]{#1 & #2 \\ \hline}
% Full-width striped table.
\newcolumntype{C}{>{\centering\arraybackslash}X}
\newenvironment{wide}[2]{\par\noindent\begingroup#1\rowcolors{2}{sand}{white}\tabularx{\textwidth}{@{}#2@{}}}{\endtabularx\endgroup\par}

\pagestyle{fancy}
\fancyhf{}
\renewcommand{\headrulewidth}{0pt}
\renewcommand{\footrulewidth}{0.5pt}
\renewcommand{\footrule}{\color{accent}\hrule width\headwidth height 0.5pt}
\lfoot{\footnotesize\color{mute}Norrhavn PX series \textperiodcentered{} Datasheet PX-DS-EN 2026-10}
\rfoot{\footnotesize\color{mute}\thepage\,/\,4}

\begin{document}

% ---------------------------------------------------------------- page 1
% Wordmark: an accent square with the initial, the name beside it.
\begin{tikzpicture}[baseline=(name.base)]
  \fill[accent] (0,0) rectangle (6mm,6mm);
  \node[text=white,font=\bfseries\large] at (3mm,3mm) {N};
  \node[anchor=west,font=\bfseries\large,inner sep=0] (name) at (8mm,3.4mm) {NORRHAVN};
  \node[anchor=west,font=\scriptsize,text=mute,inner sep=0] at (8mm,0.6mm) {Fluid Technology};
\end{tikzpicture}
\hfill{\footnotesize\color{mute}Centrifugal pumps \textperiodcentered{} PX series}

\vspace{9mm}
{\fontsize{34}{36}\selectfont\bfseries PX series}\par
\vspace{2.5mm}
{\fontsize{13}{16}\selectfont\color{mute}Close-coupled hygienic centrifugal pumps, 5 to 420 m\textsuperscript{3}/h}\par
\vspace{6mm}

% Photo on the left, key facts in a dark panel on the right, both bleeding slightly past the margin.
\noindent\begin{tikzpicture}[x=1mm,y=1mm]
  \clip (0,0) rectangle (178,62);
  % The photo keeps its full height; its own background colour fills the rest of the slot.
  \fill[photo] (0,0) rectangle (112,62);
  \node[anchor=south,inner sep=0] at (56,0) {\includegraphics[height=62mm]{pump-render-v1-crop.png}};
  \fill[ink] (112,0) rectangle (178,62);
  \foreach \y/\num/\unit/\what in {52/10/sizes/one hydraulic family, 38/420/{m\textsuperscript{3}/h}/maximum flow, 24/10/bar/maximum differential pressure, 10/140/{\textdegree C}/maximum product temperature} {
    \node[anchor=base west,text=white,font=\fontsize{18}{18}\selectfont\bfseries,inner sep=0] (n) at (118,\y) {\num};
    \node[anchor=base west,text=accent,font=\small\bfseries,inner sep=0] at ([xshift=1.5mm]n.base east) {\unit};
    \node[anchor=north west,text=white!75!ink,font=\scriptsize,inner sep=0] at ([yshift=-1.2mm]n.south west) {\what};
  }
\end{tikzpicture}

\vspace{4mm}
\begin{multicols}{3}
\sub{Overview}
The PX is a close-coupled centrifugal pump for hygienic and light process
duties. The hydraulic parts are machined in one setup, so the impeller runs with
small clearances and little recirculation: a lower power draw than open-impeller
pumps of the same size, and a flat efficiency curve around the best point.

A compression coupling fixes the stub shaft to the motor shaft and keeps the
alignment without shims. The semi-open impeller with swept vanes moves the
product with little shear.

\sub{Where it is used}
Dairy, brewing, beverage, food and personal care plants where the product must
not be sheared and the pump must be back in service quickly after cleaning. The
PX is made for cleaning-in-place (CIP) and sterilisation-in-place (SIP):
drainable casing, no dead legs, verified CIP cleanability.

Ten sizes cover capacities up to 420 m\textsuperscript{3}/h and differential
pressures up to 10 bar at 50 Hz, so a duty is met by one pump near its best
point rather than two in series or parallel.

\columnbreak
\sub{Design}
All product-wetted steel parts (casing, impeller, impeller nut and back plate)
are EN 1.4404 (AISI 316L). A stainless shroud covers the motor and four
adjustable stainless legs carry the unit.

The standard seal is a single mechanical shaft seal; a flushed single seal and a
double mechanical seal are options. The seal loads from the front, with the
spring and washers on the atmospheric side, so a seal change takes minutes
without removing the pipework, and the balanced design holds through pressure
shocks.
\end{multicols}

\sect{01}{The range at a glance}
@@GLANCE@@

\vfill
{\footnotesize\color{mute}Norrhavn Fluid Technology is a fictional company and the PX series a fictional product. This sheet was written for software demonstrations; its values are invented and must not be used for engineering decisions.}

% ---------------------------------------------------------------- page 2
\newpage
\sect{02}{Technical data}
\begin{minipage}[t]{0.48\textwidth}
\begin{kv}{Materials}
\kvr{Product wetted steel parts}{EN 1.4404 (AISI 316L)}
\kvr{Other steel parts}{Stainless steel}
\kvr{Inside surface finish}{Ra $\le$ 1.6 $\mu$m, glass-bead blasted}
\kvr{Product wetted elastomers}{EPDM}
\kvr{Rotary seal face}{Carbon}
\kvr{Stationary seal face}{Silicon carbide}
\end{kv}

\begin{kv}{Motor sizes}
\kvr{50 Hz}{0.75 -- 110 kW}
\kvr{60 Hz}{0.75 -- 110 kW}
\end{kv}

\begin{kv}{Min/max motor speed}
\kvr{2 poles, 0.75 -- 45 kW}{900 -- 4000 rpm}
\kvr{2 poles, 55 -- 110 kW}{900 -- 3600 rpm}
\kvr{4 poles, 0.75 -- 75 kW}{900 -- 2200 rpm}
\end{kv}
\end{minipage}\hfill
\begin{minipage}[t]{0.48\textwidth}
\begin{kv}{Motor}
\multicolumn{2}{@{}p{\linewidth}}{Foot-flanged IEC motor. 2 poles = 3000/3600 rpm at 50/60 Hz, 4 poles = 1500/1800 rpm at 50/60 Hz. IP 55 with drain hole and labyrinth plug, insulation class F, efficiency class IE3.} \\ \hline
\end{kv}

\begin{kv}{Warranty}
\multicolumn{2}{@{}p{\linewidth}}{Three years on PX pumps, covering all non-wear parts, on the condition that Norrhavn service parts are used.} \\ \hline
\end{kv}

\begin{kv}{Noise}
\kvr{Sound pressure at 1 m, 2 poles, 50 Hz}{Max 78 dB(A) to PX-55, max 84 dB(A) from PX-70}
\end{kv}
\end{minipage}

\sect{03}{Operating data}
\begin{minipage}[t]{0.48\textwidth}
\begin{kv}{Max inlet pressure}
\kvr{PX-5}{600 kPa (6 bar)}
\kvr{PX-10 -- PX-70}{1000 kPa (10 bar)}
\kvr{PX-70, 60 Hz}{500 kPa (5 bar)}
\kvr{PX-85 -- PX-100}{500 kPa (5 bar)}
\end{kv}

\begin{kv}{Temperature}
\kvr{Temperature range}{-10 \textdegree C to +140 \textdegree C (EPDM)}
\kvr{Flush media}{Max 70 \textdegree C}
\kvr{Flush housing sterilisation (pump not in operation)}{Max 125 \textdegree C}
\end{kv}
\end{minipage}\hfill
\begin{minipage}[t]{0.48\textwidth}
\begin{kv}{Flushed shaft seal}
\kvr{Water pressure inlet}{Max 1 bar}
\kvr{Water consumption}{0.25 -- 0.5 l/min}
\end{kv}

\begin{kv}{Double mechanical shaft seal}
\kvr{Water pressure inlet, PX-5 to PX-55}{Max 500 kPa (5 bar)}
\kvr{Water pressure inlet, PX-70 to PX-100}{Max 300 kPa (3 bar)}
\kvr{Water consumption}{0.25 -- 0.5 l/min}
\end{kv}

\begin{kv}{Seal flush connections}
\kvr{PX-5 -- PX-70, PX-100}{1/8" G}
\kvr{PX-85}{\O{}6 tube}
\end{kv}
\end{minipage}

% ---------------------------------------------------------------- page 3
\newpage
\sect{04}{Dimensions}
\begin{minipage}[t]{0.60\textwidth}
\vspace{0pt}
\begin{tikzpicture}[x=0.38mm,y=0.38mm,line cap=round,line join=round,
  dim/.style={<->,>=latex,line width=0.4pt,draw=ink},
  ext/.style={line width=0.3pt,draw=mute},
  part/.style={line width=0.5pt,draw=ink,fill=white},
  lab/.style={font=\footnotesize\bfseries,text=accent,fill=white,inner sep=1pt}]
  % ---- front view (looking into the suction)
  \begin{scope}
    \draw[part] (0,0) circle (26);
    \draw[part] (0,0) circle (16);
    \draw[part] (0,0) circle (7);
    \draw[part] (-5,26) rectangle (5,44);
    \draw[part] (-8,44) rectangle (8,47);
    \draw[part] (-36,-26) rectangle (36,-21);
    \foreach \x in {-26,26} {\draw[part] (\x-2,-21) rectangle (\x+2,-26);}
    \draw[ext] (0,47) -- (0,60);
    \draw[ext] (0,0) -- (62,0);
    \draw[ext] (8,47) -- (62,47);
    \draw[dim] (56,0) -- (56,47) node[midway,lab,right=1pt] {C};
    \draw[ext] (-36,-26) -- (-36,-40); \draw[ext] (36,-26) -- (36,-40);
    \draw[dim] (-36,-36) -- (36,-36) node[midway,lab,below=1pt] {F};
    \draw[ext] (-26,-21) -- (-26,-48); \draw[ext] (26,-21) -- (26,-48);
    \draw[dim] (-26,-46) -- (26,-46) node[midway,lab,below=1pt] {H};
    \draw[ext] (-26,0) -- (-46,0); \draw[ext] (0,26) -- (-46,26);
    \draw[dim] (-40,-26) -- (-40,26) node[midway,lab,left=1pt] {D};
    \draw[dim] (-50,-26) -- (-50,0) node[midway,lab,left=1pt] {B};
    \node[font=\scriptsize,text=mute] at (0,-56) {Front};
  \end{scope}
  % ---- side view (motor to the right)
  \begin{scope}[shift={(150,0)}]
    \draw[part] (-32,-26) rectangle (64,-21);
    \draw[part] (-20,-21) rectangle (18,23);     % casing
    \draw[part] (18,-16) rectangle (28,18);     % lantern
    \draw[part] (28,-19) rectangle (92,21);     % motor
    \draw[part] (92,-12) rectangle (98,14);     % fan cover
    \draw[part] (-26,-5) rectangle (-20,7);     % suction nozzle
    \draw[part] (-30,-7) rectangle (-26,9);     % suction flange
    \draw[part] (-6,23) rectangle (4,41);       % discharge nozzle
    \draw[part] (-9,41) rectangle (7,44);       % discharge flange
    \foreach \x in {-8,52} {\draw[part] (\x,-21) rectangle (\x+4,-26);}
    \draw[dash pattern=on 4pt off 1.5pt on 1pt off 1.5pt,line width=0.3pt] (-34,1) -- (102,1);
    \draw[ext] (-30,9) -- (-30,56); \draw[ext] (-1,44) -- (-1,56);
    \draw[dim] (-30,52) -- (-1,52) node[midway,lab,above=1pt] {A};
    \draw[ext] (-32,-26) -- (-32,-44); \draw[ext] (64,-26) -- (64,-44);
    \draw[dim] (-32,-40) -- (64,-40) node[midway,lab,below=1pt] {E};
    \draw[ext] (-6,-26) -- (-6,-52); \draw[ext] (54,-26) -- (54,-52);
    \draw[dim] (-6,-49) -- (54,-49) node[midway,lab,below=1pt] {G};
    \draw[ext] (28,21) -- (28,34); \draw[ext] (98,14) -- (98,34);
    \draw[dim] (28,30) -- (98,30) node[midway,lab,above=1pt] {J};
    \draw[ext] (92,21) -- (108,21); \draw[ext] (92,-19) -- (108,-19);
    \draw[dim] (104,-19) -- (104,21) node[midway,lab,right=1pt] {K};
    \draw[ext] (-30,-26) -- (-30,-60); \draw[ext] (98,-12) -- (98,-60);
    \draw[dim] (-30,-58) -- (98,-58) node[midway,lab,below=1pt] {N};
    \node[font=\scriptsize,text=mute] at (34,-66) {Side};
  \end{scope}
\end{tikzpicture}
\end{minipage}\hfill
\begin{minipage}[t]{0.37\textwidth}
\vspace{0pt}
\colorbox{sand}{\begin{minipage}{\dimexpr\linewidth-2\fboxsep}
\footnotesize
\textbf{Letter key}\par\vspace{1mm}
\begin{tabularx}{\linewidth}{@{}>{\leavevmode\color{accent}\bfseries}p{4mm}X@{}}
@@DIM_KEY_ONE@@
\end{tabularx}
\end{minipage}}
\end{minipage}

\sub{Pump specific measures (mm)}
@@PUMP_MEASURES@@
{\footnotesize \textsuperscript{2} Pump with the smallest standard motor, dry.}

\sub{Motor specific measures (mm)}
@@MOTOR_MEASURES@@
{\footnotesize N is given for the largest pump of each group; smaller pumps in the group are shorter by the difference in A.}

\sub{Motor overview}
@@MOTOR_OVERVIEW@@
{\footnotesize PX-5 to PX-85: 2-pole motors. PX-100: 4-pole motors.}

% ---------------------------------------------------------------- page 4
\newpage
\sect{05}{Connections}
@@CONNECTIONS@@
{\footnotesize \textsuperscript{1} Other sizes on request. M1 and M2 are the face-to-centre distances of the inlet and outlet fittings in mm.}

\sect{06}{Performance}
\begin{minipage}[t]{0.70\textwidth}
\vspace{0pt}
@@FLOW_CHART@@
\end{minipage}\hfill
\begin{minipage}[t]{0.27\textwidth}
\vspace{4mm}\small
\textbf{Test conditions}\par
{\color{rule}\hrule height 0.5pt}\vspace{1mm}
Frequency 50 Hz.\par
Synchronous speed 3000 rpm.\par
Water at 20 \textdegree C.\par
Full impeller diameter.\par
\vspace{2mm}
Each curve ends at the largest flow for continuous duty. Reduced impeller
diameters move a curve down; ask for the selection program for intermediate
points.
\end{minipage}

\vspace{2mm}
\begin{minipage}[t]{0.56\textwidth}
\sect{07}{Options}
\begin{itemize}
  \item Impeller with reduced diameter.
  \item Flushed shaft seal.
  \item Double mechanical shaft seal.
  \item Rotating seal face of silicon carbide.
  \item Product wetted elastomers FKM or FEP.
  \item 1/2" vertical drain connection.
  \item Product wetted surface finish polished to Ra $\le$ 0.8 $\mu$m, with or without certificate.
  \item Inducer (PX-10 to PX-55).
  \item Adjustable pads under the legs.
  \item Motor for other voltage and/or frequency.
  \item Half-speed motor.
  \item Increased-safety or flameproof motor.
  \item ATEX execution (PXex).
\end{itemize}
\end{minipage}\hfill
\begin{minipage}[t]{0.40\textwidth}
\sect{08}{Specifying a pump}
State the following with an enquiry or order:
\begin{enumerate}
  \item Pump size.
  \item Connections.
  \item Impeller diameter.
  \item Motor size.
  \item Voltage and frequency.
  \item Flow, pressure and temperature.
  \item Density and viscosity of the product.
  \item Options.
\end{enumerate}
\end{minipage}

\vfill
{\footnotesize\color{mute}
Norrhavn Fluid Technology is a fictional company and the PX series a fictional product. This sheet was written for software demonstrations of document-grounded data extraction. Its text, drawings, tables and values are invented and must not be used for engineering decisions. The sheet may be copied and redistributed freely.}

\end{document}
"""

if __name__ == "__main__":
    main()
