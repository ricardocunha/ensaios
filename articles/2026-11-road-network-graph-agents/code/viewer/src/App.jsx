import { useEffect, useMemo, useState } from "react";

const AGENTS = { maintenance: "Maintenance agent", closure: "Closure agent", coordinator: "Coordinator" };

const CLASSES = {
  notation: { ok: true, label: "notation variant", note: "the tool's value written another way, e.g. 3.789e-6" },
  derived: { ok: true, label: "derived", note: "100 − x, or a ± b of traced numbers in the same text" },
  upstream: { ok: false, label: "from an earlier agent's text", note: "not from a tool" },
  unsupported: { ok: false, label: "unsupported", note: "no tool result gives it" },
};

const llm = (r) => r.model !== "scripted";

const FILTERS = [
  { key: "all", label: "All LLM runs", test: llm },
  { key: "5", label: "5% budget", test: (r) => llm(r) && r.budget_pct === 5 },
  { key: "10", label: "10% budget", test: (r) => llm(r) && r.budget_pct === 10 },
  { key: "20", label: "20% budget", test: (r) => llm(r) && r.budget_pct === 20 },
  { key: "failed", label: "Closure schedule failed", test: (r) => llm(r) && !r.closure.ok },
  { key: "done", label: "Closure schedule completed", test: (r) => llm(r) && r.closure.ok },
  { key: "unsupported", label: "Unsupported number in the prose", test: (r) => r.regrade?.counts.unsupported > 0 },
  { key: "dry", label: "Scripted dry run (no LLM)", test: (r) => !llm(r) },
];

const fmt = (x, digits) => (x == null ? "—" : x.toLocaleString("en-US", digits == null ? {} : { minimumFractionDigits: digits, maximumFractionDigits: digits }));
const signed = (x, digits = 2) => (x > 0 ? "+" : x < 0 ? "−" : "") + Math.abs(x).toFixed(digits);
const title = (r) => `${r.budget_pct}% · run ${r.run}`;

function cause(agent) {
  const e = agent.error ?? "";
  if (e.includes("request_limit")) return `request limit reached after ${agent.requests} requests`;
  if (e.includes("exceeded max retries")) return "the same tool call was rejected until its retries ran out";
  if (e.includes("output retries")) return "its final answer was rejected by the output schema until the retries ran out";
  return e || "unknown";
}

export default function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(() => decodeURIComponent(window.location.hash.slice(1)));
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    fetch("data.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`data.json: HTTP ${r.status}`))))
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  const filters = useMemo(() => FILTERS.filter((f) => data?.runs.some(f.test)), [data]);
  const visible = useMemo(() => (data ? data.runs.filter((filters.find((f) => f.key === filter) ?? filters[0]).test) : []), [data, filters, filter]);

  const current = data?.runs.find((r) => r.id === selected) ?? visible[0] ?? data?.runs[0];
  const position = current ? visible.findIndex((r) => r.id === current.id) : -1;

  const go = (r) => {
    if (!r) return;
    setSelected(r.id);
    window.history.replaceState(null, "", `#${r.id}`);
  };
  const step = (delta) => go(visible[position === -1 ? 0 : (position + delta + visible.length) % visible.length]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.target.tagName === "INPUT") return;
      if (e.key === "ArrowRight") step(1);
      if (e.key === "ArrowLeft") step(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (error) {
    return (
      <main className="empty">
        <h1>No run data yet</h1>
        <p>
          The page could not load <code>data.json</code> ({error}). Run <code>make viewer</code> from the <code>code/</code> folder; it
          builds the file from <code>runs/</code>.
        </p>
      </main>
    );
  }
  if (!data || !current) return <main className="empty">Loading…</main>;

  const names = data.sections;
  const peers = data.runs.filter((r) => r.model === current.model && r.budget_pct === current.budget_pct);

  return (
    <div className="page">
      <header className="top">
        <div>
          <h1>Road maintenance agents: one pipeline run, start to end</h1>
          <p className="sub">
            {data.runs.filter(llm).length} pipeline runs from <code>{data.source}</code> · Belo Horizonte road network · solver baseline, then three agents on a
            local Qwen3-8B, audited by code
          </p>
        </div>
        <p className="notice">Synthetic repair costs, free-flow travel times, one city.</p>
      </header>

      <Tiles tiles={data.tiles} />
      <Maps figures={data.figures} />

      <div className="layout">
        <aside className="picker">
          <div className="filters">
            {filters.map((f) => (
              <button key={f.key} className={f.key === filter ? "chip on" : "chip"} onClick={() => setFilter(f.key)}>
                {f.label}
              </button>
            ))}
          </div>
          <p className="count">
            {visible.length} {visible.length === 1 ? "run" : "runs"} · budget · run number
          </p>
          <ul>
            {visible.map((r) => (
              <li key={r.id}>
                <button className={r.id === current.id ? "row on" : "row"} onClick={() => go(r)}>
                  <span className="num">{title(r)}</span>
                  <span className="codes">{r.closure.ok ? "schedule ok" : "schedule failed"}</span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <main className="steps">
          <div className="nav">
            <button onClick={() => step(-1)}>← Previous</button>
            <span>
              {current.budget_pct}% budget · run {current.run}
              {!llm(current) && " · scripted dry run"}
              {position >= 0 && ` · ${position + 1} of ${visible.length}`}
            </span>
            <button onClick={() => step(1)}>Next →</button>
          </div>

          <Step n="1" title="Start: the budget and the solver's plan" note="A greedy knapsack picks the sections with the most value per cost until the budget is spent. This is the baseline the agents start from.">
            <Baseline run={current} />
          </Step>

          <Step n="2" title="Maintenance agent: deviations from the solver" note="The agent may force sections in or out, each with a reason. The solver then refills the budget around those choices.">
            <Maintenance run={current} />
          </Step>

          <Step n="3" title="Closure agent: which month each major work closes" note="The 15 most critical sections of the plan go into 3 months, at most 5 per month, without closures that together cut hospital or school access.">
            <Closure run={current} names={names} />
          </Step>

          <Step n="4" title="Coordinator: the quarterly plan in prose" note="One call writes the summary, trade-offs and risks from the facts of steps 1–3. It has no tools.">
            <Coordinator agent={current.coordinator} />
          </Step>

          <Step n="5" title="End: the audit" note="Code, not a model, checks the plan against the solver, the schedule against the access rule, and every number in the prose against the tool results.">
            <Audit run={current} names={names} peers={peers} budget={data.budgets[current.budget_pct]} go={go} />
          </Step>
        </main>
      </div>
    </div>
  );
}

function Tiles({ tiles }) {
  if (!tiles.length) return null;
  return (
    <section className="summary" aria-label="Numbers over all LLM runs">
      {tiles.map((t) => (
        <div className="tile" key={t.label}>
          <span className="tile-label">{t.label}</span>
          <span className="tile-value">{t.value}</span>
          <span className="tile-unit">{t.unit}</span>
        </div>
      ))}
    </section>
  );
}

function Maps({ figures }) {
  if (!figures.length) return null;
  return (
    <section className="maps" aria-label="Maps of the network">
      {figures.map((f) => (
        <figure key={f.src}>
          <a href={f.src} target="_blank" rel="noreferrer">
            <img src={f.src} alt={f.caption} />
          </a>
          <figcaption>
            {f.caption}
            <span>{f.attribution}</span>
          </figcaption>
        </figure>
      ))}
    </section>
  );
}

function Step({ n, title, note, children }) {
  return (
    <section className="step">
      <div className="step-head">
        <span className="step-n">{n}</span>
        <div>
          <h2>{title}</h2>
          <p>{note}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

function Mark({ ok, children }) {
  return (
    <span className={ok ? "mark ok" : "mark bad"}>
      <span aria-hidden="true">{ok ? "✓" : "✗"}</span> {children}
    </span>
  );
}

function Sec({ id, names, info }) {
  const s = info ?? names?.[id];
  return (
    <span className="sec">
      <b>{id}</b>
      {s?.name && <span className="name"> {s.name}</span>}
      {s?.highway && <span className="name"> ({s.highway})</span>}
    </span>
  );
}

function Fact({ label, value, small }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>
        {value}
        {small && <small>{small}</small>}
      </dd>
    </div>
  );
}

function Status({ name, agent, okText, badText }) {
  const calls = Object.entries(agent.calls)
    .map(([tool, n]) => `${tool} × ${n}`)
    .join(", ");
  return (
    <p className="verdict">
      <Mark ok={agent.ok}>{agent.ok ? okText : badText}</Mark>
      <span className="muted">
        {" "}
        · {name}: {agent.requests} model {agent.requests === 1 ? "request" : "requests"}, {fmt(agent.seconds, 1)} s{calls && ` · calls: ${calls}`}
      </span>
    </p>
  );
}

function Rejected({ agent }) {
  if (!agent.rejected.length) return null;
  return (
    <div className="problems">
      <h3>Rejected by the tools or the output schema along the way</h3>
      <ul>
        {agent.rejected.map((r, i) => (
          <li key={i}>
            <code>{r.tool}</code>: {r.message}
            {r.times > 1 && <b> (× {r.times})</b>}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Baseline({ run }) {
  const s = run.solver;
  return (
    <div>
      <dl className="facts">
        <Fact label="Budget" value={`${run.budget_pct}%`} small={`of the total repair cost: ${fmt(s.budget, 1)} synthetic cost units`} />
        <Fact label="Solver plan" value={`${fmt(s.n_sections)} sections`} small={`${fmt(s.km, 1)} km · ${fmt(s.budget_used_pct, 1)}% of the budget used`} />
        <Fact label="Value captured" value={`${fmt(s.value_share_pct, 2)}%`} small="of the value of all candidate sections (criticality × condition)" />
        <Fact label="Pothole requests covered" value={`${fmt(s.requests_covered_pct, 2)}%`} small={`${fmt(s.requests_covered)} requests on the chosen sections`} />
      </dl>
      {s.length_by_class && (
        <p className="line">
          <b>Length by road class:</b> {s.length_by_class}.
        </p>
      )}
      {s.top_roads && (
        <p className="line">
          <b>Top roads by value:</b> {s.top_roads}.
        </p>
      )}
      {run.limits && (
        <p className="line muted">
          Request limits for the agents in this run: maintenance {run.limits.maintenance}, closure {run.limits.closure}, coordinator {run.limits.coordinator}.
        </p>
      )}
    </div>
  );
}

function Maintenance({ run }) {
  const agent = run.maintenance;
  const deviations = agent.output?.deviations ?? [];
  const { solver, final } = run;
  const rows = [
    ["Sections", solver.n_sections, final.n_sections, 0, ""],
    ["Value captured", solver.value_share_pct, final.value_share_pct, 2, "%"],
    ["Pothole requests covered", solver.requests_covered_pct, final.requests_covered_pct, 2, "%"],
    ["Requests on chosen sections", solver.requests_covered, final.requests_covered, 0, ""],
    ["Budget used", solver.budget_used_pct, final.budget_used_pct, 1, "%"],
  ];
  return (
    <div>
      <Status name="maintenance agent" agent={agent} okText={`Proposal returned: ${deviations.length} deviations`} badText={`No proposal (${cause(agent)}); the solver plan stands`} />
      {deviations.length > 0 && (
        <table className="findings">
          <thead>
            <tr>
              <th>Action</th>
              <th>Section</th>
              <th className="r">Requests</th>
              <th className="r">Criticality</th>
              <th>Reason given by the agent</th>
            </tr>
          </thead>
          <tbody>
            {deviations.map((d, i) => (
              <tr key={i}>
                <td>{d.action === "add" ? "+ add" : "− remove"}</td>
                <td style={{ whiteSpace: "normal", minWidth: 190 }}>
                  <Sec id={d.section_id} info={d} />
                </td>
                <td className="r">{fmt(d.requests)}</td>
                <td className="r">{d.criticality == null ? "—" : d.criticality.toFixed(4)}</td>
                <td>{d.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {agent.output?.rationale && <blockquote>{agent.output.rationale}</blockquote>}
      <Rejected agent={agent} />
      <h3>The plan after the deviations, against the solver's</h3>
      <table>
        <thead>
          <tr>
            <th>Measure</th>
            <th className="r">Solver</th>
            <th className="r">After deviations</th>
            <th className="r">Difference</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, a, b, digits, unit]) => (
            <tr key={label}>
              <th scope="row">{label}</th>
              <td className="r">
                {fmt(a, digits)}
                {unit}
              </td>
              <td className="r">
                {fmt(b, digits)}
                {unit}
              </td>
              <td className="r">
                {signed(b - a, digits)}
                {unit && " points"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="takeaway">
        The plan after the deviations has {fmt(final.value_vs_solver_pct, 2)}% of the solver plan's value and covers {signed(final.requests_covered_pct - solver.requests_covered_pct)}{" "}
        points of pothole requests relative to it.
      </p>
    </div>
  );
}

function Closure({ run, names }) {
  const agent = run.closure;
  const out = agent.output;
  const calls = Object.values(agent.calls).reduce((a, b) => a + b, 0);
  return (
    <div>
      <Status name="closure agent" agent={agent} okText="Schedule returned" badText={`No schedule returned: ${cause(agent)}`} />
      {!agent.ok && (
        <p className="line">
          {calls} tool calls, {agent.distinct_calls} with distinct arguments. Logged error: <code>{agent.error}</code>
        </p>
      )}
      <Rejected agent={agent} />
      {agent.last_tool_answer && (
        <div className="problems">
          <h3>Last answer of the tool before the run stopped (as logged, cut at 600 characters)</h3>
          <pre className="tool">{agent.last_tool_answer}</pre>
        </div>
      )}
      {out && (
        <>
          <div className="answers">
            {out.phases.map((p) => (
              <article className="answer month" key={p.month}>
                <h3>Month {p.month}</h3>
                <ul>
                  {p.section_ids.map((id) => (
                    <li key={id}>
                      <Sec id={id} names={names} />
                    </li>
                  ))}
                </ul>
                <p className="muted">
                  Stated by the agent: {fmt(p.trips_affected)} of 1,000 sampled trips affected, {fmt(p.total_delay_s, 1)} s extra travel time in total, hospital access
                  lost at {p.hospital_nodes_lost} nodes, school access at {p.school_nodes_lost} nodes.
                </p>
              </article>
            ))}
          </div>
          {out.flags.length > 0 && (
            <>
              <h3>Access flags raised by the agent</h3>
              <table>
                <thead>
                  <tr>
                    <th>Month</th>
                    <th>Facility</th>
                    <th className="r">Nodes losing access</th>
                    <th>Note</th>
                  </tr>
                </thead>
                <tbody>
                  {out.flags.map((f, i) => (
                    <tr key={i}>
                      <td>{f.month}</td>
                      <td>{f.facility}</td>
                      <td className="r">{f.nodes_lost}</td>
                      <td>{f.note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
          {out.rationale && <blockquote>{out.rationale}</blockquote>}
        </>
      )}
      {!out && (
        <>
          <h3>The 15 major works it had to schedule</h3>
          <p>
            {run.works.map((id) => (
              <Sec key={id} id={id} names={names} />
            ))}
          </p>
        </>
      )}
    </div>
  );
}

function Coordinator({ agent }) {
  const out = agent.output;
  return (
    <div>
      <Status name="coordinator" agent={agent} okText="Plan written" badText={`No plan written (${cause(agent)})`} />
      {out && (
        <>
          <blockquote>{out.summary}</blockquote>
          <h3>Trade-offs</h3>
          <table>
            <thead>
              <tr>
                <th>Topic</th>
                <th>Decision</th>
                <th>What it costs</th>
              </tr>
            </thead>
            <tbody>
              {out.trade_offs.map((t, i) => (
                <tr key={i}>
                  <th scope="row">{t.topic}</th>
                  <td>{t.decision}</td>
                  <td>{t.cost}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {out.risks.length > 0 && (
            <div className="problems">
              <h3>Risks</h3>
              <ul>
                {out.risks.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
      <Rejected agent={agent} />
    </div>
  );
}

function Schedules({ run, names }) {
  const rows = [
    ["Naive (priority order)", run.schedules.naive],
    ["Heuristic (code, no LLM)", run.schedules.heuristic],
    ["Closure agent", run.schedules.agent_schedule],
  ];
  return (
    <table>
      <thead>
        <tr>
          <th>Schedule of the same works</th>
          <th>Access violations</th>
          <th className="r">Interaction nodes</th>
          <th className="r">Worst-month delay</th>
          <th className="r">Sum over months</th>
          <th>Hospital nodes lost per month</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([label, s]) => (
          <tr key={label}>
            <th scope="row">{label}</th>
            {s ? (
              <>
                <td>
                  <Mark ok={s.violations === 0}>{s.violations === 0 ? "none" : `${s.violations} ${s.violations === 1 ? "month" : "months"}`}</Mark>
                  {Object.entries(s.conflicting_pairs ?? {}).map(([month, pairs]) => (
                    <div key={month} className="muted">
                      month {month}: {pairs.map((p) => p.join(" + ")).join("; ")}
                    </div>
                  ))}
                </td>
                <td className="r">{fmt(s.interaction_nodes)}</td>
                <td className="r">{fmt(s.peak_total_delay_s, 1)} s</td>
                <td className="r">{fmt(s.sum_total_delay_s, 1)} s</td>
                <td>{s.hospital_nodes_lost ? Object.values(s.hospital_nodes_lost).join(" / ") : "—"}</td>
              </>
            ) : (
              <td colSpan="5" className="muted">
                no schedule to score
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Numbers({ run }) {
  const audit = run.text_audit;
  const re = run.regrade;
  const missing = re?.not_strict ?? audit.not_found ?? [];
  return (
    <div>
      <p>
        <Mark ok={audit.grounded === audit.checked}>
          {audit.grounded} of {audit.checked} numbers traced
        </Mark>{" "}
        to a tool result by exact lookup
        {run.ledger_size != null && ` in a ledger of ${fmt(run.ledger_size)} numbers the tools returned in this run`}
        {audit.trivial_skipped > 0 && ` (${audit.trivial_skipped} trivial numbers such as month indices skipped)`}. The run file lists the numbers that were not
        traced; the traced ones are only counted.
      </p>
      {re && (
        <p className="line">
          Second pass over the misses: <b>{re.with_derived}</b> traced when notation variants and derived numbers count.{" "}
          {Object.entries(CLASSES)
            .map(([key, c]) => `${re.counts[key]} ${c.label}`)
            .join(" · ")}
          .
        </p>
      )}
      {missing.length > 0 && (
        <table className="findings">
          <thead>
            <tr>
              <th>Where</th>
              <th>Number</th>
              <th>{re ? "Second pass" : "Lookup"}</th>
              <th>Text around it</th>
            </tr>
          </thead>
          <tbody>
            {missing.map((m, i) => {
              const c = CLASSES[m.class];
              return (
                <tr key={i}>
                  <td>
                    <code>{m.where}</code>
                  </td>
                  <td>
                    <b>{m.number}</b>
                  </td>
                  <td title={c?.note}>{c ? <Mark ok={c.ok}>{c.label}</Mark> : <Mark ok={false}>not found</Mark>}</td>
                  <td>{m.context}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      <p className="line muted">The lookup checks the number, not the sentence: a traced number can still be used in a wrong claim.</p>
    </div>
  );
}

function Audit({ run, names, peers, budget, go }) {
  const { solver, final } = run;
  const p = run.phase_audit;
  const c = budget?.consistency;
  return (
    <div>
      <h3>Plan against the solver</h3>
      <p>
        {fmt(final.value_vs_solver_pct, 2)}% of the solver plan's value; pothole requests covered {fmt(final.requests_covered_pct, 2)}% against {fmt(solver.requests_covered_pct, 2)}% (
        {signed(final.requests_covered_pct - solver.requests_covered_pct)} points); {run.plan_audit.adds.length} sections forced in, {run.plan_audit.removes.length} excluded; overlap with
        the solver plan (Jaccard) {fmt(run.plan_audit.jaccard_vs_solver, 3)}.
      </p>

      <h3>Schedule against the access rule</h3>
      <Schedules run={run} names={names} />
      <p className="line muted">
        A violation is a month whose closures together cut hospital or school access that no single work of that month cuts alone. Delay is extra travel time over
        1,000 sampled trips, free-flow.
      </p>
      {p && (
        <p className="line">
          <Mark ok={p.phase_fields_ok === p.phase_fields && p.flags_ok === p.flags_needed}>
            {p.phase_fields_ok} of {p.phase_fields} month figures and {p.flags_ok} of {p.flags_needed} access flags
          </Mark>{" "}
          stated by the closure agent match the tools' recomputation; {p.flags_missed.length} flags missed.
        </p>
      )}

      <h3>Numbers in the agents' prose</h3>
      <Numbers run={run} />

      {peers.length > 1 && (
        <>
          <h3>The {peers.length} runs at this budget</h3>
          <table>
            <thead>
              <tr>
                <th>Run</th>
                <th>Maintenance</th>
                <th className="r">Adds / removes</th>
                <th className="r">Value vs solver</th>
                <th className="r">Requests covered</th>
                <th>Closure</th>
                <th className="r">Prose numbers traced</th>
                <th className="r">Second pass</th>
              </tr>
            </thead>
            <tbody>
              {peers.map((r) => (
                <tr key={r.id} className={r.id === run.id ? "current" : ""}>
                  <th scope="row">
                    {r.id === run.id ? (
                      `run ${r.run} (this one)`
                    ) : (
                      <button className="link" onClick={() => go(r)}>
                        run {r.run}
                      </button>
                    )}
                  </th>
                  <td>
                    <Mark ok={r.maintenance.ok}>{r.maintenance.ok ? "proposal" : "failed"}</Mark>
                  </td>
                  <td className="r">
                    {r.plan_audit.adds.length} / {r.plan_audit.removes.length}
                  </td>
                  <td className="r">{fmt(r.final.value_vs_solver_pct, 2)}%</td>
                  <td className="r">{fmt(r.final.requests_covered_pct, 2)}%</td>
                  <td>
                    <Mark ok={r.closure.ok}>{r.closure.ok ? "schedule" : "failed"}</Mark>
                  </td>
                  <td className="r">
                    {r.text_audit.grounded}/{r.text_audit.checked}
                  </td>
                  <td className="r">{r.regrade?.with_derived ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {c && (
            <p className="line muted">
              Same inputs, {c.runs} runs: the deviation sets overlap by {fmt(c.deviation_jaccard_mean, 3)} (mean pairwise Jaccard, 1 = identical); the final plans by{" "}
              {fmt(c.final_plan_jaccard_mean, 3)}; value captured varies by {fmt(c.value_share_pct_std, 2)} points (standard deviation).
            </p>
          )}
        </>
      )}
    </div>
  );
}
