import clsx from "clsx";

export { clsx };

export function formatNumber(value: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 }).format(value);
}

export function formatCount(value: number): string {
  return new Intl.NumberFormat("en-US", { notation: value > 999 ? "compact" : "standard" }).format(value);
}
