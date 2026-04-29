export function formatDateTime(value: string | null): string {
  if (!value) {
    return "Still running";
  }

  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function formatRelativeTime(value: string): string {
  const date = new Date(value);
  const diffMs = date.getTime() - Date.now();
  const minutes = Math.round(diffMs / 60000);

  if (Math.abs(minutes) < 60) {
    return new Intl.RelativeTimeFormat("en-US", { numeric: "auto" }).format(minutes, "minute");
  }

  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) {
    return new Intl.RelativeTimeFormat("en-US", { numeric: "auto" }).format(hours, "hour");
  }

  const days = Math.round(hours / 24);
  return new Intl.RelativeTimeFormat("en-US", { numeric: "auto" }).format(days, "day");
}
