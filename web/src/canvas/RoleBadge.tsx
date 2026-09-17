/**
 * RoleBadge — small chip naming the part a card plays in an argument.
 *
 * Sits at the top-RIGHT of a card. The other two corners are taken: the
 * review badge owns the top-left and the placeholder chip shares the right
 * edge, so a card carrying a placeholder hint gets the role chip nudged
 * along rather than stacked on top of it.
 *
 * Always renders the word, not only a colour. A canvas is read zoomed out
 * and by people who do not all see colour the same way, so the colour is
 * the fast path and the word is what survives.
 */
import { roleOf, ROLE_STYLES } from "./role";
import type { MaybeData } from "./placeholder";

export function RoleBadge({
  data,
  /** Shift left when the placeholder chip already occupies the corner. */
  offset = false,
}: {
  data: MaybeData;
  offset?: boolean;
}) {
  const role = roleOf(data);
  if (!role) return null;
  const style = ROLE_STYLES[role];
  return (
    <div
      data-testid="role-badge"
      data-role={role}
      className={`pointer-events-none absolute -top-2.5 z-10 rounded-full px-1.5 py-0.5 text-[10px] font-medium shadow-sm ${
        offset ? "right-16" : "right-2"
      }`}
      style={{ color: style.color, background: style.bg }}
    >
      {style.label}
    </div>
  );
}
