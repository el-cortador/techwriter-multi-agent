import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { authFetch, getApiKey, setApiKey, UnauthorizedError } from "./auth";

type Overview = {
  project_slug: string;
  totals: {
    total_runs: number;
    success_runs: number;
    error_runs: number;
    avg_duration_ms: number;
    total_tokens: number;
    total_cost_usd: number;
    avg_tokens_per_run: number;
  };
  top_routes: Array<{ route_kind: string; runs: number }>;
  model_usage: Array<{ model_name: string; runs: number; total_tokens: number }>;
};

type ActivityItem = {
  day: string;
  runs: number;
  total_tokens: number;
  total_cost_usd: number;
};

type SessionItem = {
  id: number;
  source: string;
  external_session_id: string;
  user_id: string | null;
  channel_id: string | null;
  runs: number;
  total_tokens: number;
  total_cost_usd: number;
  last_activity_at: string;
};

type RunItem = {
  id: number;
  session_id: number;
  route_kind: string;
  status: string;
  model_name: string;
  started_at: string;
  duration_ms: number | null;
  total_tokens: number;
  total_cost_usd: number;
  user_id: string | null;
  channel_id: string | null;
  error_message: string | null;
};

type ErrorItem = {
  id: number;
  session_id: number;
  route_kind: string;
  model_name: string;
  started_at: string;
  error_message: string | null;
};

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

export function App() {
  const [apiKey, setCurrentApiKey] = useState(getApiKey());
  const [unauthorized, setUnauthorized] = useState(false);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [runs, setRuns] = useState<RunItem[]>([]);
  const [errors, setErrors] = useState<ErrorItem[]>([]);

  useEffect(() => {
    if (!apiKey) {
      return;
    }
    void Promise.all([
      fetchJson<Overview>(`${API_BASE}/overview`).then(setOverview),
      fetchJson<{ items: ActivityItem[] }>(`${API_BASE}/activity`).then((data) => setActivity(data.items.reverse())),
      fetchJson<{ items: SessionItem[] }>(`${API_BASE}/sessions?limit=20`).then((data) => setSessions(data.items)),
      fetchJson<{ items: RunItem[] }>(`${API_BASE}/runs?limit=20`).then((data) => setRuns(data.items)),
      fetchJson<{ items: ErrorItem[] }>(`${API_BASE}/errors?limit=10`).then((data) => setErrors(data.items))
    ]).catch((error) => {
      if (error instanceof UnauthorizedError) {
        setUnauthorized(true);
      } else {
        throw error;
      }
    });
  }, [apiKey]);

  if (!apiKey || unauthorized) {
    return (
      <ApiKeyForm
        showError={unauthorized}
        onSubmit={(key) => {
          setApiKey(key);
          setUnauthorized(false);
          setCurrentApiKey(key);
        }}
      />
    );
  }

  return (
    <div className="page">
      <header className="hero">
        <div>
          <p className="eyebrow">Project Dashboard</p>
          <h1>{overview?.project_slug ?? "Loading..."}</h1>
          <p className="subtle">Operational view over Discord sessions, runs, tokens, costs, and failures.</p>
        </div>
      </header>

      <section className="cards">
        <StatCard label="Total Runs" value={overview?.totals.total_runs ?? 0} />
        <StatCard label="Success Rate" value={formatPercent(overview)} />
        <StatCard label="Total Tokens" value={formatInt(overview?.totals.total_tokens ?? 0)} />
        <StatCard label="Total Cost" value={`$${(overview?.totals.total_cost_usd ?? 0).toFixed(4)}`} />
        <StatCard label="Avg Duration" value={`${Math.round(overview?.totals.avg_duration_ms ?? 0)} ms`} />
        <StatCard label="Avg Tokens / Run" value={formatInt(Math.round(overview?.totals.avg_tokens_per_run ?? 0))} />
      </section>

      <section className="grid">
        <Panel title="Activity">
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={activity}>
                <defs>
                  <linearGradient id="tokensFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#004e64" stopOpacity={0.9} />
                    <stop offset="95%" stopColor="#9fffcb" stopOpacity={0.12} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#d9e4dd" />
                <XAxis dataKey="day" />
                <YAxis />
                <Tooltip />
                <Area type="monotone" dataKey="total_tokens" stroke="#004e64" fill="url(#tokensFill)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title="Top Routes">
          <table className="table">
            <thead>
              <tr>
                <th>Route</th>
                <th>Runs</th>
              </tr>
            </thead>
            <tbody>
              {(overview?.top_routes ?? []).map((item) => (
                <tr key={item.route_kind}>
                  <td>{item.route_kind}</td>
                  <td>{item.runs}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </section>

      <section className="grid">
        <Panel title="Sessions">
          <Table
            headers={["ID", "User", "Channel", "Runs", "Tokens", "Last Activity"]}
            rows={sessions.map((item) => [
              String(item.id),
              item.user_id ?? "—",
              item.channel_id ?? "—",
              String(item.runs),
              formatInt(item.total_tokens),
              formatDate(item.last_activity_at)
            ])}
          />
        </Panel>

        <Panel title="Recent Runs">
          <Table
            headers={["Run", "Route", "Status", "Tokens", "Duration", "Started"]}
            rows={runs.map((item) => [
              String(item.id),
              item.route_kind,
              item.status,
              formatInt(item.total_tokens),
              item.duration_ms ? `${item.duration_ms} ms` : "—",
              formatDate(item.started_at)
            ])}
          />
        </Panel>
      </section>

      <section className="grid">
        <Panel title="Models">
          <Table
            headers={["Model", "Runs", "Tokens"]}
            rows={(overview?.model_usage ?? []).map((item) => [
              item.model_name || "—",
              String(item.runs),
              formatInt(item.total_tokens)
            ])}
          />
        </Panel>

        <Panel title="Errors">
          <Table
            headers={["Run", "Route", "Model", "Started", "Error"]}
            rows={errors.map((item) => [
              String(item.id),
              item.route_kind,
              item.model_name || "—",
              formatDate(item.started_at),
              item.error_message || "—"
            ])}
          />
        </Panel>
      </section>
    </div>
  );
}

function ApiKeyForm(props: { showError: boolean; onSubmit: (key: string) => void }) {
  const [key, setKey] = useState("");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = key.trim();
    if (trimmed) {
      props.onSubmit(trimmed);
    }
  }

  return (
    <div className="page">
      <header className="hero">
        <p className="eyebrow">Project Dashboard</p>
        <h1>API key required</h1>
        <p className="subtle">Enter the dashboard API key to view runs, sessions, tokens, and costs.</p>
      </header>
      <div className="panel auth-panel">
        <form className="auth-form" onSubmit={handleSubmit}>
          <input
            className="auth-input"
            type="password"
            placeholder="X-API-Key"
            value={key}
            onChange={(event) => setKey(event.target.value)}
            autoFocus
          />
          <button className="auth-button" type="submit">
            Continue
          </button>
        </form>
        {props.showError && <p className="auth-error">Invalid API key. Please try again.</p>}
      </div>
    </div>
  );
}

function Panel(props: { title: string; children: ReactNode }) {
  return (
    <div className="panel">
      <div className="panel-head">
        <h2>{props.title}</h2>
      </div>
      {props.children}
    </div>
  );
}

function StatCard(props: { label: string; value: string | number }) {
  return (
    <div className="card">
      <span>{props.label}</span>
      <strong>{props.value}</strong>
    </div>
  );
}

function Table(props: { headers: string[]; rows: string[][] }) {
  return (
    <table className="table">
      <thead>
        <tr>
          {props.headers.map((header) => (
            <th key={header}>{header}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {props.rows.map((row, index) => (
          <tr key={index}>
            {row.map((cell, cellIndex) => (
              <td key={`${index}-${cellIndex}`}>{cell}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await authFetch(url);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function formatInt(value: number) {
  return new Intl.NumberFormat("en-US").format(value);
}

function formatDate(value: string) {
  return new Date(value).toLocaleString();
}

function formatPercent(overview: Overview | null) {
  if (!overview || !overview.totals.total_runs) {
    return "0%";
  }
  return `${Math.round((overview.totals.success_runs / overview.totals.total_runs) * 100)}%`;
}
