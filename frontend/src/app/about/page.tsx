"use client";
import { PageHeader } from "@/components/Shell";
import { ErrorState, Loading, MetricsGrid, Panel } from "@/components/ui";
import { useApp } from "@/lib/store";
import { useTool } from "@/lib/useTool";

export default function About() {
  const { status } = useApp();
  const ov = useTool("get_dataset_overview");
  const dq = useTool("get_data_quality_report");
  return (
    <>
      <PageHeader title="About the dataset" sub="Provenance, licence and the exact definitions behind every number." />
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Provenance & attribution">
          <p className="text-sm text-zinc-300"><b>Online Retail II</b>, UCI Machine Learning Repository. Creator: Daqing Chen. A UK-based online retailer&apos;s transactions, Dec 2009 to Dec 2011.</p>
          <ul className="mt-3 space-y-1 text-sm text-zinc-400"><li>DOI: 10.24432/C5CG6D</li><li>Licence: Creative Commons Attribution 4.0 International (CC BY 4.0)</li>
            <li>Source: <a className="text-accent-soft underline" href="https://archive.ics.uci.edu/dataset/502/online+retail+ii" target="_blank" rel="noreferrer">archive.ics.uci.edu/dataset/502/online+retail+ii</a></li></ul>
          <p className="mt-3 text-xs text-zinc-600">The original workbook is not redistributed with this project; it is downloaded locally during setup.</p>
          {status && <p className="mt-3 text-xs text-zinc-600">{status.attribution}</p>}
        </Panel>
        <Panel title="Live dataset facts">{ov.error ? <ErrorState error={ov.error} /> : ov.loading ? <Loading /> : <MetricsGrid metrics={ov.data!.metrics} />}</Panel>
        <Panel title="Definitions & treatment" className="lg:col-span-2">
          <ul className="list-disc space-y-1.5 pl-5 text-sm text-zinc-400">
            <li><b className="text-zinc-300">Sale line</b>: not a cancellation, quantity &gt; 0, unit price &gt; 0, and a real product stock code. Revenue = quantity × unit price over sale lines.</li>
            <li><b className="text-zinc-300">Cancellation</b>: invoice number starts with &ldquo;C&rdquo;. Never counted as a sale. Cancellation rate = cancellation invoices ÷ (sale + cancellation invoices).</li>
            <li><b className="text-zinc-300">Excluded from revenue</b>: postage, fees, manual adjustments, samples and test codes; zero-price lines; non-cancellation negative quantities.</li>
            <li><b className="text-zinc-300">Dropped during cleaning</b>: unparseable dates/quantities/prices, exact duplicate rows, negative prices.</li>
            <li><b className="text-zinc-300">Customer identifiers</b> are removed at ingestion and unavailable to every tool.</li>
            <li><b className="text-zinc-300">Not answerable</b>: profit/margin (no costs), marketing ROI, staff productivity, stock levels, customer-level analysis. Historical data only; associations are not causes.</li>
          </ul>
          {dq.data && <div className="mt-4"><div className="panel-title mb-2">Cleaning counts for this dataset</div><MetricsGrid metrics={dq.data.metrics} /></div>}
        </Panel>
      </div>
    </>
  );
}
