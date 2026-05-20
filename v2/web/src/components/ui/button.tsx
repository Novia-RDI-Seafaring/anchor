/**
 * shadcn-style Button — minimal variants tailored to Anchor's neutral palette.
 */
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1 rounded transition disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-neutral-400",
  {
    variants: {
      variant: {
        default:
          "bg-neutral-900 text-white hover:bg-neutral-800",
        ghost:
          "bg-transparent text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900",
        outline:
          "border border-neutral-300 bg-white text-neutral-700 hover:bg-neutral-50",
      },
      size: {
        sm: "h-7 px-2 text-xs",
        icon: "h-6 w-6 p-0",
        md: "h-8 px-3 text-sm",
      },
    },
    defaultVariants: { variant: "ghost", size: "sm" },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
