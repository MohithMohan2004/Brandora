import { useState } from "react";

function Table({ rows, wideKey }) {
  if (!rows?.length) return <div className="empty">Nothing to show yet.</div>;
  const cols = Object.keys(rows[0]);
  return (
    <div className="table-wrap">
      <table>
        <thead><tr>{cols.map((c) => <th key={c}>{c.replace(/_/g, " ")}</th>)}</tr></thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {cols.map((c) => <td key={c} className={c === wideKey ? "wide" : ""}>{String(row[c])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Evidence({ retrieved, catalogue }) {
  const [tab, setTab] = useState(retrieved?.length ? "trace" : "products");

  const trace = (retrieved || []).map((item) => ({
    source_id: item.source_id,
    type: item.kind,
    similarity: item.score != null ? item.score.toFixed(3) : "mandatory rule",
    retrieved_content: item.text,
  }));

  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2>Evidence</h2>
          <p>
            Everything the model was allowed to use. Mandatory guidelines are always included, even when they are not
            among the closest semantic matches. Similarity scores are retrieval signals, not proof that a source is correct.
          </p>
        </div>
      </div>
      <div className="seg-tabs" role="tablist">
        {[["trace", "Retrieval trace"], ["products", "Product catalogue"], ["guidelines", "Company guidelines"]].map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? "on" : ""} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </div>
      {tab === "trace" && <Table rows={trace} wideKey="retrieved_content" />}
      {tab === "products" && <Table rows={catalogue?.products} />}
      {tab === "guidelines" && <Table rows={catalogue?.guidelines} />}
    </section>
  );
}
