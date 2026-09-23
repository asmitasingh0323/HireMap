import { useState, useEffect, useMemo } from "react";
import { socket, startSearch, fetchMarket, API_BASE } from "./api";
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, Legend,
  ResponsiveContainer, Cell, CartesianGrid,
} from "recharts";
import "./App.css";

const SOURCE_COLORS = {
  adzuna: "#4f8cff",
  remoteok: "#22c55e",
  weworkremotely: "#f59e0b",
  remotive: "#a855f7",
  arbeitnow: "#ef4444",
  greenhouse: "#0ea5e9",
};

// The API only returns listings that are still live, so a card can honestly
// say "still active". We prefer the source's own posting date and fall back
// to when this crawler first saw the listing.
function freshnessLabel(job) {
  const posted = job.posted_date || job.first_seen;
  if (!posted) return "still active";
  const days = Math.floor((Date.now() - new Date(posted).getTime()) / 86400000);
  if (isNaN(days) || days < 0) return "still active";
  const word = job.posted_date ? "posted" : "seen";
  if (days === 0) return `${word} today \u00b7 still active`;
  if (days === 1) return `${word} 1 day ago \u00b7 still active`;
  return `${word} ${days} days ago \u00b7 still active`;
}

// Small helpers for the decoded job card
const SENIORITY_COLORS = {
  intern: "#64748b", junior: "#0ea5e9", mid: "#8b5cf6",
  senior: "#f59e0b", lead: "#ef4444", unknown: "#94a3b8",
};

function money(value) {
  if (!value) return null;
  return `$${Math.round(value / 1000)}k`;
}

// "$153k - $376k (estimated)" or null when nothing is known
function salaryLine(job) {
  const low = money(job.salary_min_ai) || money(job.salary_min);
  const high = money(job.salary_max_ai) || money(job.salary_max);
  if (!low && !high) return null;
  const range = low && high ? `${low} - ${high}` : (low || high);
  return range + (job.salary_basis === "estimated" ? " (estimated)" : "");
}

function splitSkills(text) {
  if (!text) return [];
  return text.split(",").map((s) => s.trim()).filter(Boolean);
}

// One hue per chart: each chart shows a single series, so identity never
// depends on telling two colors apart. The paid-range chart is the one
// exception and uses two clearly different hues plus a legend.
const INK = "#334155";
const MUTED = "#64748b";
const PRIMARY = "#4f46e5";
const ACCENT = "#f59e0b";

function StatTile({ label, value, hint }) {
  return (
    <div style={{
      background: "#fff", borderRadius: 10, padding: "14px 18px",
      minWidth: 150, boxShadow: "0 1px 3px rgba(15,23,42,0.08)",
    }}>
      <div style={{ fontSize: "1.7rem", fontWeight: 600, color: INK }}>
        {value}
      </div>
      <div style={{ fontSize: "0.8rem", color: MUTED }}>{label}</div>
      {hint && (
        <div style={{ fontSize: "0.72rem", color: MUTED, marginTop: 2 }}>
          {hint}
        </div>
      )}
    </div>
  );
}

function ChartCard({ title, subtitle, children }) {
  return (
    <div className="chart-card" style={{ flex: "1 1 340px", minWidth: 300 }}>
      <h3 style={{ marginBottom: 2 }}>{title}</h3>
      {subtitle && (
        <div style={{ fontSize: "0.75rem", color: MUTED, marginBottom: 6 }}>
          {subtitle}
        </div>
      )}
      {children}
    </div>
  );
}

function MarketView({ market, loading, error, onReload }) {
  if (loading) return <p className="empty">Loading market summary…</p>;
  if (error) {
    return (
      <p className="empty">
        {error} <button onClick={onReload}>Try again</button>
      </p>
    );
  }
  if (!market || market.total_jobs === 0) {
    return <p className="empty">No jobs collected yet.</p>;
  }

  const remote = (market.arrangement || [])
    .find((a) => a.name === "remote");
  const remoteShare = remote
    ? Math.round((100 * remote.jobs) / market.total_jobs) + "%" : "—";

  return (
    <section style={{ padding: "0 4px" }}>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap",
                    marginBottom: 16 }}>
        <StatTile label="live listings" value={market.total_jobs} />
        <StatTile label="read by the model" value={market.interpreted_jobs}
                  hint={`of ${market.total_jobs} live listings`} />
        <StatTile label="remote" value={remoteShare}
                  hint="of roles where the model could tell" />
        <StatTile label="sources" value={(market.sources || []).length} />
      </div>

      <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
        {market.top_skills.length > 0 && (
          <ChartCard title="Most requested skills"
                     subtitle="how many live listings ask for each">
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={market.top_skills} layout="vertical"
                        margin={{ left: 8, right: 24 }}>
                <XAxis type="number" allowDecimals={false}
                       tick={{ fill: MUTED, fontSize: 12 }} />
                <YAxis type="category" dataKey="skill" width={110}
                       tick={{ fill: INK, fontSize: 12 }} />
                <Tooltip cursor={{ fill: "rgba(79,70,229,0.06)" }} />
                <Bar dataKey="jobs" fill={PRIMARY} radius={[0, 4, 4, 0]}
                     barSize={14} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        )}

        {market.hiring_activity.length > 0 && (
          <ChartCard title="Hiring activity"
                     subtitle="new listings first seen each day">
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={market.hiring_activity}
                         margin={{ left: 4, right: 16, top: 8 }}>
                <CartesianGrid stroke="#e2e8f0" vertical={false} />
                <XAxis dataKey="day" tick={{ fill: MUTED, fontSize: 11 }} />
                <YAxis allowDecimals={false}
                       tick={{ fill: MUTED, fontSize: 12 }} />
                <Tooltip />
                <Line type="monotone" dataKey="jobs" stroke={PRIMARY}
                      strokeWidth={2} dot={{ r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          </ChartCard>
        )}

        {market.seniority.length > 0 && (
          <ChartCard title="Seniority mix"
                     subtitle="live listings by level the model read">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={market.seniority}>
                <XAxis dataKey="name" tick={{ fill: INK, fontSize: 12 }} />
                <YAxis allowDecimals={false}
                       tick={{ fill: MUTED, fontSize: 12 }} />
                <Tooltip cursor={{ fill: "rgba(79,70,229,0.06)" }} />
                <Bar dataKey="jobs" fill={PRIMARY} radius={[4, 4, 0, 0]}
                     barSize={34} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        )}

        {market.arrangement.length > 0 && (
          <ChartCard title="Where the work happens"
                     subtitle="remote, hybrid or onsite">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={market.arrangement}>
                <XAxis dataKey="name" tick={{ fill: INK, fontSize: 12 }} />
                <YAxis allowDecimals={false}
                       tick={{ fill: MUTED, fontSize: 12 }} />
                <Tooltip cursor={{ fill: "rgba(79,70,229,0.06)" }} />
                <Bar dataKey="jobs" fill={PRIMARY} radius={[4, 4, 0, 0]}
                     barSize={34} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        )}

        {market.salary_by_seniority.length > 0 && (
          <ChartCard title="Pay by level"
                     subtitle="average of the ranges found, in dollars a year">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={market.salary_by_seniority}>
                <XAxis dataKey="name" tick={{ fill: INK, fontSize: 12 }} />
                <YAxis tick={{ fill: MUTED, fontSize: 12 }}
                       tickFormatter={(v) => `$${Math.round(v / 1000)}k`} />
                <Tooltip formatter={(v) => `$${Number(v).toLocaleString()}`} />
                <Legend />
                <Bar dataKey="low" name="range low" fill={PRIMARY}
                     radius={[4, 4, 0, 0]} barSize={18} />
                <Bar dataKey="high" name="range high" fill={ACCENT}
                     radius={[4, 4, 0, 0]} barSize={18} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        )}

        {market.top_companies.length > 0 && (
          <ChartCard title="Companies hiring most"
                     subtitle="live listings per company">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={market.top_companies} layout="vertical"
                        margin={{ left: 8, right: 24 }}>
                <XAxis type="number" allowDecimals={false}
                       tick={{ fill: MUTED, fontSize: 12 }} />
                <YAxis type="category" dataKey="name" width={120}
                       tick={{ fill: INK, fontSize: 12 }} />
                <Tooltip cursor={{ fill: "rgba(79,70,229,0.06)" }} />
                <Bar dataKey="jobs" fill={PRIMARY} radius={[0, 4, 4, 0]}
                     barSize={14} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        )}
      </div>
    </section>
  );
}

export default function App() {
  const [keyword, setKeyword] = useState("python developer");
  const [location, setLocation] = useState("Seattle");
  const [deadline, setDeadline] = useState(10);

  const [searchId, setSearchId] = useState(null);
  const [status, setStatus] = useState("idle"); // idle | running | done
  const [expectedSources, setExpectedSources] = useState([]);
  const [doneSources, setDoneSources] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [summary, setSummary] = useState(null);
  const [connected, setConnected] = useState(false);

  // Market view (weeks 13-14)
  const [view, setView] = useState("search");     // "search" | "market"
  const [market, setMarket] = useState(null);
  const [marketLoading, setMarketLoading] = useState(false);
  const [marketError, setMarketError] = useState(null);

  const loadMarket = async () => {
    setMarketLoading(true);
    setMarketError(null);
    try {
      setMarket(await fetchMarket());
    } catch (e) {
      setMarketError("Could not load the market summary.");
    } finally {
      setMarketLoading(false);
    }
  };

  // Load it the first time the market tab is opened, then on demand
  useEffect(() => {
    if (view === "market" && !market && !marketLoading) loadMarket();
  }, [view]);

  // Wire up socket listeners once
  useEffect(() => {
    socket.on("connect", () => setConnected(true));
    socket.on("disconnect", () => setConnected(false));

    socket.on("search_started", (data) => {
      setSearchId(data.search_id);
      setExpectedSources(data.sources || []);
      setDoneSources([]);
      setJobs([]);
      setSummary(null);
      setStatus("running");
    });

    socket.on("source_done", (data) => {
      setDoneSources((prev) => [...new Set([...prev, data.source])]);
      setJobs((prev) => [...prev, ...(data.jobs || [])]);
    });

    socket.on("search_complete", (data) => {
      setSummary(data);
      setStatus("done");
    });

    return () => {
      socket.off("connect");
      socket.off("disconnect");
      socket.off("search_started");
      socket.off("source_done");
      socket.off("search_complete");
    };
  }, []);

  const handleSearch = async () => {
    if (!keyword.trim()) return;
    setStatus("running");
    await startSearch(keyword, location, deadline);
  };

  // Build skill-frequency data from job tags/skills
  const skillData = useMemo(() => {
    const counts = {};
    jobs.forEach((j) => {
      // Prefer the model's required skills; fall back to the source's tags
      const source = j.extracted_skills || j.skills;
      if (!source) return;
      source.split(",").forEach((s) => {
        const skill = s.trim().toLowerCase();
        if (skill) counts[skill] = (counts[skill] || 0) + 1;
      });
    });
    return Object.entries(counts)
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 8);
  }, [jobs]);

  // Source breakdown for the chart
  const sourceData = useMemo(() => {
    const counts = {};
    jobs.forEach((j) => {
      counts[j.source] = (counts[j.source] || 0) + 1;
    });
    return Object.entries(counts).map(([name, count]) => ({ name, count }));
  }, [jobs]);

  return (
    <div className="app">
      <header className="header">
        <h1>HireMap</h1>
        <p className="tagline">Distributed Real-Time Job Market Intelligence</p>
        <span className={`conn ${connected ? "on" : "off"}`}>
          {connected ? "● live" : "○ disconnected"}
        </span>
      </header>

      {/* VIEW SWITCH */}
      <div style={{ display: "flex", gap: 8, margin: "4px 0 12px" }}>
        {[["search", "Search"], ["market", "Market"]].map(([key, label]) => (
          <button key={key} onClick={() => setView(key)}
            style={{
              padding: "6px 16px", borderRadius: 8, cursor: "pointer",
              border: view === key ? "none" : "1px solid #cbd5e1",
              background: view === key ? PRIMARY : "#fff",
              color: view === key ? "#fff" : INK,
            }}>{label}</button>
        ))}
        {view === "market" && (
          <button onClick={loadMarket}
            style={{ padding: "6px 14px", borderRadius: 8, cursor: "pointer",
                     border: "1px solid #cbd5e1", background: "#fff",
                     color: MUTED }}>Refresh</button>
        )}
      </div>

      {view === "market" && (
        <MarketView market={market} loading={marketLoading}
                    error={marketError} onReload={loadMarket} />
      )}

      {/* SEARCH FORM */}
      {view === "search" && (
      <section className="search-bar">
        <input
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="Keyword (e.g. python developer)"
        />
        <input
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          placeholder="Location (e.g. Seattle)"
        />
        <div className="deadline">
          <label>Deadline: {deadline}s</label>
          <input
            type="range" min="1" max="20" value={deadline}
            onChange={(e) => setDeadline(Number(e.target.value))}
          />
        </div>
        <button onClick={handleSearch} disabled={status === "running"}>
          {status === "running" ? "Searching…" : "Search"}
        </button>
      </section>
      )}

      {/* WORKER / SOURCE STATUS PANEL */}
      {view === "search" && status !== "idle" && (
        <section className="sources-panel">
          {expectedSources.map((src) => {
            const isDone = doneSources.includes(src);
            return (
              <div key={src} className={`source-chip ${isDone ? "done" : "pending"}`}>
                <span className="dot" style={{ background: SOURCE_COLORS[src] || "#888" }} />
                {src}
                <span className="state">{isDone ? "✓ done" : "… working"}</span>
              </div>
            );
          })}
        </section>
      )}

      {/* SUMMARY */}
      {view === "search" && summary && (
        <section className={`summary ${summary.complete ? "complete" : "partial"}`}>
          <strong>{summary.complete ? "Complete" : "Partial (deadline reached)"}</strong>
          {" — "}{summary.total_results} jobs from {summary.completed_sources.length}/{expectedSources.length} sources
        </section>
      )}

      {/* CHARTS */}
      {view === "search" && jobs.length > 0 && (
        <section className="charts">
          <div className="chart-card">
            <h3>Jobs by Source</h3>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={sourceData}>
                <XAxis dataKey="name" /><YAxis allowDecimals={false} /><Tooltip />
                <Bar dataKey="count">
                  {sourceData.map((entry, i) => (
                    <Cell key={i} fill={SOURCE_COLORS[entry.name] || "#4f8cff"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          {skillData.length > 0 && (
            <div className="chart-card">
              <h3>Top Skills</h3>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={skillData} layout="vertical">
                  <XAxis type="number" allowDecimals={false} />
                  <YAxis type="category" dataKey="name" width={90} />
                  <Tooltip /><Bar dataKey="count" fill="#22c55e" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </section>
      )}

      {/* RESULTS */}
      {view === "search" && (
      <section className="results">
        {jobs.map((j, i) => (
          <div key={i} className="job-card">
            <div className="job-top">
              <span className="job-num">#{i + 1}</span>
              <span className="job-title">{j.title}</span>
              <span className="job-source" style={{ background: SOURCE_COLORS[j.source] || "#888" }}>
                {j.source}
              </span>
            </div>
            <div className="job-company">{j.company || "Unknown company"}</div>
            <div className="job-fresh" style={{
              fontSize: "0.8rem", color: "#15803d", margin: "2px 0",
            }}>
              ● {freshnessLabel(j)}
            </div>
            <div className="job-meta">
              {j.location || "—"}
              {salaryLine(j) ? ` · ${salaryLine(j)}` : ""}
            </div>

            {/* What the model pulled out of the description */}
            {(j.seniority || j.work_arrangement || j.extracted_skills) && (
              <div className="job-decoded" style={{ marginTop: 6 }}>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap",
                              marginBottom: 4 }}>
                  {j.seniority && j.seniority !== "unknown" && (
                    <span style={{
                      fontSize: "0.72rem", padding: "2px 8px", borderRadius: 10,
                      color: "#fff", textTransform: "capitalize",
                      background: SENIORITY_COLORS[j.seniority] || "#94a3b8",
                    }}>{j.seniority}</span>
                  )}
                  {j.work_arrangement && j.work_arrangement !== "unknown" && (
                    <span style={{
                      fontSize: "0.72rem", padding: "2px 8px", borderRadius: 10,
                      border: "1px solid #cbd5e1", color: "#475569",
                      textTransform: "capitalize",
                    }}>{j.work_arrangement}</span>
                  )}
                </div>

                {splitSkills(j.extracted_skills).length > 0 && (
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap",
                                alignItems: "center", marginBottom: 3 }}>
                    <span style={{ fontSize: "0.72rem", color: "#64748b" }}>
                      needs
                    </span>
                    {splitSkills(j.extracted_skills).map((skill) => (
                      <span key={skill} style={{
                        fontSize: "0.72rem", padding: "1px 7px", borderRadius: 4,
                        background: "#e0e7ff", color: "#3730a3",
                      }}>{skill}</span>
                    ))}
                  </div>
                )}

                {splitSkills(j.preferred_skills).length > 0 && (
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap",
                                alignItems: "center" }}>
                    <span style={{ fontSize: "0.72rem", color: "#64748b" }}>
                      nice to have
                    </span>
                    {splitSkills(j.preferred_skills).map((skill) => (
                      <span key={skill} style={{
                        fontSize: "0.72rem", padding: "1px 7px", borderRadius: 4,
                        background: "#f1f5f9", color: "#475569",
                      }}>{skill}</span>
                    ))}
                  </div>
                )}
              </div>
            )}
            <div className="job-actions">
              {j.url ? (
                <a className="apply-btn" href={j.url} target="_blank" rel="noopener noreferrer">
                  Apply →
                </a>
              ) : (
                <span className="apply-btn disabled">No link</span>
              )}
            </div>
          </div>
        ))}
        {status === "running" && jobs.length === 0 && (
          <p className="empty">Workers fetching… results will stream in live.</p>
        )}
      </section>
      )}
    </div>
  );
}