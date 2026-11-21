"use client";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/Shell";
import { CsvLink, ErrorState, Kpi, Loading, MetricsGrid, Panel, SimpleTable } from "@/components/ui";
import { ApiError, getJson } from "@/lib/api";
import { fmtInt } from "@/lib/format";
import { useTool } from "@/lib/useTool";

interface Preview { page: number; page_size: number; total_rows: number; rows: Record<string, unknown>[]; note: string }

export default function DataExplorer() {
  const schema = useTool("get_dataset_schema");
  const quality = useTool("get_data_quality_report");
  const ov = useTool("get_dataset_overview");
  const [page, setPage] = useState(1);
  const [pv, setPv] = useState<Preview | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  useEffect(() => { setPv(null); getJson<Preview>(`/api/explorer/preview?page=${page}&page_size=25`).then(setPv).catch(setErr); }, [page]);
  const pages = pv ? Math.ceil(pv.total_rows / pv.page_size) : 0;
  const q = quality.data?.metrics;
  return (
    <>
      <PageHeader title="Data Explorer" sub="Schema, quality and a paginated preview of the cleaned data. Invoice numbers and customer identifiers are never exposed." />
      {ov.error ? <ErrorState error={ov.error} /> : (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Kpi name="Rows (cleaned)" value={fmtInt(ov.data?.metrics.total_records)} source="get_dataset_overview" />
          <Kpi name="First date" value={String(ov.data?.metrics.first_date ?? "n/a")} />
          <Kpi name="Last date" value={String(ov.data?.metrics.last_date ?? "n/a")} />
          <Kpi name="Columns" value={fmtInt(schema.data?.metrics.columns)} source="get_dataset_schema" />
        </div>
      )}
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Panel title="Schema & column descriptions" action={schema.data && <CsvLink tool="get_dataset_schema" table="schema" />}>
          {schema.loading ? <Loading /> : schema.error ? <ErrorState error={schema.error} /> : <SimpleTable rows={schema.data!.tables.schema} max={30} />}
          {schema.data?.notes.map((n, i) => <p key={i} className="mt-2 text-xs text-zinc-500">{n}</p>)}
        </Panel>
        <Panel title="Data quality & missing values">
          {quality.loading ? <Loading /> : quality.error ? <ErrorState error={quality.error} /> : (<><MetricsGrid metrics={quality.data!.metrics} />
            {q && <p className="mt-2 text-xs text-zinc-600">Missing descriptions: {fmtInt(q.missing_description)} lines. Missing customer ids are counted during ingestion ({fmtInt(q.missing_customer_id)}), then the column is dropped.</p>}
            {quality.data!.notes.map((n, i) => <p key={i} className="mt-1 text-xs text-zinc-600">{n}</p>)}</>)}
        </Panel>
      </div>
      <Panel title="Data preview" className="mt-4" action={pv && <span className="text-xs text-zinc-500">Page {pv.page} of {fmtInt(pages)}</span>}>
        {err ? <ErrorState error={err} /> : !pv ? <Loading /> : <><SimpleTable rows={pv.rows} max={25} />
          <div className="mt-3 flex items-center gap-2">
            <button className="btn" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</button>
            <button className="btn" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>Next</button>
            <span className="text-xs text-zinc-600">{pv.note}</span></div></>}
      </Panel>
    </>
  );
}
