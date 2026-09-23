import { useState, useEffect, useMemo } from "react";
import { socket, startSearch, API_BASE } from "./api";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
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

      {/* SEARCH FORM */}
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

      {/* WORKER / SOURCE STATUS PANEL */}
      {status !== "idle" && (
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
      {summary && (
        <section className={`summary ${summary.complete ? "complete" : "partial"}`}>
          <strong>{summary.complete ? "Complete" : "Partial (deadline reached)"}</strong>
          {" — "}{summary.total_results} jobs from {summary.completed_sources.length}/{expectedSources.length} sources
        </section>
      )}

      {/* CHARTS */}
      {jobs.length > 0 && (
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
    </div>
  );
}