import { DEFAULT_BG } from "./colors";

/** Show a fill color or a checkerboard when the fill is transparent. */
export function ToolbarFillSwatch({ color }: { color: string }) {
  const isTransparent = color === DEFAULT_BG || color === "transparent";
  if (isTransparent) {
    return (
      <span
        className="block h-3.5 w-3.5 rounded border border-neutral-400"
        style={{
          backgroundImage:
            "linear-gradient(45deg, #d4d4d4 25%, transparent 25%), " +
            "linear-gradient(-45deg, #d4d4d4 25%, transparent 25%), " +
            "linear-gradient(45deg, transparent 75%, #d4d4d4 75%), " +
            "linear-gradient(-45deg, transparent 75%, #d4d4d4 75%)",
          backgroundSize: "6px 6px",
          backgroundPosition: "0 0, 0 3px, 3px -3px, -3px 0px",
        }}
        aria-hidden
      />
    );
  }
  return (
    <span
      className="block h-3.5 w-3.5 rounded border border-neutral-400"
      style={{ background: color }}
      aria-hidden
    />
  );
}
