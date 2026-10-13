import { useEffect, useMemo, useState } from "react";

const RUN_NAMES = {
  "cnh-teacher-deepseek": "Teacher: DeepSeek-V4-Pro",
  "student-base": "Student: Qwen3-8B, not tuned",
  "student-tuned": "Student: Qwen3-8B + LoRA",
};

const SOURCES = {
  noise: "the printed text with injected OCR noise",
  decoy: "the text printed on a non-CNH document",
  refusal: "the Reader's refusal",
  reader: "a Reader run",
};

// Tiles read the tables `make report` wrote to docs/RESULTS.md: [label, section, run, column, unit].
const TILES = [
  ["Reader zero-shot (Qwen3.5-9B), BID", "BID (real CNH templates)", "bid-qwen35_9b-zeroshot", "label acc", "label accuracy"],
  ["Reader LoRA round 1, BID", "BID (real CNH templates)", "bid-paddleocr_vl-lora-v1", "label acc", "label accuracy"],
  ["Reader LoRA round 3, BID", "BID (real CNH templates)", "bid-paddleocr_vl-lora-v3", "label acc", "label accuracy"],
  ["Reader LoRA round 3, synthetic test", "Synthetic test (round-1 design)", "paddleocr_vl-lora-v3", "label acc", "label accuracy"],
  ["Extractor Teacher", "Extractor (Stage 2)", "cnh-teacher-deepseek", "exact records", "records exactly right"],
  ["Extractor Student, not tuned", "Extractor (Stage 2)", "student-base", "exact records", "records exactly right"],
  ["Extractor Student + LoRA", "Extractor (Stage 2)", "student-tuned", "exact records", "records exactly right"],
];

const isCnh = (c) => c.kind === "cnh";
const runs = (c) => c.extractor?.runs ?? [];
const run = (c, name) => runs(c).find((r) => r.run === name);
const wrongGate = (c, r) => r.gate.is_cnh !== isCnh(c);
const wrongLabel = (r) => (r.labels ?? []).some((l) => !l.ok);

const FILTERS = [
  { key: "all", label: "All", test: () => true },
  { key: "cnh", label: "CNH", test: isCnh },
  { key: "non", label: "Non-CNH", test: (c) => !isCnh(c) },
  { key: "label", label: "Reader got a label wrong", needs: "readers", test: (c, r) => Boolean(r) && wrongLabel(r) },
  { key: "gate", label: "Gate verdict wrong", needs: "readers", test: (c, r) => Boolean(r) && wrongGate(c, r) },
  { key: "inexact", label: "Extractor not exact", needs: "extractor", test: (c) => runs(c).some((r) => !r.exact) },
  { key: "fixed", label: "Fixed by tuning", needs: "pair", test: (c) => run(c, "student-base")?.exact === false && run(c, "student-tuned")?.exact === true },
  { key: "broken", label: "Broken by tuning", needs: "pair", test: (c) => run(c, "student-base")?.exact === true && run(c, "student-tuned")?.exact === false },
];

function stem(id) {
  return id.slice(id.indexOf("/") + 1).replace(/_in$/, "");
}

function nameOnCard(c) {
  return /^NOME: (.+)$/m.exec(c.answer)?.[1] ?? "";
}

function reading(c, wanted) {
  return c.readers.find((r) => r.name === wanted) ?? c.readers[c.readers.length - 1];
}

function shown(value) {
  if (value == null || value === "") return "—";
  return Array.isArray(value) ? value.join(" / ") : String(value);
}

export default function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(() => decodeURIComponent(window.location.hash.slice(1)));
  const [setKey, setSetKey] = useState(() => decodeURIComponent(window.location.hash.slice(1)).split("/")[0]);
  const [readerName, setReaderName] = useState(null);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetch("data.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`data.json: HTTP ${r.status}`))))
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  const group = data?.sets.find((s) => s.key === setKey) ?? data?.sets[0];
  const inSet = useMemo(() => (data ? data.items.filter((c) => c.set === group.key) : []), [data, group]);
  const has = useMemo(
    () => ({
      readers: inSet.some((c) => c.readers.length > 0),
      extractor: inSet.some((c) => c.extractor),
      pair: inSet.some((c) => runs(c).length > 1),
    }),
    [inSet],
  );

  const visible = useMemo(() => {
    const keep = FILTERS.find((f) => f.key === filter).test;
    const q = search.trim().toLowerCase();
    return inSet.filter((c) => keep(c, reading(c, readerName)) && (!q || stem(c.id).toLowerCase().includes(q) || c.answer.toLowerCase().includes(q)));
  }, [inSet, filter, search, readerName]);

  const current = inSet.find((c) => c.id === selected) ?? visible[0] ?? inSet[0];
  const position = current ? visible.findIndex((c) => c.id === current.id) : -1;

  const go = (c) => {
    if (!c) return;
    setSelected(c.id);
    window.history.replaceState(null, "", `#${c.id}`);
  };
  const step = (delta) => go(visible[position === -1 ? 0 : (position + delta + visible.length) % visible.length]);
  const pickSet = (key) => {
    setSetKey(key);
    setFilter("all");
    go(data.items.find((c) => c.set === key));
  };

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

  const reader = reading(current, readerName);
  const extractor = current.extractor;
  let n = 0;

  return (
    <div className="page">
      <header className="top">
        <div>
          <h1>CNH pipeline: one image, start to end</h1>
          <p className="sub">
            {data.items.length} images with a Reader or Extractor run · Reader scores count CNHs only · the Extractor runs read a noised
            ground-truth Transcription, not a Reader's output
          </p>
        </div>
        <p className="notice">Synthetic and BID images only; no real person's document.</p>
      </header>

      <Summary summary={data.summary} />

      <div className="layout">
        <aside className="picker">
          <div className="filters" role="group" aria-label="Image set">
            {data.sets.map((s) => (
              <button key={s.key} className={s.key === group.key ? "chip on" : "chip"} onClick={() => pickSet(s.key)}>
                {s.name} ({s.count})
              </button>
            ))}
          </div>
          <input type="search" placeholder="File name or text on the card" value={search} onChange={(e) => setSearch(e.target.value)} />
          <div className="filters" role="group" aria-label="Filter">
            {FILTERS.filter((f) => !f.needs || has[f.needs]).map((f) => (
              <button key={f.key} className={f.key === filter ? "chip on" : "chip"} onClick={() => setFilter(f.key)}>
                {f.label}
              </button>
            ))}
          </div>
          <p className="count">{visible.length} images</p>
          <ul>
            {visible.map((c) => (
              <li key={c.id}>
                <button className={c.id === current.id ? "row on" : "row"} onClick={() => go(c)}>
                  <span className="num">{stem(c.id)}</span>
                  <span className="codes">{isCnh(c) ? nameOnCard(c) || "CNH" : "Non-CNH"}</span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <main className="steps">
          <div className="nav">
            <button onClick={() => step(-1)}>← Previous</button>
            <span>
              {stem(current.id)}
              {position >= 0 && ` · ${position + 1} of ${visible.length}`}
            </span>
            <button onClick={() => step(1)}>Next →</button>
          </div>

          <Step n={++n} title="Start: the image" note={`One image from the set "${group.name}". The ground truth is hidden from the models.`}>
            <Start current={current} />
          </Step>

          {reader && (
            <Step
              n={++n}
              title="Reader: the Transcription"
              note={
                "The vision model writes one LABEL: value line per printed field and corrects nothing." +
                (extractor ? " The Extractor runs below did not read this output." : "")
              }
            >
              <Reading current={current} reader={reader} onPick={setReaderName} />
            </Step>
          )}

          {extractor && (
            <Step
              n={++n}
              title="Extractor input: the Transcription it was given"
              note={`This run's input was ${SOURCES[extractor.source] ?? extractor.source}. The run file does not store it; it is rebuilt here with the run's seed.`}
            >
              <Given text={extractor.input} printed={current.answer} noised={extractor.source === "noise"} />
            </Step>
          )}

          <Step
            n={++n}
            title="CNH Gate: is this text a CNH?"
            note={`A text check before the Extractor: at least 2 of the ${data.gate_labels.length} labels only a CNH prints (${data.gate_labels.join(", ")}).`}
          >
            <Gate
              current={current}
              rows={[reader && [`Reader: ${reader.name}`, reader.gate], extractor && ["Extractor input", extractor.gate]].filter(Boolean)}
            />
          </Step>

          {extractor && (
            <Step
              n={++n}
              title="Extractor: tool calls and outcome"
              note="A text-only agent validates and corrects the values with tools, then submits a CNH Record or a Rejection."
            >
              <div className="answers">
                {extractor.runs.map((r) => (
                  <Extraction key={r.run} run={r} />
                ))}
              </div>
            </Step>
          )}

          {extractor ? (
            <Step n={++n} title="End: the record against the ground truth" note="Field by field. The ✓ and ✗ marks are the ones the run wrote, not recomputed here.">
              <Record current={current} fields={data.fields} />
            </Step>
          ) : (
            <Step n={++n} title="End: every Reader run on this image" note="The same image through each Reader run on disk, against the ground truth.">
              <Readers current={current} active={reader} />
            </Step>
          )}
        </main>
      </div>
    </div>
  );
}

function Summary({ summary }) {
  const tiles = TILES.map(([label, section, name, column, unit]) => {
    const row = summary[section]?.[name];
    return row?.[column] && { label, value: row[column], unit: `${unit}, ${row.CNHs ? `${row.CNHs} CNHs` : `${row.n} runs`}` };
  }).filter(Boolean);
  if (!tiles.length) return null;
  return (
    <section className="summary" aria-label="Scores over all images, from docs/RESULTS.md">
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

function Mark({ ok, yes, no }) {
  return (
    <span className={ok ? "mark ok" : "mark bad"}>
      <span aria-hidden="true">{ok ? "✓" : "✗"}</span> {ok ? yes : no}
    </span>
  );
}

function Start({ current }) {
  const tags = Object.entries(current.tags);
  return (
    <div className="query">
      <img src={current.image} alt={`Document image ${stem(current.id)}`} />
      <div className="grow">
        <h3>What it is</h3>
        <p className="labels">
          <span className="label">
            <b>{isCnh(current) ? "CNH" : "Non-CNH"}</b>
            <span className="name"> {isCnh(current) ? "should become a CNH Record" : "should be rejected"}</span>
          </span>
          {tags.map(([k, v]) => (
            <span className="label" key={k}>
              <span className="name">{k} </span>
              <b>{String(v)}</b>
            </span>
          ))}
        </p>
        <h3 className="gap">Ground truth: what is printed</h3>
        <pre className="text">{current.answer}</pre>
        {current.set === "bid" && isCnh(current) && (
          <p className="muted small">BID ground truth covers only the fields that can be matched to a label without ambiguity.</p>
        )}
      </div>
    </div>
  );
}

function Reading({ current, reader, onPick }) {
  return (
    <div>
      {current.readers.length > 1 && (
        <div className="filters gapb" role="group" aria-label="Reader run">
          {current.readers.map((r) => (
            <button key={r.run} className={r.run === reader.run ? "chip on" : "chip"} onClick={() => onPick(r.name)}>
              {r.name}
            </button>
          ))}
        </div>
      )}
      <p className="muted small">
        {reader.name} · {reader.seconds?.toFixed(1)} s{reader.refused && " · the Reader answered NÃO É CNH"}
      </p>
      <pre className="text">{reader.transcription}</pre>
      {reader.labels && (
        <table className="compare">
          <thead>
            <tr>
              <th>Label</th>
              <th>Printed</th>
              <th>Read</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {reader.labels.map((l) => (
              <tr key={l.label}>
                <th scope="row">{l.label}</th>
                <td>{shown(l.printed)}</td>
                <td>{l.read == null ? "line missing" : shown(l.read)}</td>
                <td>
                  <Mark ok={l.ok} yes="match" no="differs" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function Given({ text, printed, noised }) {
  const original = new Set(printed.split("\n"));
  const lines = text.split("\n");
  const changed = lines.filter((l) => !original.has(l)).length;
  const dropped = printed.split("\n").length - lines.filter((l) => l.includes(":")).length;
  return (
    <div>
      <pre className="text">
        {lines.map((l, i) => (
          <span key={i} className={noised && !original.has(l) ? "line changed" : "line"}>
            {noised && (original.has(l) ? "  " : "≠ ")}
            {l}
            {"\n"}
          </span>
        ))}
      </pre>
      {noised && (
        <p className="muted small">
          ≠ marks a line that differs from the printed text: {changed} of {lines.length}
          {dropped > 0 && `; ${dropped} printed ${dropped === 1 ? "line was" : "lines were"} left out`}.
        </p>
      )}
    </div>
  );
}

function Gate({ current, rows }) {
  return (
    <table>
      <thead>
        <tr>
          <th>Text</th>
          <th>CNH-only labels found</th>
          <th>Gate says</th>
          <th>Against the ground truth</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(([title, gate]) => (
          <tr key={title}>
            <th scope="row">{title}</th>
            <td>{gate.labels.length ? `${gate.labels.length}: ${gate.labels.join(", ")}` : "none"}</td>
            <td>{gate.is_cnh ? "CNH, passes" : "not a CNH, rejected"}</td>
            <td>
              <Mark ok={gate.is_cnh === isCnh(current)} yes="right" no={isCnh(current) ? "wrong: a CNH was rejected" : "wrong: a non-CNH passed"} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Extraction({ run }) {
  const rejected = run.outcome && "motivo" in run.outcome;
  return (
    <article className="answer">
      <h3>{RUN_NAMES[run.run] ?? run.run}</h3>
      <p>
        <b>{!run.outcome ? "Nothing submitted" : rejected ? "Rejection" : "CNH Record submitted"}</b>
        <span className="muted">
          {" "}
          · {run.tool_calls} tool calls in {run.model_calls} model calls · {run.input_tokens} tokens in, {run.output_tokens} out
        </span>
      </p>
      {rejected && <blockquote>{run.outcome.motivo}</blockquote>}
      {run.steps ? (
        <table className="calls">
          <thead>
            <tr>
              <th>Turn</th>
              <th>Tool</th>
              <th>Arguments</th>
              <th>Tool answer</th>
            </tr>
          </thead>
          <tbody>
            {run.steps.map((s, i) => (
              <tr key={i}>
                <td>{s.turn}</td>
                <th scope="row">{s.tool}</th>
                <td>
                  <code>{Object.entries(s.args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ")}</code>
                </td>
                <td>
                  <code>{s.result}</code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted">
          The run file stores only the number of tool calls. The calls themselves are in LangSmith, which this page does not read
          {run.role === "teacher" && "; only Golden Trajectories were pulled to disk"}.
        </p>
      )}
    </article>
  );
}

function Record({ current, fields }) {
  const { expected, runs: all } = current.extractor;
  const base = run(current, "student-base");
  const tuned = run(current, "student-tuned");
  return (
    <div>
      <table className="compare">
        <thead>
          <tr>
            <th>Field</th>
            <th>Expected</th>
            {all.map((r) => (
              <th key={r.run}>{RUN_NAMES[r.run] ?? r.run}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {expected &&
            fields.map((f) => (
              <tr key={f}>
                <th scope="row">{f}</th>
                <td>{shown(expected[f])}</td>
                {all.map((r) => (
                  <td key={r.run}>
                    {shown(r.outcome?.[f])} <Mark ok={r.fields[f]} yes="match" no="differs" />
                  </td>
                ))}
              </tr>
            ))}
          <tr>
            <th scope="row">Outcome</th>
            <td>{expected ? "CNH Record" : "Rejection"}</td>
            {all.map((r) => {
              const right = Object.values(r.fields).filter(Boolean).length;
              const what = !r.outcome ? "nothing submitted" : "motivo" in r.outcome ? "Rejection" : "CNH Record";
              return (
                <td key={r.run}>
                  {what}
                  {expected && `, ${right} of ${fields.length} fields`} <Mark ok={r.exact} yes="exactly right" no="not exact" />
                </td>
              );
            })}
          </tr>
        </tbody>
      </table>
      {base && tuned && base.exact !== tuned.exact && (
        <p className="takeaway">{tuned.exact ? "The tuned Student got this one exactly right; the untuned one did not." : "The untuned Student got this one exactly right; the tuned one did not."}</p>
      )}
      {current.set === "student" && !tuned && <p className="muted small">The tuned Student's run failed on this image and was not scored.</p>}
    </div>
  );
}

function Readers({ current, active }) {
  return (
    <table>
      <thead>
        <tr>
          <th>Reader run</th>
          <th>Labels read right</th>
          <th>Reader refused</th>
          <th>Gate</th>
          <th>Seconds</th>
        </tr>
      </thead>
      <tbody>
        {current.readers.map((r) => (
          <tr key={r.run} className={r.run === active.run ? "active" : ""}>
            <th scope="row">
              {r.name}
              {r.run === active.run && <span className="muted"> (shown above)</span>}
            </th>
            <td>{r.labels ? `${r.labels.filter((l) => l.ok).length} of ${r.labels.length}` : "not a CNH"}</td>
            <td>{r.refused ? "yes" : "no"}</td>
            <td>
              <Mark ok={!wrongGate(current, r)} yes={r.gate.is_cnh ? "passes" : "rejected"} no={r.gate.is_cnh ? "passes, should reject" : "rejected, is a CNH"} />
            </td>
            <td>{r.seconds?.toFixed(1)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
