/**
 * shadcn-style Popover — thin wrapper around @radix-ui/react-popover.
 *
 * Used by the NodeContextToolbar chips (Fill / Stroke / Text) to anchor a
 * single-level swatch panel above the chip itself. Each chip owns its own
 * Popover so the panels can't stack-collide with one another (the bug we
 * had when Style → Fill + Stroke shared an anchor and Radix layered them
 * at the same `z-index`).
 *
 * Always portals via `PopoverPortal` so the panel escapes any
 * `overflow: hidden` on the canvas / toolbar ancestor.
 */
import * as PopoverPrimitive from "@radix-ui/react-popover";
import {
  forwardRef,
  type ComponentPropsWithoutRef,
  type ElementRef,
} from "react";

import { cn } from "@/lib/cn";

const Popover = PopoverPrimitive.Root;
const PopoverTrigger = PopoverPrimitive.Trigger;
const PopoverPortal = PopoverPrimitive.Portal;
const PopoverAnchor = PopoverPrimitive.Anchor;

const PopoverContent = forwardRef<
  ElementRef<typeof PopoverPrimitive.Content>,
  ComponentPropsWithoutRef<typeof PopoverPrimitive.Content>
>(({ className, sideOffset = 6, align = "center", ...props }, ref) => (
  <PopoverPortal>
    <PopoverPrimitive.Content
      ref={ref}
      sideOffset={sideOffset}
      align={align}
      className={cn(
        "z-50 rounded-md border border-neutral-200 bg-white p-2 text-neutral-700 shadow-md",
        "data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
        className,
      )}
      {...props}
    />
  </PopoverPortal>
));
PopoverContent.displayName = PopoverPrimitive.Content.displayName;

export { Popover, PopoverTrigger, PopoverContent, PopoverPortal, PopoverAnchor };
