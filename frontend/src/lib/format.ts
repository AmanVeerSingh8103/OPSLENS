export const fmtInt = (v: unknown) => (typeof v === "number" ? Math.round(v).toLocaleString("en-GB") : "n/a");
export const fmtMoney = (v: unknown, compact = false) => {
  if (typeof v !== "number") return "n/a";
  return compact && Math.abs(v) >= 1000
    ? `£${new Intl.NumberFormat("en-GB", { notation: "compact", maximumFractionDigits: 2 }).format(v)}`
    : `£${v.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};
export const fmtPct = (v: unknown) => (typeof v === "number" ? `${v.toLocaleString("en-GB", { maximumFractionDigits: 2 })}%` : "n/a");

export const label = (k: string) => k.replace(/_/g, " ").replace(/\bpct\b/, "%").replace(/\bavg\b/, "average");

/** Format a metric from its key name. Unavailable values are shown as n/a, never invented. */
export function fmtMetric(key: string, v: string | number | null | undefined): string {
  if (v === null || v === undefined) return "n/a";
  if (typeof v === "string") return v;
  if (key.endsWith("_pct") || key.endsWith("pct_of_sales")) return fmtPct(v);
  if (/(revenue|value|sales|cost)/.test(key) && !/invoices?$|count|lines|units/.test(key)) return fmtMoney(v);
  if (Number.isInteger(v)) return fmtInt(v);
  return v.toLocaleString("en-GB", { maximumFractionDigits: 2 });
}
export const shortMonth = (m: string) => m; // YYYY-MM labels are already compact and unambiguous
