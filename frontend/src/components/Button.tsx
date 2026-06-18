import type { ButtonHTMLAttributes, ReactNode } from "react";

import { clsx } from "clsx";

type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  icon?: ReactNode;
  variant?: ButtonVariant;
}

const variantClass: Record<ButtonVariant, string> = {
  primary: "border-forest bg-forest text-white hover:bg-[#185c42]",
  secondary: "border-line bg-panel text-ink hover:bg-[#eef2ec]",
  danger: "border-rose bg-rose text-white hover:bg-[#963030]",
  ghost: "border-transparent bg-transparent text-ink hover:bg-[#eef2ec]",
};

export function Button({
  children,
  icon,
  variant = "secondary",
  className,
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      className={clsx(
        "inline-flex h-9 items-center justify-center gap-2 rounded-md border px-3 text-sm font-medium",
        "transition focus:outline-none focus:ring-2 focus:ring-cobalt/30",
        "disabled:cursor-not-allowed disabled:opacity-55",
        variantClass[variant],
        className,
      )}
      disabled={disabled}
      {...props}
    >
      {icon}
      <span className="truncate">{children}</span>
    </button>
  );
}
