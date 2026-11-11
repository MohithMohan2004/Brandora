import { useMemo, useState } from "react";
import Icon from "../icons.jsx";
import { Segmented } from "../ui.jsx";
import Toolbar from "./Toolbar.jsx";

const matches = (row, q) => !q || Object.values(row).some((v) => String(v).toLowerCase().includes(q));

function Table({ rows, q }) {
  const shown = useMemo(() => (rows || []).filter((r) => matches(r, q)), [rows, q]);
  if (!rows?.length) return <div className="empty-inline">Loading…</div>;
  if (!shown.length) return <div className="empty-inline">Nothing matches “{q}”.</div>;
  const cols = Object.keys(rows[0]);
  return (
    <div className="table-wrap">
      <table>
        <thead><tr>{cols.map((c) => <th key={c}>{c.replace(/_/g, " ")}</th>)}</tr></thead>
        <tbody>
          {shown.map((row, i) => (
            <tr key={i}>
              {cols.map((c) => <td key={c} className={/_id$/.test(c) ? "mono nowrap" : ""}><div className="cell">{String(row[c])}</div></td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// "key: value | key: value" record text, shown as a readable list.
const fields = (text) => text.split(" | ").map((p) => p.split(": ")).filter((p) => p.length > 1 && p[0] !== "record_type");

function Trace({ retrieved, q }) {
  const shown = retrieved.filter((r) => matches(r, q));
  if (!shown.length) return <div className="empty-inline">Nothing matches “{q}”.</div>;
  return (
    <ol className="trace">
      {shown.map((item) => (
        <li key={item.source_id} className="trace-item">
          <div className="trace-head">
            <span className={`tag ${item.kind}`}>{item.kind}</span>
            <code>{item.source_id.split(":")[1]}</code>
            {item.score != null ? (
              <span className="trace-score" title="Cosine similarity to the brief: a retrieval signal, not proof">
                <span className="meter"><span style={{ width: `${Math.max(0, item.score) * 100}%` }} /></span>
                {item.score.toFixed(3)}
              </span>
            ) : <span className="tag rule">always included</span>}
          </div>
          <dl className="trace-fields">
            {fields(item.text).map(([k, ...v]) => (
              <div key={k}><dt>{k.replace(/_/g, " ")}</dt><dd>{v.join(": ")}</dd></div>
            ))}
          </dl>
        </li>
      ))}
    </ol>
  );
}

export default function Evidence({ retrieved, catalogue }) {
  const [tab, setTab] = useState(retrieved?.length ? "trace" : "products");
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();

  const options = [
    ...(retrieved?.length ? [{ value: "trace", label: `Retrieved ${retrieved.length}` }] : []),
    { value: "products", label: `Products ${catalogue?.products?.length ?? ""}`.trim() },
    { value: "guidelines", label: `Guidelines ${catalogue?.guidelines?.length ?? ""}`.trim() },
  ];

  return (
    <>
      <Toolbar title="Evidence" subtitle={retrieved?.length ? "What this ad was allowed to use" : "Catalogue and brand guidelines"}>
        <label className="search-field">
          <Icon name="search" size={15} />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter" aria-label="Filter records" />
          {query && <button className="icon-btn xs" onClick={() => setQuery("")} aria-label="Clear filter"><Icon name="x" size={12} /></button>}
        </label>
      </Toolbar>
      <div className="page evidence-page">
        <div className="evidence-bar">
          <Segmented label="Records" options={options} value={tab} onChange={setTab} />
          <p className="muted small">
            {tab === "trace"
              ? "Mandatory guidelines are always included, even when they are not the closest matches."
              : "Synthetic demo data. Edit the CSV files in backend/data to change it."}
          </p>
        </div>
        {tab === "trace" && retrieved && <Trace retrieved={retrieved} q={q} />}
        {tab === "products" && <Table rows={catalogue?.products} q={q} />}
        {tab === "guidelines" && <Table rows={catalogue?.guidelines} q={q} />}
      </div>
    </>
  );
}
