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
};

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
      if (!j.skills) return;
      j.skills.split(",").forEach((s) => {
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
            <div className="job-meta">
              {j.location || "—"}
              {j.salary_min ? ` · $${Math.round(j.salary_min).toLocaleString()}+` : ""}
              {j.skills ? ` · ${j.skills.split(",").slice(0, 3).join(", ")}` : ""}
            </div>
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