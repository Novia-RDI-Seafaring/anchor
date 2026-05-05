# Ingestion Pipeline — Bronze / Silver / Gold

This document describes the target architecture for turning a PDF into
structured, source-grounded knowledge that the agent and canvas can consume.
It is the working design; not everything here is implemented yet.

## Layers at a glance

```
backend/data/
├── bronze/
│   └── <doc-slug>.pdf                        # raw, as-is
│
├── silver/<doc-slug>/
│   ├── docling.json                          # raw docling export
│   ├── index.json                            # deterministic TOC (IMPLEMENTED)
│   ├── pages/
│   │   ├── 1.md                              # per-page markdown, faithful
│   │   ├── 1.png                             # 150 DPI render for VLM + UI
│   │   ├── 2.md
│   │   ├── 2.png
│   │   └── …
│   └── pages.meta.json                       # page dims, docling item ids, checksum
│
└── gold/<doc-slug>/
    ├── document.json                         # section tree + document metadata
    ├── sections/
    │   ├── technical-data.md
    │   ├── technical-data--materials.md
    │   ├── operating-data--max-inlet-pressure.md
    │   └── …
    └── sections.meta.json                    # per-section: title, path, tags,
                                              #   page_range, source_refs, kind
```

Each layer has a single clear purpose:

| Layer | Atom | Produced by | Purpose |
|---|---|---|---|
| **Bronze** | file | upload | raw substrate |
| **Silver / `docling.json`** | document | docling (already running) | structured extraction with bboxes |
| **Silver / `index.json`** | document | deterministic from docling | cheap navigation TOC |
| **Silver / `pages/N.md`** | page | deterministic from docling | faithful per-page rendering |
| **Gold / `sections/*.md`** | section | LLM pass over silver | semantic, tagged, cross-page units |

## Why per-section *and* per-page

Sections are the semantic atom, but **pages are where bboxes live**. A section
spanning pages 2–3 needs to reference specific regions on both pages. So:

- Silver owns the page atom: `pages/2.md` is the ground-truth per-page rendering.
  Every md element traces back to docling items with bboxes.
- Gold owns the section atom: `sections/operating-data--max-inlet-pressure.md`
  is the semantic unit. Its metadata lists `source_refs: [{page, bbox, ...}]`
  pointing back into silver pages.

The agent's read path:

```
document.json (tree) → pick section → sections/*.md → (for provenance) follow
source_refs into silver pages with bboxes → open the PDF at a specific region.
```

No content duplication: sections *reference* silver pages, they don't copy them.
(Sections can inline the text into their own md for easier reading; the meta
file records the refs either way.)

## Section metadata shape

```python
class SourceRef(BaseModel):
    page: int
    bbox: list[float]
    item_ids: list[str] = []        # optional: docling item ids we matched

class SectionMeta(BaseModel):
    id: str                         # "technical-data--motor--motor-sizes"
    title: str                      # "Motor sizes"
    path: list[str]                 # ["TECHNICAL DATA","Motor","Motor sizes"]
    level: int                      # 3
    parent_id: str | None
    children_ids: list[str] = []
    page_range: tuple[int, int]     # (2, 2)
    source_refs: list[SourceRef]
    tags: list[str] = []            # ["per_model","specs","motor"]
    md_file: str                    # "sections/technical-data--motor--motor-sizes.md"
    kind: Literal["narrative","property_group","table_2d","figure","mixed"]

class DocumentGold(BaseModel):
    document: DocumentMeta
    tree: list[str]                 # root section ids in order
    sections: dict[str, SectionMeta]
    schema_version: int = 1
```

The `kind` field enables different rendering downstream: canvas can turn a
`property_group` drop into a spec node, a `narrative` drop into a text card,
and a `figure` drop into an image node.

## Tags — closed vocabulary

Open-ended tagging drifts (`per_model` vs `per-model` vs `per_model_specs`).
Seed a small closed set per domain and grow it explicitly:

```
structural:  introduction, benefits, application, ordering, warranty, options
content:     narrative, property_group, table_2d, figure, cross_ref
semantic:    per_model_specs, operating_limits, materials, dimensions,
             connections, motor_specs, performance_curve, safety
entity:      mentions:lkh-5, mentions:lkh-10, …, mentions:iec80, …
```

`entity:` tags make cross-doc queries trivial ("every section tagged
`mentions:lkh-25`"). Closed vocab is enforced in the Pydantic schema —
if the LLM emits a new tag, validation fails and we review.

## Two representations per page

Doing the exercise of "produce markdown and JSON for this page" on pages 2
and 3 of the Alfa Laval LKH leaflet exposed a sharp split:

- **Page 2** (all property groups) — markdown is clean and more useful than
  JSON. `Materials`, `Motor sizes`, `Max inlet pressure` etc. are all
  label→value lists. No real 2D tables.
- **Page 3** (all real 2D tables + a load-bearing figure) — markdown gets wide
  and awkward; JSON handles grouped columns and composite row keys cleanly.

Takeaway: **gold carries both views**. Per page (and per section):

- `markdown`: the natural-reading rendering
- `blocks`: structured JSON when the content needs precise lookup

The LLM emits both in a single structured-output call; the reader (agent
or UI) picks which one it wants.

### Block types (refined from the schema sketch)

```python
class Figure(BaseModel):
    kind: Literal["chart","diagram","photo","schematic","other"]
    description: str                  # verbose enough to stand alone
    legend: dict[str, str] = {}       # for charts
    axes: dict[str, str] = {}         # for charts

class TableColumn(BaseModel):
    label: str
    models: list[str] = []            # present when the column represents a group

class TableRow(BaseModel):
    key: str                          # flat composite ok ("Clamp ISO 2037 — M1")
    note_ref: int | None = None
    values: dict[str, str | None]     # keyed by individual unit, not group label

class Table(BaseModel):
    title: str
    description: str | None = None
    row_header: str
    columns: list[str | TableColumn]  # list[str] simple, list[TableColumn] grouped
    rows: list[TableRow]
    notes: dict[str, str] = {}        # footnote index -> text

class Section(BaseModel):
    title: str
    description: str | None = None
    properties: dict[str, str] | None = None
    tables: list[Table] = []
    figures: list[Figure] = []
    subsections: list["Section"] = []

class PageContent(BaseModel):
    page: int
    markdown: str
    sections: list[Section]
```

### Design notes from the cold-drafting exercise

- **Property groups ≠ tables.** Most "tables" on spec pages are `{label: value}`
  pairs styled as tables. Keep `properties` and `tables` as separate first-class
  block types, not one reduced to the other.
- **Grouped columns expand.** The Connections table groups models
  (`LKH-10 / 20 / 35`) into shared columns. Gold expands `row.values` to key on
  individual models so lookup is direct, and preserves the group in `columns`
  so the grouping is still legible. Some redundancy, much simpler queries.
- **Composite row keys flattened.** `Clamp ISO 2037 — M1` rather than
  `{Clamp ISO 2037: {M1: ...}}`. Rows become independently addressable with no
  traversal logic.
- **Transpose freely.** The PDF lays out "Motor overview" as 13 cols × 1 row;
  gold transposes to 13 rows × 1 col because queries are keyed on pump model.
  The extractor is allowed to choose the orientation that makes lookup easy.
- **Figures can be load-bearing.** Without the diagram caption on p3, all the
  dimension-letter keys are meaningless. VLM-generated descriptions are not
  decoration — they're content.

## Regions layer — visual atoms with crops

Sections are good for "bag of properties under a heading" pages. Some pages
aren't shaped that way: a page of performance curves is six self-contained
visual blocks (spec card + H/Q chart + P/Q chart, ×2 frequencies). Docling
sees scattered text + a few pictures. The semantic atoms are *regions*.

A **region** is a logical block on a page: a chart, a spec card, a table, a
labelled diagram. Each region has:

- a bbox on the page
- a `kind` (chart / spec_block / table / figure / diagram / text)
- a title + standalone description (VLM-grade — the description is enough to
  understand the region without seeing it)
- optional `markdown` (when the content is renderable as text)
- optional `data` (structured payload — chart series, spec props, table)
- closed-vocab `tags` and `entities` (`mentions:lkh-5`, `50hz`, `h-q-curve`)
- one or more crops: PNG always, SVG/mini-PDF when the source is vector
- a back-link to silver page + bbox

Regions live in **gold**, not silver: they are LLM output and not
deterministic. Sections (existing gold concept) and regions coexist —
sections are semantic groupings, regions are visual atoms. A section can
reference regions by id; a region can stand alone (a chart dropped onto the
canvas doesn't need a parent section).

```
gold/<slug>/
├── document.json
├── pages/
│   ├── 1.regions.json           # list[Region]
│   ├── 1/                       # cropped assets, region id = filename stem
│   │   ├── r1-spec-lkh5-50hz.png
│   │   ├── r2-curve-h-q-50hz.svg
│   │   └── …
│   └── 2.regions.json
└── sections/                    # optional, may reference region ids
```

### Region schema

```python
class RegionCrop(BaseModel):
    png: str                          # always present, relative to gold dir
    svg: str | None = None            # vector when the source allows
    pdf: str | None = None            # mini-pdf for exact reproduction

class Region(BaseModel):
    id: str                           # "p1-r2-curve-h-q-50hz"
    page: int
    bbox: list[float]                 # BOTTOMLEFT, PDF coordinates
    kind: Literal["chart","spec_block","table","figure","diagram","text","caption"]
    title: str
    description: str
    markdown: str | None = None
    data: dict | None = None
    tags: list[str] = []              # closed vocab
    entities: list[str] = []          # ["mentions:lkh-5", ...]
    crops: RegionCrop
    source_refs: list[SourceRef] = [] # docling items the region absorbed
```

### Two-pass production

1. **VLM pass** — input: silver page PNG + the page's docling text items
   (so the model can ground itself in real text instead of OCR-ing the
   image). Output: list[Region] without crops, with *approximate* pixel
   bboxes. Tags from the closed vocab; freeform tags fail Pydantic
   validation and we re-prompt.

2. **Deterministic snap + crop pass** — for each region:
   - convert pixel bbox → PDF coords using the page render scale
   - **snap** the box to docling items: any docling item whose bbox center
     falls inside the VLM box is absorbed; the final region bbox is the
     union of those items. Robust to VLM coordinate noise — the model only
     has to point at the right neighborhood.
   - **crop**:
     - PNG: PyMuPDF `page.get_pixmap(clip=rect, dpi=200)`
     - SVG: `page.get_svg_image(...)` clipped (vector preserved for
       charts/diagrams)
     - mini-PDF: new doc + `insert_pdf` + `set_cropbox(rect)` (exact, smallest)
   - PNG always; SVG + mini-PDF only when `kind in {chart, diagram, figure}`.

### Why both regions and sections

- Sections answer "what does this document say about X?" — semantic groupings.
- Regions answer "what's the canonical visual block for this thing?" — needed
  the moment a chart, diagram, or labelled photo is *itself* the answer.

A drag-onto-canvas UX maps to regions: drop the H/Q curve, get a node with
the SVG + description + entities + a back-link to the page. No re-rendering
at drop time, no LLM call at drop time.

## Bboxes: LLM emits semantics, docling provides coordinates

The LLM extraction step **does not deal with bboxes**. It reads the page image
+ docling text items and emits the structured page content. A deterministic
second pass walks the emitted content and joins each value to docling items by
fuzzy text match, copying the bbox across.

Why: frontier models are unreliable at coordinates, and we already have all
the bboxes. Splitting the task cleanly — *LLM does semantics, docling does
coordinates, we glue them* — is much more robust than asking the model to do
both.

## Relation to docling's hierarchical chunker

Docling's `HierarchicalChunker` produces chunks tagged with heading ancestry
and page/bbox. It is related to — but not the same as — gold sections:

| | Docling chunker | Gold sections |
|---|---|---|
| Purpose | Feed a RAG embedding store | Semantic units for agent + canvas |
| Atom size | RAG-friendly (~200–500 tokens) | Whatever the section actually is |
| Output | list of chunks w/ heading paths | tree of sections w/ tags + provenance |
| Splits sections? | yes (when large) | no — section is the unit |
| Merges tiny ones? | sometimes | no |
| Tags | no | yes |
| Semantics | text + metadata | markdown + typed kind |

But it's a useful **input** to gold extraction — it already identifies section
boundaries and heading ancestry, which lets us start gold building from a
deterministic skeleton instead of recovering structure from flat docling items.

### Page-spanning sections

When a section crosses a page boundary (e.g. a big table that starts at the
bottom of p2 and continues on p3), docling's chunker may split it. Gold
**merges** such splits before turning them into a section: if consecutive
chunks share the same heading ancestry, concatenate their content into one
section. The section atom is the logical unit, not the page-bounded fragment.

## Gold extraction — three-step recipe

```
1. Deterministic skeleton from docling hierarchical chunks
   → section tree: ids, titles, paths, page_range, initial source_refs
   → save as sections.meta.json (tags + md empty)

2. LLM per section (pass 1)
   → input: section text (from silver pages) + page image if section contains figures
   → output: PageContent-style structured JSON + markdown + suggested tags
   → VLM only when section includes a figure

3. Deterministic cross-link (pass 2)
   → walk the emitted markdown/blocks
   → fuzzy-match every value against docling items on the section's pages
   → resolve source_refs with bboxes
   → persist sections/*.md and updated sections.meta.json
```

Each section is re-extractable independently. Re-running step 2 for a single
section doesn't touch the rest of the gold tree.

## Where we are today (2026-04-08)

- ✅ **Silver `docling.json`** — produced at upload by `ingestion/bronze.py`
  through `ingestion/pipeline.py`
- ✅ **Silver `index.json`** — deterministic builder + rebuild script
  (`src/ingestion/silver.py`, `scripts/rebuild_indexes.py`)
- ✅ **Agent reads index** — `capabilities/context.py` auto-loads index for
  every document on the canvas when gold is unavailable
- ⏳ **Silver `pages/N.md`** — not yet built
- ⏳ **Silver `pages.meta.json`** — not yet built
- ⏳ **Gold `sections/*.md` + `document.json`** — alfa-laval hand-crafted today;
  extractor not written
- ⏳ **Closed-vocab tag system** — not yet defined in code
- ⏳ **Bbox backfill pass** — source refs exist per table row in curated gold
  but no deterministic fuzzy-match utility yet

## Next narrow slice

1. **Deterministic silver per-page md renderer** (`silver.py::render_pages_md`)
   - walks docling items in reading order, emits `pages/N.md` grouped by heading
   - no LLM
   - `rebuild_indexes.py` also emits page md alongside `index.json`
2. **Deterministic silver per-page image renderer** (`silver.py::render_pages_png`)
   - PyMuPDF `page.get_pixmap(dpi=150)` over the bronze PDF, writes `pages/N.png`
   - default 150 DPI, overridable per-doc; regenerable any time
   - feeds the gold VLM pass and the canvas page-preview UI
3. **Context loader fallback** — if gold is missing but silver md exists,
   inject the relevant silver page md into the agent's context
4. **Then** start on gold extraction (LLM pass over silver pages → section
   tree with tags + source refs)

This gives a clean markdown reading experience for any doc on the canvas
without requiring any LLM work, and sets up the gold extractor to read from
silver pages rather than raw docling items.

## Open questions

- ~~Deterministic silver-md vs LLM-polished silver-md~~ — **decided**: silver
  page md is LLM-polished. The deterministic walk is the seed input to a
  vision LLM call (`silver.polish_pages_md`), which gets the page PNG, the
  raw md, and the docling items, and emits clean markdown. Pages with few
  items and no tables/pictures skip the polish (`needs_polish` heuristic) so
  pure narrative pages stay free. Real client plugged at call site,
  injectable for tests.
- Where do FMU files live in the pipeline? Bronze for the `.fmu`, silver for
  `modelDescription.xml` + extracted variable list, no gold. Likely a parallel
  asset type rather than part of the doc pipeline. Out of scope for this doc.
- Per-section vs per-page gold re-extraction cost. Section is the logical unit
  but a single section can be long — worth timing an LLM call on the biggest
  section in the corpus before committing to per-section as the atom.
