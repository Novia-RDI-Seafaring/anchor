import { Handle, NodeResizer, Position, type NodeProps } from "@xyflow/react";
import { useMemo } from "react";
import type { Components } from "react-markdown";
import Markdown, { defaultUrlTransform } from "react-markdown";
import { useParams } from "react-router-dom";
import remarkGfm from "remark-gfm";

import { isAnchorHref, parseAnchorHref } from "@/canvas/anchorHref";
import { SourceRefLink } from "@/canvas/SourceRefLink";

import { DEFAULT_BG, DEFAULT_STROKE, resolveColors, resolveText } from "@/canvas/colors";
import { PlaceholderChip } from "@/canvas/PlaceholderChip";
import { placeholderState, PLACEHOLDER_BG, PLACEHOLDER_STROKE } from "@/canvas/placeholder";
import { ReviewBadge } from "@/canvas/ReviewBadge";
import { useInlineField } from "@/canvas/useInlineField";
import { useLiveResize } from "@/canvas/useLiveResize";

/**
 * MarkdownNode — a card whose body is Markdown, rendered as rich text.
 *
 * The other text-bearing cards render one string: a note's body is prose
 * with line breaks, a fact's is a single assertion. That falls apart as
 * soon as the thing being said has structure — a short list of findings,
 * a table of three options, a snippet of code, a link back to a source.
 * Agents write exactly that shape of content, and until now it landed on
 * the canvas as raw asterisks and pipes.
 *
 * `data.text` holds the Markdown source, the same key every other card
 * uses for its body, so an agent that knows one card knows this one. It
 * renders with GitHub-flavoured extensions on: tables, task lists,
 * strikethrough, bare autolinks.
 *
 * Raw HTML in the source is escaped, never parsed. Markdown arrives here
 * from agents over MCP as often as from a person typing, so the rendering
 * path stays HTML-free by construction (no `rehype-raw`, no
 * `dangerouslySetInnerHTML`) rather than by sanitising after the fact.
 *
 * Every size in the rendered body is relative (`em`), so the node's own
 * text size scales headings, code and tables together — the size control
 * in the properties panel moves the whole card, not just its paragraphs.
 *
 * Editing:
 *   - Title (optional, single-line) — double-click the strip. It only
 *     shows when the card has a name or is selected, so an unnamed card
 *     is pure content.
 *   - Body (Markdown source) — double-click it. Enter breaks the line,
 *     because newlines are syntax here; Cmd/Ctrl+Enter or clicking away
 *     commits, Esc cancels.
 */
export function MarkdownNode({ id, data, selected }: NodeProps) {
  const d = data as {
    label?: string;
    text?: string;
    width?: number;
    height?: number;
    bg_color?: string;
    stroke_color?: string;
    text_color?: string;
  };
  const label = d.label ?? "";
  const text = d.text ?? "";
  const { id: workspaceSlug } = useParams<{ id: string }>();
  const rename = useInlineField({
    workspaceSlug: workspaceSlug ?? "",
    nodeId: id,
    value: label,
    field: "label",
    canEdit: selected ?? false,
    // The title is optional; a freshly placed card puts the caret in the
    // body instead, so it does not claim the pending-focus stamp.
    claimsPendingFocus: false,
  });
  const body = useInlineField({
    workspaceSlug: workspaceSlug ?? "",
    nodeId: id,
    value: text,
    field: "text",
    multiline: true,
    canEdit: selected ?? false,
    // The body is the card. Place one and start typing.
    claimsPendingFocus: true,
    enterKey: "newline",
  });
  const { width: liveW, height: liveH, handlers: resizeHandlers } = useLiveResize(
    d.width,
    d.height,
  );
  const { bg, stroke } = resolveColors(d);
  const t = resolveText(d);
  const components = useMemo(() => markdownComponents(workspaceSlug), [workspaceSlug]);

  const wrapStyle: React.CSSProperties = { fontSize: t.fontSize };
  if (liveW) {
    wrapStyle.width = liveW;
    wrapStyle.maxWidth = "none";
  }
  if (liveH) wrapStyle.height = liveH;
  if (bg !== DEFAULT_BG) wrapStyle.background = bg;
  if (stroke !== DEFAULT_STROKE) {
    wrapStyle.borderColor = stroke;
  }
  if (d.text_color) wrapStyle.color = t.color;
  const ph = placeholderState(d);
  if (ph.active) {
    wrapStyle.background = PLACEHOLDER_BG;
    wrapStyle.borderColor = PLACEHOLDER_STROKE;
    wrapStyle.color = PLACEHOLDER_STROKE;
    wrapStyle.borderStyle = "dashed";
  }
  const showTitle = label !== "" || (selected ?? false);
  return (
    <div
      className={`relative flex max-w-md flex-col rounded-md border border-neutral-300 bg-white px-3 py-2 text-neutral-900 shadow-sm ${
        selected ? "cursor-move" : "cursor-pointer"
      }`}
      style={wrapStyle}
    >
      {ph.active ? <PlaceholderChip hint={ph.hint} /> : null}
      <ReviewBadge data={data as Record<string, unknown>} nodeId={id} />
      <NodeResizer
        isVisible={selected ?? false}
        minWidth={160}
        minHeight={64}
        color="#0ea5e9"
        {...resizeHandlers}
      />
      <Handle type="target" position={Position.Left} />
      {showTitle ? (
        rename.editing ? (
          <input
            {...rename.inputProps}
            className={`${rename.inputProps.className} w-full rounded border border-neutral-300 bg-white px-1 py-0 font-semibold uppercase tracking-wide text-neutral-500 outline-none focus:border-sky-500`}
            style={{ fontSize: t.headingFontSize }}
            placeholder="title"
          />
        ) : (
          <div
            className={`shrink-0 uppercase tracking-wide text-neutral-500 ${
              selected ? "cursor-text" : "cursor-pointer"
            }`}
            style={{
              fontSize: t.headingFontSize,
              ...(d.text_color ? { color: t.color } : {}),
              fontWeight: Math.max(t.fontWeight, 600),
              textAlign: t.textAlign,
              fontFamily: t.fontFamily,
            }}
            onDoubleClick={(e) => {
              e.stopPropagation();
              rename.beginEdit();
            }}
            title={selected ? "double-click to name" : undefined}
          >
            {label || <span className="font-normal italic tracking-normal text-neutral-400">untitled</span>}
          </div>
        )
      ) : null}
      {body.editing ? (
        <textarea
          {...body.inputProps}
          className={`${body.inputProps.className} mt-1 min-h-[4rem] w-full flex-1 resize-none rounded border border-neutral-300 bg-white px-1 py-0.5 font-mono text-[0.9em] leading-snug text-neutral-900 outline-none focus:border-sky-500`}
          placeholder="# Markdown — Enter for a new line, Cmd+Enter to save"
        />
      ) : text ? (
        <div
          className={`nowheel mt-1 min-h-0 flex-1 overflow-y-auto leading-snug ${
            selected ? "cursor-text" : "cursor-pointer"
          }`}
          style={{
            ...(d.text_color ? { color: t.color } : {}),
            textAlign: t.textAlign,
            fontFamily: t.fontFamily,
          }}
          onDoubleClick={(e) => {
            e.stopPropagation();
            body.beginEdit();
          }}
          title={selected ? "double-click to edit the Markdown" : undefined}
        >
          <Markdown remarkPlugins={[remarkGfm]} components={components} urlTransform={urlTransform}>
            {text}
          </Markdown>
        </div>
      ) : (
        <div
          className={`mt-1 italic leading-snug text-neutral-400 ${
            selected ? "cursor-text" : "cursor-pointer"
          }`}
          onDoubleClick={(e) => {
            e.stopPropagation();
            body.beginEdit();
          }}
          title={selected ? "double-click to edit the Markdown" : undefined}
        >
          {selected ? "double-click to write Markdown" : "(empty)"}
        </div>
      )}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

/**
 * Element styling for the rendered body. Sizes are `em` so one text-size
 * control scales the whole card; spacing is tight because this is a card
 * on a canvas, not a document page.
 */
const BASE_COMPONENTS: Components = {
  h1: (props) => <h1 className="mt-2 mb-1 text-[1.5em] font-semibold first:mt-0" {...props} />,
  h2: (props) => <h2 className="mt-2 mb-1 text-[1.25em] font-semibold first:mt-0" {...props} />,
  h3: (props) => <h3 className="mt-2 mb-0.5 text-[1.1em] font-semibold first:mt-0" {...props} />,
  h4: (props) => <h4 className="mt-1.5 mb-0.5 font-semibold first:mt-0" {...props} />,
  p: (props) => <p className="my-1 first:mt-0 last:mb-0" {...props} />,
  ul: (props) => <ul className="my-1 list-disc space-y-0.5 pl-4" {...props} />,
  ol: (props) => <ol className="my-1 list-decimal space-y-0.5 pl-4" {...props} />,
  li: (props) => <li className="leading-snug" {...props} />,
  a: (props) => (
    <a
      className="text-sky-700 underline underline-offset-2"
      target="_blank"
      rel="noreferrer noopener"
      {...props}
    />
  ),
  // `anchor:` links are replaced per-card in `markdownComponents`, which
  // has the workspace slug the viewer needs.
  blockquote: (props) => (
    <blockquote className="my-1 border-l-2 border-neutral-300 pl-2 italic text-neutral-600" {...props} />
  ),
  code: (props) => (
    <code className="rounded bg-neutral-100 px-1 py-0.5 font-mono text-[0.9em]" {...props} />
  ),
  pre: (props) => (
    <pre
      className="nowheel my-1 overflow-x-auto rounded bg-neutral-100 p-2 text-[0.85em] [&_code]:bg-transparent [&_code]:p-0"
      {...props}
    />
  ),
  hr: (props) => <hr className="my-2 border-neutral-300" {...props} />,
  table: (props) => (
    <div className="nowheel my-1 overflow-x-auto">
      <table className="w-full border-collapse text-[0.9em]" {...props} />
    </div>
  ),
  th: (props) => (
    <th className="border border-neutral-300 bg-neutral-50 px-1 py-0.5 text-left font-semibold" {...props} />
  ),
  td: (props) => <td className="border border-neutral-300 px-1 py-0.5 align-top" {...props} />,
  img: (props) => <img className="my-1 max-w-full rounded" {...props} />,
};

/**
 * The element map for one card: the shared styling, plus a link handler
 * that turns `anchor:` targets into source refs. A ref needs the canvas
 * slug to open the document beside the right card, which is why this is
 * built per card rather than once at module load.
 */
function markdownComponents(workspaceSlug: string | undefined): Components {
  return {
    ...BASE_COMPONENTS,
    a: (props) => {
      const { href, children, ...rest } = props;
      if (isAnchorHref(href)) {
        return (
          <SourceRefLink workspaceSlug={workspaceSlug} refValue={parseAnchorHref(href)}>
            {children}
          </SourceRefLink>
        );
      }
      return (
        <a
          className="text-sky-700 underline underline-offset-2"
          target="_blank"
          rel="noreferrer noopener"
          href={href}
          {...rest}
        >
          {children}
        </a>
      );
    },
  };
}

/**
 * Which link targets survive into the rendered card.
 *
 * react-markdown drops unknown protocols, which is what neutralises a
 * `javascript:` link. `anchor:` is the one scheme we widen that by, and
 * deliberately: it never navigates, it opens a document in the viewer.
 */
function urlTransform(url: string): string {
  if (isAnchorHref(url)) return url;
  return defaultUrlTransform(url);
}
