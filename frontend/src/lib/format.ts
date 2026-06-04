export function formatCurrency(value: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatPercent(value: number | null | undefined) {
  if (value == null) {
    return "--";
  }
  return `${Math.round(value * 100)}%`;
}
