import type { ComponentPropsWithoutRef, CSSProperties } from "react";

type SourceMarkProps = Omit<ComponentPropsWithoutRef<"div">, "style"> & {
  box: Pick<CSSProperties, "left" | "top" | "width" | "height">;
  flying?: boolean;
};

/** Key by placement, not reference: a new reference moves the existing mark. */
export function SourceMark({ box, flying = true, className = "", ...props }: SourceMarkProps) {
  return (
    <div
      {...props}
      aria-hidden
      className={`anchor-mark anchor-mark-fade pointer-events-none absolute${flying ? " anchor-mark-flying" : ""} ${className}`}
      style={box}
    />
  );
}
