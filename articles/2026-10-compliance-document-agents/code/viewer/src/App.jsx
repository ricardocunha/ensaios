import { useEffect, useMemo, useState } from "react";

const LEVELS = { text: "Text PDF", heavy: "Heavy scan" };
const LEVEL_NOTES = { text: "born-digital, no OCR needed", heavy: "110 dpi, 3° skew, faded; read by OCR" };
const VERDICTS = { compliant: "compliant", violation: "violation", not_applicable: "not applicable", unclear: "unclear" };
const SIGNALS = [
  ["samples disagree", "Samples disagree"],
  ["quote not verbatim", "Quote not verbatim"],
  ["page quality < 0.9", "OCR score of the quoted pages below 0.9"],
  ["auditor disputes", "Auditor disputes a reported violation"],
];

const FILTERS = [
  { key: "all", label: "All", test: () => true },
  { key: "escalated", label: "Escalated", test: (d) => d.escalated },
  { key: "wrong", label: "Wrong", test: (d) => !d.correct },
  { key: "missed", label: "Wrong and not escalated", test: (d) => !d.correct && !d.escalated },
  { key: "violation", label: "Label is violation", test: (d, item) => item.label === "violation" },
  { key: "disagree", label: "Samples disagree", test: (d) => d.agreement < 1 },
];

// the run's binary answer: violation, or nothing to flag (compliant / not applicable)
function flagged(verdict) {
  return { violation: true, compliant: false, not_applicable: false }[verdict] ?? null;
}

function flagText(flag) {
  return flag === null ? "no valid answer" : flag ? "violation" : "nothing to flag";
}

function outcome(d) {
  if (d.correct) return d.escalated ? ["warn", "✓", "Correct, and escalated to a human anyway"] : ["ok", "✓", "Correct, kept by the agent"];
  return d.escalated ? ["warn", "✗", "Wrong, escalated to a human"] : ["bad", "✗", "Wrong and not escalated"];
}

function lower(level) {
  return LEVELS[level].replace(/^./, (c) => c.toLowerCase());
}

function percent(x, digits = 1) {
  return `${(x * 100).toFixed(digits)}%`;
}

function pages(list) {
  return list?.length ? `page ${list.join(", ")}` : "no page";
}

export default function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(() => decodeURIComponent(window.location.hash.slice(1)));
  const [mode, setMode] = useState("text");
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetch("data.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`data.json: HTTP ${r.status}`))))
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  const levels = data ? Object.keys(LEVELS).filter((l) => data.summary[l]) : [];
  const level = levels.includes(mode) ? mode : "text";

  const visible = useMemo(() => {
    if (!data) return [];
    const keep = FILTERS.find((f) => f.key === filter).test;
    const q = search.trim().toLowerCase();
    return data.items.filter((item) => {
      const d = item.conditions[level]?.decision;
      return d && keep(d, item) && (!q || `${item.id} ${item.label}`.toLowerCase().includes(q));
    });
  }, [data, filter, search, level]);

  const current = data?.items.find((c) => c.id === selected) ?? visible[0] ?? data?.items[0];
  const position = current ? visible.findIndex((c) => c.id === current.id) : -1;

  const go = (c) => {
    if (!c) return;
    setSelected(c.id);
    window.history.replaceState(null, "", `#${c.id}`);
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

  const rule = data.rules[current.rule];
  const contract = data.contracts[current.doc];
  const shown = current.conditions[level] ? level : "text";
  const run = current.conditions[shown];
  const parse = contract.parses[shown];
  const n = data.summary.text;

  return (
    <div className="page">
      <header className="top">
        <div>
          <h1>Contract review: one rule on one contract, start to end</h1>
          <p className="sub">
            {Object.keys(data.contracts).length} synthetic contracts (fictitious parties) × {Object.keys(data.rules).length} rules of Lei 14.133 ·{" "}
            {n.samples} {n.samples === 1 ? "sample" : "samples"} per decision · local Qwen3-8B · labels are the planted ground truth
          </p>
        </div>
        <p className="notice">Test bench on synthetic contracts. Not legal advice.</p>
      </header>

      <Summary summary={data.summary} levels={levels} />

      <div className="layout">
        <aside className="picker">
          <input type="search" placeholder="Contract or rule (e.g. 007, foro)" value={search} onChange={(e) => setSearch(e.target.value)} />
          <Toggle levels={levels} level={level} onChange={setMode} label="Condition the list is filtered on" />
          <div className="filters">
            {FILTERS.map((f) => (
              <button key={f.key} className={f.key === filter ? "chip on" : "chip"} onClick={() => setFilter(f.key)}>
                {f.label}
              </button>
            ))}
          </div>
          <p className="count">
            {visible.length} decisions · {lower(level)}
          </p>
          <ul>
            {visible.map((c) => (
              <li key={c.id}>
                <button className={c.id === current.id ? "row on" : "row"} onClick={() => go(c)}>
                  <span className="num">{c.doc.replace("synth-", "#")}</span>
                  <span className="codes">
                    {c.rule} · {VERDICTS[c.label]}
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
              {current.doc} · {current.rule}
              {position >= 0 && ` · ${position + 1} of ${visible.length}`}
            </span>
            <button onClick={() => step(1)}>Next →</button>
          </div>

          <Step n="1" title="Start: the contract and how it was parsed" note="A synthetic contract, parsed by Docling into sections. The same contract as a text PDF and as a degraded scan.">
            <div className="pair">
              {levels
                .filter((l) => contract.parses[l])
                .map((l) => (
                  <Parse key={l} name={LEVELS[l]} note={LEVEL_NOTES[l]} parse={contract.parses[l]} active={l === shown} />
                ))}
            </div>
          </Step>

          <Step n="2" title="The rule being checked" note="One rule of Lei 14.133/2021, given to the reviewer in Portuguese, as in the contracts.">
            <p>
              <span className="label">
                <b>{current.rule}</b> <span className="name">{rule.article}</span>
              </span>{" "}
              <span className="muted">
                {rule.kind === "limit"
                  ? "Limit rule: the model extracts the values and code applies the limit."
                  : "Presence rule: the model decides whether the clause is there."}
              </span>
            </p>
            <p className="question">{rule.check}</p>
            <blockquote className="quote">{rule.law}</blockquote>
          </Step>

          <Step
            n="3"
            title="Review: what the reviewer found"
            note={`The reviewer reads the contract through the MCP tools and must quote its evidence. ${run.samples.length} ${run.samples.length === 1 ? "run" : "independent runs"} of the same check; code then looks for each quote in the parsed text.`}
          >
            <Toggle levels={levels.filter((l) => current.conditions[l])} level={shown} onChange={setMode} label="Condition shown" />
            <div className="answers">
              {run.samples.map((s, i) => (
                <Sample key={i} sample={s} label={current.label} sections={parse.sections} />
              ))}
            </div>
            <Sections samples={run.samples} sections={parse.sections} />
          </Step>

          <Step
            n="4"
            title="Audit: a second agent tries to refute reported violations"
            note={`It searches the contract itself; a dispute counts only with a counter-quote found in the parsed text. Showing: ${lower(shown)}.`}
          >
            <Audits samples={run.samples} audited={data.summary[shown].audited} />
          </Step>

          <Step
            n="5"
            title="Uncertainty signals and the escalation decision"
            note={`The decision is the majority of the samples. It goes to a human if any check outside the model fires. Showing: ${lower(shown)}.`}
          >
            <Decision decision={run.decision} />
          </Step>

          <Step n="6" title="End: the outcome against the label" note="The label is what was planted when the contract was generated; the model never sees it.">
            <Result current={current} contract={contract} levels={levels} shown={shown} />
          </Step>
        </main>
      </div>
    </div>
  );
}

function Summary({ summary, levels }) {
  const tiles = levels.flatMap((l) => {
    const s = summary[l];
    const of = `of ${s.decisions} decisions`;
    return [
      [`${LEVELS[l]}s: majority verdict correct`, s.accuracy, `${of}, nothing escalated`],
      [`${LEVELS[l]}s: escalated to a human`, s.escalated, of],
      [`${LEVELS[l]}s: correct among those kept`, s.accuracy_kept, "of the decisions not escalated"],
    ];
  });
  return (
    <section className="summary" aria-label="Scores over all decisions">
      {tiles.map(([label, value, unit], i) => (
        <div className="tile" key={i}>
          <span className="tile-label">{label}</span>
          <span className="tile-value">{percent(value)}</span>
          <span className="tile-unit">{unit}</span>
        </div>
      ))}
    </section>
  );
}

function Toggle({ levels, level, onChange, label }) {
  if (levels.length < 2) return null;
  return (
    <div className="toggle" role="group" aria-label={label}>
      {levels.map((l) => (
        <button key={l} className={l === level ? "on" : ""} aria-pressed={l === level} onClick={() => onChange(l)}>
          {LEVELS[l]}
        </button>
      ))}
    </div>
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

function Parse({ name, note, parse, active }) {
  return (
    <article className={active ? "answer active" : "answer"}>
      <h3>
        {name} <span className="muted plain">· {note}</span>
      </h3>
      <dl className="facts">
        <dt>Pages</dt>
        <dd>{parse.pages}</dd>
        <dt>OCR</dt>
        <dd>{parse.ocr_used ? "used" : "not used (text layer)"}</dd>
        <dt>Lowest page OCR score</dt>
        <dd>{parse.ocr_score_min ?? "—"}</dd>
        <dt>Docling grade</dt>
        <dd>
          {parse.mean_grade} (lowest page: {parse.low_grade})
        </dd>
      </dl>
      <h3>{parse.sections.length} sections found</h3>
      <ol className="outline" start="0">
        {parse.sections.map((s) => (
          <li key={s.id}>
            {s.heading} <span className="muted">· {s.text.length} chars</span>
          </li>
        ))}
      </ol>
      <a href={parse.pdf} target="_blank" rel="noreferrer">
        Open the synthetic PDF
      </a>
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

function Sample({ sample, label, sections }) {
  const title = `Sample ${sample.sample + 1}`;
  if (sample.error) {
    return (
      <article className="answer">
        <h3>{title}</h3>
        <span className="labels">
          <span className="label miss">
            <span aria-hidden="true">✗ </span>no valid answer
          </span>
        </span>
        <p className="muted">{sample.error}</p>
      </article>
    );
  }
  const flag = flagged(sample.verdict);
  const hit = flag !== null && flag === (label === "violation");
  const section = sections[sample.section_id];
  return (
    <article className="answer">
      <h3>
        {title}
        {sample.redone && <span className="muted plain"> · re-run after a server error</span>}
      </h3>
      <span className="labels">
        <span className={hit ? "label hit" : "label miss"}>
          <span aria-hidden="true">{hit ? "✓ " : "✗ "}</span>
          <b>{VERDICTS[sample.verdict] ?? sample.verdict}</b>
          <span className="name"> {hit ? "matches the label" : flag === null ? "no usable answer" : "does not match the label"}</span>
        </span>
      </span>
      {sample.evidence ? <blockquote>{sample.evidence}</blockquote> : <p className="muted">No quote given.</p>}
      {sample.verbatim !== null && <Mark ok={sample.verbatim} yes="Quote found in the parsed text" no="Quote not found in the parsed text" />}
      <p className="muted">{section ? `From section ${section.id}, ${section.heading} (${pages(section.pages)}).` : "No section cited."}</p>
      {sample.facts && <Facts facts={sample.facts} />}
      <p>{sample.reason}</p>
      <p className="muted">
        Self-reported confidence {sample.confidence} · {sample.tool_calls} tool calls · {sample.tokens.toLocaleString("en")} tokens
      </p>
    </article>
  );
}

function Facts({ facts }) {
  const rows = Object.entries(facts).filter(([k]) => !["section_id", "evidence", "confidence"].includes(k));
  return (
    <dl className="facts">
      {rows.map(([k, v]) => (
        <FactRow key={k} name={k} value={v} />
      ))}
    </dl>
  );
}

function FactRow({ name, value }) {
  return (
    <>
      <dt>{name}</dt>
      <dd>{value === null || value === "" ? "—" : String(value)}</dd>
    </>
  );
}

function Sections({ samples, sections }) {
  const ids = [...new Set(samples.map((s) => s.section_id).filter((id) => sections[id]))].sort((a, b) => a - b);
  if (!ids.length) return null;
  return (
    <div className="sections">
      {ids.map((id) => (
        <details key={id}>
          <summary>
            Parsed text of section {id}: {sections[id].heading}
          </summary>
          <pre>{sections[id].text || "(no text under this heading)"}</pre>
        </details>
      ))}
    </div>
  );
}

function Audits({ samples, audited }) {
  const rows = samples.filter((s) => s.audit);
  if (!audited) return <p className="muted">No auditor run for this condition.</p>;
  if (!rows.length) return <p className="muted">No sample reported a violation, so the auditor did not run.</p>;
  return (
    <table className="findings">
      <thead>
        <tr>
          <th>Sample</th>
          <th>Auditor</th>
          <th>Counter-quote</th>
          <th>Reason given</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((s) => {
          const a = s.audit;
          return (
            <tr key={s.sample}>
              <td>{s.sample + 1}</td>
              <td>{a.error ? "no valid answer" : a.auditor_agrees ? "agrees: violation" : "disputes"}</td>
              <td>
                {a.counter_quote ? (
                  <>
                    “{a.counter_quote}” <Mark ok={a.counter_quote_verbatim} yes="found in the parsed text" no="not found, so it does not count" />
                  </>
                ) : (
                  "—"
                )}
              </td>
              <td>{a.error ?? a.auditor_reason}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function Decision({ decision: d }) {
  const votes = Math.round(d.agreement * d.samples);
  const values = {
    "samples disagree": d.flag === null ? "no valid sample" : `${votes} of ${d.samples} samples say “${flagText(d.flag)}”`,
    "quote not verbatim": d.verbatim === null ? "no quote to check" : d.verbatim ? "quote found in the parsed text" : "quote not found in the parsed text",
    "page quality < 0.9": d.page_quality === null ? "pages not OCR'd, or no section cited" : `lowest OCR score ${d.page_quality}`,
    "auditor disputes": d.disputed ? "at least one sample disputed with a counter-quote" : "no dispute",
  };
  return (
    <div>
      <table className="signals">
        <thead>
          <tr>
            <th>Escalate when</th>
            <th>Measured</th>
            <th>Result</th>
          </tr>
        </thead>
        <tbody>
          {SIGNALS.map(([key, name]) => (
            <tr key={key}>
              <th scope="row">{name}</th>
              <td>{values[key]}</td>
              <td>{d.signals[key] ? <strong>fires</strong> : "does not fire"}</td>
            </tr>
          ))}
          <tr>
            <th scope="row">No valid answer</th>
            <td>{d.flag === null ? "every sample failed or was unclear" : "there is a majority answer"}</td>
            <td>{d.flag === null ? <strong>fires</strong> : "does not fire"}</td>
          </tr>
          <tr className="unused">
            <th scope="row">Self-reported confidence</th>
            <td>mean {d.self_confidence.toFixed(2)}</td>
            <td>not used in the rule</td>
          </tr>
        </tbody>
      </table>
      <p className={d.escalated ? "verdict warn" : "verdict ok"}>
        {d.escalated ? "Escalated to a human" : "Not escalated: the agent keeps this decision"}
        <span className="muted"> · majority answer: {flagText(d.flag)}</span>
      </p>
    </div>
  );
}

function Result({ current, contract, levels, shown }) {
  const rows = levels.filter((l) => current.conditions[l]);
  const [tone, , text] = outcome(current.conditions[shown].decision);
  const planted = contract.planted.length ? contract.planted.join(", ") : "none";
  return (
    <div>
      <p>
        Label for this rule: <span className="label"><b>{VERDICTS[current.label]}</b></span>{" "}
        <span className="muted">
          · violations planted in this contract: {planted}
          {contract.hard.length > 0 && ` · compliant variants that look suspicious: ${contract.hard.join(", ")}`}
        </span>
      </p>
      <table className="result">
        <thead>
          <tr>
            <th>Condition</th>
            <th>Sample verdicts</th>
            <th>Majority answer</th>
            <th>Against the label</th>
            <th>Escalated</th>
            <th>Outcome</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((l) => {
            const { decision: d, samples } = current.conditions[l];
            const [, mark, label] = outcome(d);
            return (
              <tr key={l} className={l === shown ? "shown" : ""}>
                <th scope="row">{LEVELS[l]}</th>
                <td>{samples.map((s) => (s.error ? "no answer" : VERDICTS[s.verdict] ?? s.verdict)).join(", ")}</td>
                <td>{flagText(d.flag)}</td>
                <td>{d.correct ? "✓ correct" : "✗ wrong"}</td>
                <td>{d.escalated ? "yes" : "no"}</td>
                <td>
                  <span aria-hidden="true">{mark}</span> {label}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className={`takeaway ${tone}`}>
        {LEVELS[shown]}: {text.toLowerCase()}.
        {current.label !== "violation" && " “Compliant” and “not applicable” both count as nothing to flag."}
      </p>
    </div>
  );
}
