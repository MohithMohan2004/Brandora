import { useMemo, useState } from "react";
import { api } from "../api.js";
import Icon from "../icons.jsx";
import { Segmented, relTime } from "../ui.jsx";
import Toolbar from "./Toolbar.jsx";
import Thumb from "./Thumb.jsx";
import { tier } from "./Relevance.jsx";

const STATUS = {
  approved: ["Approved", "t-ok"],
  rejected: ["Rejected", "t-bad"],
  review: ["In review", "t-none"],
  copy: ["Copy only", "t-none"],
};

const FILTERS = [
  { value: "all", label: "All" },
  { value: "approved", label: "Approved" },
  { value: "review", label: "In review" },
  { value: "copy", label: "Copy only" },
];

// "Today", "Yesterday", "This week", then month names.
function dayGroup(iso) {
  if (!iso) return "Earlier";
  const d = new Date(iso);
  const today = new Date();
  const start = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const days = Math.round((start(today) - start(d)) / 86400000);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return "This week";
  return d.toLocaleDateString(undefined, { month: "long", year: "numeric" });
}

export default function History({ items, loading, threshold, currentId, onOpen, onRemove, onNew }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState("recent");

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = items.filter((h) =>
      (filter === "all" || h.status === filter || (filter === "review" && h.status === "rejected"))
      && (!q || `${h.headline} ${h.prompt} ${h.product} ${h.copy}`.toLowerCase().includes(q)));
    if (sort === "score") list = [...list].sort((a, b) => (b.relevance ?? -1) - (a.relevance ?? -1));
    return list;
  }, [items, query, filter, sort]);

  const groups = useMemo(() => {
    if (sort !== "recent") return [["", shown]];
    const out = [];
    shown.forEach((h) => {
      const g = dayGroup(h.updated_at);
      if (!out.length || out[out.length - 1][0] !== g) out.push([g, []]);
      out[out.length - 1][1].push(h);
    });
    return out;
  }, [shown, sort]);

  return (
    <>
      <Toolbar title="History" subtitle={loading ? "Loading…" : `${items.length} ${items.length === 1 ? "ad" : "ads"}`}>
        <label className="search-field">
          <Icon name="search" size={15} />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search ads" aria-label="Search ads" />
          {query && <button className="icon-btn xs" onClick={() => setQuery("")} aria-label="Clear search"><Icon name="x" size={12} /></button>}
        </label>
      </Toolbar>

      <div className="page history-page">
        <div className="history-bar">
          <Segmented label="Filter" options={FILTERS} value={filter} onChange={setFilter} size="sm" />
          <Segmented label="Sort" size="sm" value={sort} onChange={setSort} options={[
            { value: "recent", label: "Newest", icon: "clock" },
            { value: "score", label: "Relevance", icon: "sparkle" },
          ]} />
        </div>

        {!items.length && !loading && (
          <div className="empty-state">
            <span className="empty-icon"><Icon name="clock" size={28} /></span>
            <h2>No ads yet</h2>
            <p>Every ad you generate is kept here, with its poster, relevance score and review decision.</p>
            <button className="btn primary lg" onClick={onNew}><Icon name="plus" size={16} /> New ad</button>
          </div>
        )}
        {items.length > 0 && !shown.length && <div className="empty-inline">No ads match these filters.</div>}

        {groups.map(([label, list]) => (
          <section key={label || "all"} className="history-group" aria-label={label || "Ads"}>
            {label && <h2 className="history-day">{label}</h2>}
            <ul className="history-grid">
              {list.map((h) => {
                const [statusLabel, statusTone] = STATUS[h.status] || STATUS.review;
                return (
                  <li key={h.id} className={`ad-tile ${currentId === h.id ? "on" : ""}`}>
                    <button className="ad-tile-open" onClick={() => onOpen(h)} aria-label={`Open ${h.headline || "ad"}`}>
                      <span className="ad-thumb">
                        {h.thumb ? (
                          <Thumb src={api.thumbUrl(h.id, h.thumb)} />
                        ) : (
                          <span className="ad-thumb-copy">
                            <b>{h.headline || "Untitled ad"}</b>
                            <span>{h.copy}</span>
                          </span>
                        )}
                        {h.relevance != null && (
                          <span className={`ad-score t-${tier(h.relevance, threshold)}`} title={`Relevance ${h.relevance}`}>{h.relevance}</span>
                        )}
                      </span>
                      <span className="ad-tile-body">
                        <span className="ad-tile-title">{h.headline || "Untitled ad"}</span>
                        <span className="ad-tile-meta">
                          <span className="truncate">{(h.product || "").replace(/\s*\(.*\)$/, "") || "No product"}</span>
                          <span aria-hidden="true">·</span>
                          <span className="nowrap">{relTime(h.updated_at)}</span>
                        </span>
                        <span className={`status-chip ${statusTone}`}>{statusLabel}</span>
                      </span>
                    </button>
                    <button className="icon-btn sm ad-tile-delete" onClick={() => onRemove(h)}
                      aria-label={`Delete ${h.headline || "ad"}`} title="Delete">
                      <Icon name="trash" size={15} />
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>
    </>
  );
}
