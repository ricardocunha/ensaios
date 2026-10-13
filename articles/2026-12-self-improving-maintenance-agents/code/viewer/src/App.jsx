import { useEffect, useMemo, useState } from "react";

const ARM_NAMES = { none: "No memory", ungated: "Ungated memory", gated: "Gated memory" };
const ARMS = Object.keys(ARM_NAMES);

const CLASS_NAMES = {
  pre_incident: "Followed by a logbook incident",
  false_alarm: "False alarm",
  near_incident: "Near an incident",
};

const TOOLS = {
  residual_series: "daily residuals of one signal group, up to the alarm day",
  context_signals: "converter and nacelle residuals, hours with data, the other turbines' score that day",
  maintenance_log: "logbook rows on this turbine before the decision time",
  final_diagnosis: "the structured answer (not a lookup)",
};

const FILTERS = [
  { key: "all", label: "All", test: () => true },
  { key: "failure", label: "Followed by a logbook incident", test: (e) => e.hindsight.klass === "pre_incident" },
  { key: "false", label: "False alarm", test: (e) => e.hindsight.klass === "false_alarm" },
  { key: "action", label: "Action differs between arms", test: (e, v) => differs(e, v, "action") },
  { key: "component", label: "Component differs between arms", test: (e, v) => differs(e, v, "component") },
  { key: "memory", label: "Gated memory showed a past episode", test: (e, v) => (e.runs[v]?.gated?.memories.length ?? 0) > 0 },
];

function differs(episode, version, field) {
  const values = Object.values(episode.runs[version] ?? {}).map((a) => a.diagnosis?.[field] ?? "error");
  return new Set(values).size > 1;
}

function rule(key, policy) {
  const p = policy ?? {};
  return (
    {
      outcome_pending: "outcome not known yet",
      low_similarity: `similarity below ${p.min_similarity}`,
      too_old: `older than ${p.max_age_days} days`,
      other_turbine: "other turbine",
      other_turbine_and_group: "other turbine and other signal group",
      over_k: `passed the rules, beyond the ${p.max_k} kept`,
    }[key] ?? key
  );
}

const signed = (z) => `${z > 0 ? "+" : ""}${z.toFixed(1)}`;
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

export default function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(() => decodeURIComponent(window.location.hash.slice(1)));
  const [chosen, setChosen] = useState("v1");
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetch("data.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`data.json: HTTP ${r.status}`))))
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  const version = data?.versions.includes(chosen) ? chosen : data?.versions[0];

  const visible = useMemo(() => {
    if (!data) return [];
    const keep = FILTERS.find((f) => f.key === filter).test;
    const q = search.trim().toLowerCase();
    const match = (e) => !q || [String(e.id), e.turbine, e.start, e.top_group ?? ""].some((x) => x.toLowerCase().includes(q));
    return data.episodes.filter((e) => keep(e, version) && match(e));
  }, [data, filter, search, version]);

  const current = data?.episodes.find((e) => String(e.id) === selected) ?? visible[0] ?? data?.episodes[0];
  const position = current ? visible.findIndex((e) => e.id === current.id) : -1;

  const go = (e) => {
    if (!e) return;
    setSelected(String(e.id));
    window.history.replaceState(null, "", `#${e.id}`);
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

  const summary = data.summary[version] ?? {};
  const runs = current.runs[version] ?? {};
  const arms = ARMS.filter((a) => runs[a]);
  const toggle = data.versions.length > 1 && <Versions versions={data.versions} version={version} onChange={setChosen} />;
  const goTo = (id) => go(data.episodes.find((e) => e.id === id));

  return (
    <div className="page">
      <header className="top">
        <div>
          <h1>Maintenance agent replay: one alarm, start to end</h1>
          <p className="sub">
            {data.episodes.length} alarm episodes replayed in time order · one EDP wind farm, 5 turbines · local model · three arms: no memory,
            ungated memory, gated memory
          </p>
        </div>
        <p className="notice">
          One wind farm{data.logbook ? `, ${data.logbook.incidents} incidents` : ""}: too few for a statistical claim.
        </p>
      </header>

      {toggle && <div className="scope">Numbers and answers shown for {toggle}</div>}
      <Summary summary={summary} logbook={data.logbook} version={version} />

      <div className="layout">
        <aside className="picker">
          <input type="search" placeholder="Turbine, date or episode (e.g. T07, 2016-11)" value={search} onChange={(e) => setSearch(e.target.value)} />
          <div className="filters">
            {FILTERS.map((f) => (
              <button key={f.key} className={f.key === filter ? "chip on" : "chip"} onClick={() => setFilter(f.key)}>
                {f.label}
              </button>
            ))}
          </div>
          <p className="count">{plural(visible.length, "episode")}, oldest first</p>
          <ul>
            {visible.map((e) => (
              <li key={e.id}>
                <button className={e.id === current.id ? "row on" : "row"} onClick={() => go(e)}>
                  <span className="num">#{e.id}</span>
                  <span className="codes">
                    {e.turbine} · {e.start} · {e.top_group ?? "n/a"}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <main className="steps">
          <div className="nav">
            <button onClick={() => step(-1)}>← Previous</button>
            <span>
              Episode #{current.id} · {current.turbine} · {current.start}
              {position >= 0 && ` · ${position + 1} of ${visible.length}`}
            </span>
            <button onClick={() => step(1)}>Next →</button>
          </div>

          <Step n="1" title="Start: the alarm, as known at decision time" note="What the prompt stated, built from data up to the end of the first alarm day. Nothing later.">
            <Alarm episode={current} />
          </Step>

          <Step
            n="2"
            title="Look up: the tools the agent called"
            note="Tool calls in the order the run recorded them. The run files keep the tool names, not the arguments or the returned text."
          >
            <div className="answers">
              {arms.map((a) => (
                <Lookups key={a} name={ARM_NAMES[a]} run={runs[a]} />
              ))}
            </div>
          </Step>

          <Step
            n="3"
            title="Remember: what memory put in the prompt"
            note="Past episodes as the prompt printed them, with an outcome only where it was already known at decision time. The run files count the gate's rejections per rule; they do not list the rejected episodes."
          >
            <div className="answers">
              {arms.map((a) => (
                <Memory key={a} arm={a} run={runs[a]} policy={summary.policies?.[a]} goTo={goTo} />
              ))}
            </div>
          </Step>

          <Step n="4" title="Diagnose: the answer in each arm" note={`The same alarm, three memory arms, prompt ${version}.`}>
            {toggle}
            <div className="answers">
              {arms.map((a) => (
                <Diagnosis key={a} name={ARM_NAMES[a]} run={runs[a]} />
              ))}
            </div>
          </Step>

          <Step
            n="5"
            title="End: what the logbook says happened afterwards"
            note="Hindsight. The agent did not have any of this when it answered; the replay used it only for scoring."
          >
            <Hindsight episode={current} version={version} arms={arms} />
          </Step>
        </main>
      </div>

      <footer className="foot">
        Data: CARE to Compare (Gück &amp; Roelofs, Zenodo, DOI 10.5281/zenodo.15846963) and EDP Open Data wind farm failure logbooks 2016/2017, both
        CC BY-SA 4.0. What this page shows is derived from them and is shared under CC BY-SA 4.0.
      </footer>
    </div>
  );
}

function Versions({ versions, version, onChange }) {
  return (
    <span className="toggle" role="group" aria-label="Prompt version">
      {versions.map((v) => (
        <button key={v} className={v === version ? "on" : ""} aria-pressed={v === version} onClick={() => onChange(v)}>
          Prompt {v}
        </button>
      ))}
    </span>
  );
}

function Summary({ summary, logbook, version }) {
  const arms = ARMS.filter((a) => summary.arms?.[a]);
  const classes = summary.classes ?? {};
  const total = summary.arms?.[arms[0]]?.episodes;
  const perArm = (pick) => arms.map((a) => [ARM_NAMES[a], pick(summary.arms[a])]);
  const single = [
    ["Alarms replayed", total, `episodes, each in ${plural(arms.length, "arm")}`],
    ["Followed by a logbook incident", classes.pre_incident, `of ${total} alarms, started up to 30 days before one`],
    ["False alarms", classes.false_alarm, `of ${total} alarms, started on a healthy day`],
    ["Logbook incidents", logbook?.incidents, `merged from ${logbook?.rows} logbook rows`],
  ].filter(([, v]) => v != null);
  const grouped = arms.length
    ? [
        ['Answered "inspect"', "of all alarms", perArm((a) => `${a.inspect}/${a.episodes}`)],
        ["Named the failed component", "of alarms followed by an incident", perArm((a) => a.component_ok)],
        ['Answered "ignore"', "of false alarms", perArm((a) => a.ignore_on_false_alarm)],
        ["Past episodes in the prompt", "mean per alarm", perArm((a) => a.mean_memories?.toFixed(2)).filter(([, v]) => v != null)],
      ].filter(([, , rows]) => rows.length)
    : [];
  if (!single.length && !grouped.length) return null;
  return (
    <section className="summary" aria-label={`Results over all alarms, prompt ${version}`}>
      {single.map(([label, value, unit]) => (
        <div className="tile" key={label}>
          <span className="tile-label">{label}</span>
          <span className="tile-value">{value}</span>
          <span className="tile-unit">{unit}</span>
        </div>
      ))}
      {grouped.map(([label, unit, rows]) => (
        <div className="tile" key={label}>
          <span className="tile-label">{label}</span>
          <dl className="tile-rows">
            {rows.map(([name, value]) => (
              <div key={name}>
                <dt>{name}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
          <span className="tile-unit">{unit}</span>
        </div>
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

function Alarm({ episode }) {
  return (
    <div className="alarm">
      <dl className="facts">
        <Fact name="Turbine" value={episode.turbine} />
        <Fact name="First alarm day" value={episode.start} />
        <Fact name="Decision time" value={episode.decision_time} />
        {episode.score != null && <Fact name="Detector score that day" value={`${episode.score.toFixed(1)} (alarm above 2.5)`} />}
        <Fact name="Top signal group" value={episode.top_group ?? "n/a"} />
        <Fact name="Logbook component it maps to" value={episode.detector_component ?? "n/a"} />
        {episode.context_signal && <Fact name="Top context signal" value={episode.context_signal} />}
      </dl>
      <div className="alarm-detail">
        <div>
          <h3>Top residual signals on the alarm day</h3>
          <table>
            <thead>
              <tr>
                <th>Signal</th>
                <th>Measures</th>
                <th className="right">Residual z</th>
              </tr>
            </thead>
            <tbody>
              {episode.signals.map((s) => (
                <tr key={s.signal}>
                  <td>
                    <code>{s.signal}</code>
                  </td>
                  <td>{s.label}</td>
                  <td className="right">{signed(s.z)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted small">z = 0 means the reading is what the normal-behaviour model expects.</p>
        </div>
        {episode.series && <Chart series={episode.series} />}
      </div>
    </div>
  );
}

function Fact({ name, value }) {
  return (
    <div>
      <dt>{name}</dt>
      <dd>{value}</dd>
    </div>
  );
}

const W = 520;
const H = 200;
const BOX = { left: 34, right: 16, top: 14, bottom: 26 };

function ticks(lo, hi) {
  const step = [1, 2, 5, 10, 20, 50].find((s) => (hi - lo) / s <= 5) ?? 100;
  const out = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) out.push(t);
  return out;
}

function Chart({ series }) {
  const [hover, setHover] = useState(null);
  const values = series.z.filter((v) => v != null);
  const lo = Math.floor(Math.min(0, ...values));
  const hi = Math.ceil(Math.max(0, ...values));
  const last = series.z.length - 1;
  const x = (i) => BOX.left + (i / last) * (W - BOX.left - BOX.right);
  const y = (v) => BOX.top + ((hi - v) / (hi - lo || 1)) * (H - BOX.top - BOX.bottom);
  let path = "";
  series.z.forEach((v, i) => {
    if (v != null) path += `${series.z[i - 1] == null ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
  });
  const onMove = (e) => {
    const box = e.currentTarget.getBoundingClientRect();
    const i = Math.round((((e.clientX - box.left) / box.width) * W - BOX.left) / ((W - BOX.left - BOX.right) / last));
    setHover(Math.max(0, Math.min(last, i)));
  };
  const shown = hover != null && series.z[hover] != null ? hover : null;
  return (
    <figure className="chart">
      <figcaption>
        <h3>
          {series.label}: daily residual z, {series.days.length} days up to the alarm day
        </h3>
      </figcaption>
      <div className="chart-box">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Daily residual z of ${series.label} from ${series.days[0]} to ${series.days[last]}`} onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
          {ticks(lo, hi).map((t) => (
            <g key={t}>
              <line className={t === 0 ? "zero" : "grid"} x1={BOX.left} x2={W - BOX.right} y1={y(t)} y2={y(t)} />
              <text className="tick" x={BOX.left - 6} y={y(t) + 4} textAnchor="end">
                {t}
              </text>
            </g>
          ))}
          <text className="tick" x={BOX.left} y={H - 6}>
            {series.days[0]}
          </text>
          <text className="tick" x={W - BOX.right} y={H - 6} textAnchor="end">
            {series.days[last]} (alarm day)
          </text>
          <path className="line" d={path} />
          {series.z[last] != null && <circle className="dot" cx={x(last)} cy={y(series.z[last])} r="4" />}
          {shown != null && (
            <g>
              <line className="cross" x1={x(shown)} x2={x(shown)} y1={BOX.top} y2={H - BOX.bottom} />
              <circle className="dot" cx={x(shown)} cy={y(series.z[shown])} r="4" />
            </g>
          )}
        </svg>
        {shown != null && (
          <div className={shown > last / 2 ? "tip left" : "tip"} style={{ left: `${(x(shown) / W) * 100}%`, top: `${(y(series.z[shown]) / H) * 100}%` }}>
            <b>{signed(series.z[shown])}</b> {series.days[shown]}
          </div>
        )}
      </div>
    </figure>
  );
}

function Lookups({ name, run }) {
  return (
    <article className="answer">
      <h3>{name}</h3>
      <ol className="tools">
        {run.tools.map((t, i) => (
          <li key={i}>
            <code>{t}</code>
            <span className="muted"> {TOOLS[t] ?? ""}</span>
          </li>
        ))}
      </ol>
      {run.tools.length === 0 && <p className="muted">No tool call recorded.</p>}
      <p className="muted">
        {plural(run.requests, "model request")} · {run.input_tokens.toLocaleString("en")} tokens in, {run.output_tokens.toLocaleString("en")} out ·{" "}
        {run.seconds.toFixed(1)} s
      </p>
    </article>
  );
}

function Memory({ arm, run, policy, goTo }) {
  if (arm === "none") {
    return (
      <article className="answer">
        <h3>{ARM_NAMES[arm]}</h3>
        <p className="muted">This arm has no memory: the prompt holds only the alarm.</p>
        {run.track_record && <blockquote>{run.track_record}</blockquote>}
      </article>
    );
  }
  const rejected = Object.entries(run.gate_rejections);
  return (
    <article className="answer">
      <h3>{ARM_NAMES[arm]}</h3>
      <p className="muted">
        {plural(run.memories_visible, "past episode")} visible at decision time, {run.memories.length} shown to the model.
      </p>
      {run.memories.map((m) => (
        <div className="memory" key={m.episode_id}>
          <p>
            <button className="link" onClick={() => goTo(m.episode_id)}>
              Episode #{m.episode_id}
            </button>{" "}
            <span className="label">similarity {m.similarity.toFixed(2)}</span> <span className="label">{m.age_days.toFixed(0)} days earlier</span>
          </p>
          {m.summary && <p className="small">{m.summary}</p>}
          {m.diagnosis_then && <p className="small">Diagnosis then: {m.diagnosis_then}.</p>}
          <p className="small">
            <b>Outcome known then:</b> {m.outcome ?? (m.outcome_known ? "known" : "not known yet")}.{m.lesson && ` Lesson: ${m.lesson}`}
          </p>
        </div>
      ))}
      {rejected.length > 0 && (
        <div>
          <h4>{arm === "gated" ? "Rejected by the gate, by rule" : "Not shown"}</h4>
          <ul className="rules">
            {rejected.map(([key, n]) => (
              <li key={key}>
                <b>{n}</b> {rule(key, policy)}
              </li>
            ))}
          </ul>
        </div>
      )}
      {run.track_record && (
        <div>
          <h4>Track record line in the prompt</h4>
          <blockquote>{run.track_record}</blockquote>
        </div>
      )}
    </article>
  );
}

function Diagnosis({ name, run }) {
  const d = run.diagnosis;
  if (!d) {
    return (
      <article className="answer">
        <h3>{name}</h3>
        <p>No diagnosis recorded: {run.error ?? "unknown error"}</p>
      </article>
    );
  }
  const why = d.differs_from_record && d.differs_from_record.trim().toLowerCase() !== "n/a" ? d.differs_from_record : null;
  return (
    <article className="answer">
      <h3>{name}</h3>
      <dl className="verdict-grid">
        <Fact name="Action" value={<span className="label strong">{d.action}</span>} />
        <Fact name="Component" value={d.component} />
        <Fact name="Urgency" value={d.urgency} />
        <Fact name="Confidence" value={d.confidence.toFixed(2)} />
      </dl>
      <h4>Evidence given</h4>
      <blockquote>{d.evidence}</blockquote>
      {why && (
        <>
          <h4>Why this alarm differs from the track record</h4>
          <blockquote>{why}</blockquote>
        </>
      )}
    </article>
  );
}

function Mark({ ok, yes, no }) {
  return (
    <span className={ok ? "mark ok" : "mark bad"}>
      <span aria-hidden="true">{ok ? "✓" : "✗"}</span> {ok ? yes : no}
    </span>
  );
}

function Hindsight({ episode, version, arms }) {
  const h = episode.hindsight;
  const runs = episode.runs[version];
  const scored = h.scored?.[version] ?? {};
  const failure = h.klass === "pre_incident";
  const actions = new Set(arms.map((a) => runs[a].diagnosis?.action ?? "error"));
  return (
    <div>
      <div className="outcome">
        <span className="tag">Hindsight</span>
        {h.klass ? (
          <p>
            <b>{CLASS_NAMES[h.klass]}.</b>{" "}
            {failure &&
              `The logbook has an incident on ${episode.turbine} ${plural(h.days_before_incident, "day")} after the first alarm day, component ${h.incident_component}.`}
            {h.klass === "false_alarm" && `The alarm started on a healthy day: outside the window from 30 days before to 30 days after any logbook incident on ${episode.turbine}.`}
            {h.klass === "near_incident" &&
              `The alarm started inside the 30-day window around a logbook incident on ${episode.turbine}, but no incident began in the 30 days after it. The replay does not score the action for these.`}
          </p>
        ) : (
          <p className="muted">No scoring class in the run files for this episode.</p>
        )}
        {h.n_days != null && (
          <p className="muted">
            The alarm went on for {plural(h.n_days, "day")} (to {h.end}), with a peak detector score of {h.peak_score}.
          </p>
        )}
      </div>
      <table className="result">
        <thead>
          <tr>
            <th>Arm</th>
            <th>Action</th>
            <th>Component</th>
            <th>Component against the logbook</th>
            <th>Action against the outcome</th>
          </tr>
        </thead>
        <tbody>
          {arms.map((a) => {
            const d = runs[a].diagnosis;
            const s = scored[a];
            return (
              <tr key={a}>
                <th scope="row">{ARM_NAMES[a]}</th>
                <td>{d?.action ?? "error"}</td>
                <td>{d?.component ?? "—"}</td>
                <td>{failure && s ? <Mark ok={s.component_ok} yes="matches the failed component" no={`logbook says ${h.incident_component}`} /> : "not scored"}</td>
                <td>
                  {s && h.klass !== "near_incident" ? (
                    <Mark ok={s.appropriate} yes={failure ? "inspect before an incident" : "ignore on a false alarm"} no={failure ? "no inspection before an incident" : "not ignore on a false alarm"} />
                  ) : (
                    "not scored"
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="takeaway">
        {actions.size === 1
          ? `All ${arms.length === 1 ? "" : `${arms.length} `}arms gave the same action (${[...actions][0]}) on this alarm: memory did not change the decision.`
          : "The action differs between arms on this alarm."}
        {differs(episode, version, "component") && " The component named differs between arms."}
      </p>
    </div>
  );
}
