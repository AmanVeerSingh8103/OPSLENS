"use client";
import { BarsChart, CancellationChart, TrendChart } from "@/components/Charts";
import { PageHeader } from "@/components/Shell";
import { CsvLink, ErrorState, Kpi, Loading, Panel } from "@/components/ui";
import { fmtInt, fmtMoney } from "@/lib/format";
import { useTool } from "@/lib/useTool";

export default function Overview() {
  const ov = useTool("get_dataset_overview");
  const trend = useTool("get_revenue_trend");
  const ctry = useTool("get_country_performance", { top_n: 10 });
  const prod = useTool("get_product_performance", { top_n: 10 });
  const canc = useTool("get_cancellation_analysis", { top_n: 5 });
  const m = ov.data?.metrics;
  return (
    <>
      <PageHeader title="Overview" sub="Every figure on this page is calculated by the backend from the loaded dataset. Hover a KPI to see which tool produced it." />
      {ov.error ? <ErrorState error={ov.error} /> : ov.loading || !m ? <Loading /> : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4" data-testid="kpis">
            <Kpi name="Transaction records" value={fmtInt(m.total_records)} source="get_dataset_overview" />
            <Kpi name="Completed invoices" value={fmtInt(m.completed_invoices)} source="get_dataset_overview" />
            <Kpi name="Cancellation invoices" value={fmtInt(m.cancellation_invoices)} source="get_dataset_overview" />
            <Kpi name="Sales revenue" value={fmtMoney(m.sales_revenue, true)} sub={fmtMoney(m.sales_revenue)} source="get_dataset_overview" />
            <Kpi name="Unique products" value={fmtInt(m.unique_products)} source="get_dataset_overview" />
            <Kpi name="Countries" value={fmtInt(m.countries)} source="get_dataset_overview" />
            <Kpi name="Avg invoice value" value={fmtMoney(m.average_invoice_value)} source="get_dataset_overview" />
            <Kpi name="Date range" value={`${m.first_date} → ${m.last_date}`} source="get_dataset_overview" />
          </div>
          <p className="mt-2 text-xs text-zinc-600">Revenue = quantity × unit price on completed sale lines (cancellations, postage/fees and adjustments excluded). Revenue is not profit.</p>
          <div className="mt-5 grid gap-4 lg:grid-cols-2">
            <Panel title="Monthly revenue trend" action={trend.data && <CsvLink tool="get_revenue_trend" table="monthly" />}>
              {trend.error ? <ErrorState error={trend.error} /> : trend.data ? <TrendChart rows={trend.data.tables.monthly} /> : <Loading />}
              {trend.data?.notes.map((n, i) => <p key={i} className="mt-1 text-xs text-zinc-600">{n}</p>)}
            </Panel>
            <Panel title="Transaction activity (invoices per month)">
              {trend.error ? <ErrorState error={trend.error} /> : trend.data ? <BarsChart rows={trend.data.tables.monthly} x="year_month" y="invoices" fmt={fmtInt} color="#4f8cff" /> : <Loading />}
            </Panel>
            <Panel title="Sales by country (top 10)" action={ctry.data && <CsvLink tool="get_country_performance" table="countries" />}>
              {ctry.error ? <ErrorState error={ctry.error} /> : ctry.data ? <BarsChart rows={ctry.data.tables.countries} x="country" y="revenue" horizontal h={300} /> : <Loading />}
            </Panel>
            <Panel title="Top-performing products by revenue" action={prod.data && <CsvLink tool="get_product_performance" table="top_products" />}>
              {prod.error ? <ErrorState error={prod.error} /> : prod.data ? <BarsChart rows={prod.data.tables.top_products} x="stock_code" y="revenue" h={300} /> : <Loading />}
            </Panel>
            <Panel title="Cancellation trend (invoices and rate)" className="lg:col-span-2" action={canc.data && <CsvLink tool="get_cancellation_analysis" table="monthly" />}>
              {canc.error ? <ErrorState error={canc.error} /> : canc.data ? <CancellationChart rows={canc.data.tables.monthly} /> : <Loading />}
              {canc.data?.notes.map((n, i) => <p key={i} className="mt-1 text-xs text-zinc-600">{n}</p>)}
            </Panel>
          </div>
        </>
      )}
    </>
  );
}
