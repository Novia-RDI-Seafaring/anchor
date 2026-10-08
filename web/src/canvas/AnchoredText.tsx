import { Fragment, useMemo } from "react";
import { useParams } from "react-router-dom";

import { isAnchorHref, parseAnchorHref } from "@/canvas/anchorHref";
import { SourceRefLink } from "@/canvas/SourceRefLink";

/**
 * AnchoredText — plain text, except that `anchor:` links become anchors.
 *
 * A `markdown` card renders full Markdown. Every other text-bearing card
 * renders one plain string, which until now meant a source link written
 * in a `fact`, a `note` or a `text` element arrived on the canvas as
 * literal square brackets. So the only way to write one sentence with
 * provenance was to reach for a `markdown` card, which quietly made the
 * simple cards the tier where claims go unanchored. That is backwards
 * for this application: pointing at your source is the one thing every
 * element should be able to do.
 *
 * This renders `[words](anchor:...)` as a SourceRefLink and leaves
 * everything else exactly as typed. Deliberately NOT Markdown: `**bold**`
 * stays asterisks here, because formatting is what distinguishes a
 * `markdown` card and collapsing that distinction would reformat every
 * card already on a canvas. One capability moves, the type vocabulary
 * does not.
 *
 * Non-`anchor:` links are left as text too. An http link in a plain card
 * is not a provenance claim, and turning bare text into clickable
 * outbound links is a different decision with its own risks.
 */

/** `[text](target)` — target stops at whitespace or the closing paren. */
const LINK_RE = /\[([^\]]*)\]\(([^)\s]+)\)/g;

export function AnchoredText({
  text,
  workspaceSlug,
}: {
  text: string;
  /** Owning canvas, so the viewer opens beside the right document card. */
  workspaceSlug?: string;
}) {
  const { id: routeSlug } = useParams<{ id: string }>();
  const slug = workspaceSlug ?? routeSlug;

  const parts = useMemo(() => splitAnchorLinks(text), [text]);

  // Nothing to resolve: hand back the string so the DOM stays identical
  // to what these cards rendered before.
  if (parts.length === 1 && typeof parts[0] === "string") return <>{parts[0]}</>;

  return (
    <>
      {parts.map((part, i) =>
        typeof part === "string" ? (
          <Fragment key={i}>{part}</Fragment>
        ) : (
          <SourceRefLink key={i} workspaceSlug={slug} refValue={part.ref}>
            {part.text}
          </SourceRefLink>
        ),
      )}
    </>
  );
}

type AnchorPart = { text: string; ref: ReturnType<typeof parseAnchorHref> };

/**
 * Split a string into literal runs and `anchor:` links, in order.
 *
 * A link whose target is not an `anchor:` href stays a literal run, so
 * ordinary prose containing brackets is never eaten.
 */
export function splitAnchorLinks(text: string): Array<string | AnchorPart> {
  const out: Array<string | AnchorPart> = [];
  let last = 0;
  // A fresh regex per call: /g carries lastIndex across calls otherwise.
  const re = new RegExp(LINK_RE.source, "g");
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    const whole = m[0];
    const label = m[1] ?? "";
    const href = m[2] ?? "";
    if (!isAnchorHref(href)) continue;
    if (m.index > last) out.push(text.slice(last, m.index));
    out.push({ text: label, ref: parseAnchorHref(href) });
    last = m.index + whole.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out.length > 0 ? out : [text];
}
