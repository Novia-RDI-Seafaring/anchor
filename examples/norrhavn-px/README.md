# Norrhavn PX: an example datasheet

A four-page product datasheet for a fictional centrifugal pump series,
written for demonstrations of document-grounded extraction. Norrhavn Fluid
Technology does not exist, the PX series does not exist, and every value is
invented. The sheet may be copied and redistributed freely.

| File | What it is |
|---|---|
| `norrhavn-px-datasheet.pdf` | The datasheet. Real text throughout, so table cells, dimension letters and legend entries resolve to bounding boxes. |
| `norrhavn-px-42-drawing.pdf` | An outline drawing of one size (PX-42) with the dimension letters A to H. The letters match the datasheet's dimension table, so one value can be anchored in two places: the table cell and the dimension on the drawing. |
| `gen.py` | Writes the datasheet LaTeX. One table of sizes drives every table, the drawing letters and the flow-chart curves. |
| `pump-render-v1-crop.png` | The product picture on page 1. |

## What the sheet contains

- Page 1: product picture with a key-facts panel, overview / where it is used / design in three columns, and "the range at a glance" (max flow, max head, motor range, inlet and outlet per size).
- Page 2: technical data (materials, motor, motor sizes, speeds, warranty, noise) and operating data (max inlet pressure per size, temperature, flushed and double shaft seal, seal flush connections). Key/value tables in two columns.
- Page 3: a two-view dimension drawing with letters, a letter key, pump-specific measures (A to H and mass for ten sizes), motor-specific measures per IEC frame, and the motor overview.
- Page 4: connections per standard (M1, M2, DN), a performance chart with ten curves labelled by model, options, and what to state when specifying a pump.

Ten sizes: PX-5, PX-10, PX-15, PX-20, PX-30, PX-42, PX-55, PX-70, PX-85, PX-100.

## Rebuild

Needs a TeX distribution with `pgfplots`, `sourcesanspro`, `tabularx` and `tikz` (any full TeX Live or MacTeX).

```sh
python3 gen.py
pdflatex norrhavn-px.tex
pdflatex norrhavn-px.tex   # second pass places the page 1 header
```

Change a number in `SIZES`, `PX42` or `MOTORS` in `gen.py` and rebuild; the tables, the curves and page 1 follow.

## Try it in Anchor

```sh
anchor ingest examples/norrhavn-px/norrhavn-px-datasheet.pdf
anchor ingest examples/norrhavn-px/norrhavn-px-42-drawing.pdf
```

Then drag the datasheet onto a canvas and pull a row from the dimension table. The row's anchor points at the cell on page 3; the same letter appears on the drawing.
