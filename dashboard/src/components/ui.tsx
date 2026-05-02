import { Link } from "react-router-dom";
import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown } from "lucide-react";

import { clsx } from "@/lib/utils";

export function Panel({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={clsx(
        "rounded-[28px] border border-border/80 bg-mist/90 p-6 shadow-card backdrop-blur",
        className,
      )}
    >
      {children}
    </section>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
      <div className="space-y-2">
        {eyebrow ? (
          <p className="font-mono text-xs uppercase tracking-[0.32em] text-muted-foreground text-olive">
            {eyebrow}
          </p>
        ) : null}
        <div className="space-y-1">
          <h1 className="text-3xl font-semibold tracking-[-0.04em] text-ink md:text-4xl">{title}</h1>
          {description ? <p className="max-w-3xl text-sm text-stone-600 md:text-base">{description}</p> : null}
        </div>
      </div>
      {action}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <Panel className="border-dashed bg-paper/70 text-center">
      <div className="mx-auto max-w-lg space-y-3 py-8">
        <h2 className="text-xl font-semibold tracking-[-0.03em]">{title}</h2>
        <p className="text-sm text-stone-600">{description}</p>
        {action}
      </div>
    </Panel>
  );
}

export function ErrorState({
  title = "Something went wrong",
  description,
  action,
}: {
  title?: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <Panel className="border-danger/20 bg-danger/5">
      <div className="space-y-3">
        <h2 className="text-xl font-semibold text-danger">{title}</h2>
        <p className="text-sm text-stone-700">{description}</p>
        {action}
      </div>
    </Panel>
  );
}

export function LoadingCard({ label = "Loading" }: { label?: string }) {
  return (
    <Panel>
      <div className="animate-pulse space-y-4">
        <div className="h-3 w-24 rounded-full bg-sand" />
        <div className="h-8 w-56 rounded-full bg-sand/80" />
        <div className="h-24 rounded-[20px] bg-sand/70" />
      </div>
      <p className="mt-4 font-mono text-xs uppercase tracking-[0.24em] text-stone-500">{label}</p>
    </Panel>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const label = status
    .toLowerCase()
    .split("_")
    .map((chunk) => chunk.charAt(0).toUpperCase() + chunk.slice(1))
    .join(" ");
  const tone =
    status === "READY" || status === "COMPLETED" || status === "ACTIVE"
      ? "bg-success/10 text-success border-success/20"
      : status === "RUNNING" || status === "DEPLOYING"
        ? "bg-accent/10 text-accent border-accent/20"
        : status === "FAILED" || status === "DELETED"
          ? "bg-danger/10 text-danger border-danger/20"
          : "bg-warning/10 text-warning border-warning/20";

  return (
    <span
      className={clsx(
        "inline-flex h-9 min-w-[120px] items-center justify-center rounded-full border px-4 text-center font-mono text-[11px] tracking-[0.08em]",
        tone,
      )}
    >
      {label}
    </span>
  );
}

export function LabelChips({ labels }: { labels: Record<string, unknown> }) {
  const entries = Object.entries(labels);
  if (entries.length === 0) {
    return <span className="text-sm text-stone-500">No labels</span>;
  }

  return (
    <div className="flex flex-wrap gap-2">
      {entries.map(([key, value]) => (
        <span
          key={key}
          className="inline-flex rounded-full border border-border bg-paper px-3 py-1 font-mono text-[11px] text-stone-700"
        >
          {key}:{String(value)}
        </span>
      ))}
    </div>
  );
}

export function StatCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <Panel className="space-y-6">
      <div className="space-y-2">
        <p className="font-mono text-xs uppercase tracking-[0.24em] text-stone-500">{label}</p>
        <p className="text-4xl font-semibold tracking-[-0.05em]">{value}</p>
      </div>
      <p className="text-sm text-stone-600">{detail}</p>
    </Panel>
  );
}

export function SectionTitle({
  title,
  description,
  linkTo,
  linkLabel,
}: {
  title: string;
  description?: string;
  linkTo?: string;
  linkLabel?: string;
}) {
  return (
    <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
      <div className="space-y-1">
        <h2 className="text-xl font-semibold tracking-[-0.03em]">{title}</h2>
        {description ? <p className="text-sm text-stone-600">{description}</p> : null}
      </div>
      {linkTo && linkLabel ? (
        <Link className="font-mono text-xs uppercase tracking-[0.24em] text-accent" to={linkTo}>
          {linkLabel}
        </Link>
      ) : null}
    </div>
  );
}

export function SearchInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <input
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="w-full rounded-full border border-border bg-paper px-4 py-3 text-sm outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/20"
      placeholder={placeholder}
    />
  );
}

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export function SelectInput({
  ariaLabel,
  className,
  disabled,
  onValueChange,
  options,
  placeholder = "Select",
  value,
}: {
  ariaLabel?: string;
  className?: string;
  disabled?: boolean;
  onValueChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  value: string;
}) {
  const id = useId();
  const rootRef = useRef<HTMLSpanElement | null>(null);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const [popoverStyle, setPopoverStyle] = useState<React.CSSProperties | null>(null);
  const selectedOption = useMemo(() => options.find((option) => option.value === value), [options, value]);

  useLayoutEffect(() => {
    if (!open) {
      return;
    }

    function updatePosition() {
      const rect = buttonRef.current?.getBoundingClientRect();
      if (!rect) {
        return;
      }
      const availableBelow = window.innerHeight - rect.bottom - 16;
      setPopoverStyle({
        left: rect.left,
        maxHeight: Math.max(160, Math.min(256, availableBelow)),
        top: rect.bottom + 8,
        width: rect.width,
      });
    }

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }

    function handlePointerDown(event: PointerEvent) {
      const target = event.target as Node;
      if (!rootRef.current?.contains(target) && !popoverRef.current?.contains(target)) {
        setOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <span className={clsx("relative block w-full", open ? "z-[90]" : "z-0", className)} ref={rootRef}>
      <button
        aria-controls={open ? id : undefined}
        aria-expanded={open}
        aria-label={ariaLabel}
        className="flex h-10 w-full items-center justify-between gap-2 rounded-full border border-border bg-paper px-4 text-left text-sm text-ink shadow-sm outline-none transition hover:border-accent/45 hover:bg-white focus:border-accent focus:bg-white focus:ring-2 focus:ring-accent/20 disabled:cursor-not-allowed disabled:opacity-50"
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
        ref={buttonRef}
        type="button"
      >
        <span className={clsx("min-w-0 truncate", selectedOption ? "text-ink" : "text-stone-500")}>
          {selectedOption?.label ?? placeholder}
        </span>
        <ChevronDown
          aria-hidden="true"
          className={clsx("h-4 w-4 shrink-0 text-stone-500 transition", open ? "rotate-180" : "")}
        />
      </button>
      {open && popoverStyle ? createPortal(
        <div
          className="fixed z-[9999] overflow-auto rounded-2xl border border-border bg-white p-1.5 shadow-2xl ring-1 ring-black/5"
          id={id}
          ref={popoverRef}
          role="listbox"
          style={popoverStyle}
        >
          {options.map((option) => {
            const selected = option.value === value;
            return (
              <button
                aria-selected={selected}
                className={clsx(
                  "flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left text-sm transition",
                  selected ? "bg-accent/10 text-ink" : "text-stone-700 hover:bg-mist",
                  option.disabled ? "cursor-not-allowed opacity-45" : "",
                )}
                disabled={option.disabled}
                key={option.value}
                onClick={() => {
                  onValueChange(option.value);
                  setOpen(false);
                }}
                role="option"
                type="button"
              >
                <span className="min-w-0 whitespace-normal break-words">{option.label}</span>
                {selected ? <Check aria-hidden="true" className="h-4 w-4 shrink-0 text-accent" /> : null}
              </button>
            );
          })}
        </div>,
        document.body,
      ) : null}
    </span>
  );
}

export function PaginationControls({
  total,
  limit,
  offset,
  onOffsetChange,
}: {
  total: number;
  limit: number;
  offset: number;
  onOffsetChange: (offset: number) => void;
}) {
  const start = total === 0 ? 0 : offset + 1;
  const end = Math.min(offset + limit, total);
  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-border bg-paper/70 px-4 py-3 text-sm text-stone-600 sm:flex-row sm:items-center sm:justify-between">
      <span>
        Showing {start}-{end} of {total}
      </span>
      <div className="flex gap-2">
        <SecondaryButton disabled={offset === 0} onClick={() => onOffsetChange(Math.max(0, offset - limit))} type="button">
          Previous
        </SecondaryButton>
        <SecondaryButton disabled={offset + limit >= total} onClick={() => onOffsetChange(offset + limit)} type="button">
          Next
        </SecondaryButton>
      </div>
    </div>
  );
}

export function PrimaryButton({
  children,
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={clsx(
        "inline-flex items-center justify-center rounded-full bg-ink px-5 py-3 text-sm font-semibold text-white transition hover:bg-stone-800 disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function SecondaryButton({
  children,
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={clsx(
        "inline-flex items-center justify-center rounded-full border border-border bg-paper px-5 py-3 text-sm font-semibold text-ink transition hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function GhostButton({
  children,
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={clsx(
        "inline-flex items-center justify-center rounded-full px-4 py-2 text-sm font-semibold text-stone-700 transition hover:bg-paper hover:text-ink disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
    >
      {children}
    </button>
  );
}
