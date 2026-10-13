import { useEffect, useMemo, useState } from "react";

const ARM_NAMES = {
  zero_shot: "Photo only",
  retrieval: "Photo + 3 cases",
  shuffled: "Photo + 3 cases, wrong labels",
};

const FILTERS = [
  { key: "all", label: "All", test: () => true },
  { key: "changed", label: "Answer changed with wrong labels", test: (c) => answerChanged(c) },
  { key: "unverified", label: "Citation check failed", test: (c) => c.arms.retrieval?.explanation?.verified === false },
  { key: "exact", label: "Exact match", test: (c) => compare(c.arms.retrieval.labels, c.truth).exact },
  { key: "normal", label: "Normal eyes", test: (c) => c.truth.includes("normal") },
];

function compare(answer, truth) {
  const found = answer.filter((x) => truth.includes(x));
  const extra = answer.filter((x) => !truth.includes(x));
  const missed = truth.filter((x) => !answer.includes(x));
  return { found, extra, missed, exact: extra.length === 0 && missed.length === 0 };
}

function answerChanged(c) {
  const a = c.arms.retrieval?.labels;
  const b = c.arms.shuffled?.labels;
  return Boolean(a && b) && [...a].sort().join() !== [...b].sort().join();
}

function number(id) {
  return id.split("/")[1];
}

export default function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(() => decodeURIComponent(window.location.hash.slice(1)));
  const [mode, setMode] = useState("retrieval");
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetch("data.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`data.json: HTTP ${r.status}`))))
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  const visible = useMemo(() => {
    if (!data) return [];
    const keep = FILTERS.find((f) => f.key === filter).test;
    const q = search.trim().toLowerCase();
    return data.cases.filter((c) => keep(c) && (!q || number(c.id) === q || c.truth.some((t) => t.toLowerCase().includes(q))));
  }, [data, filter, search]);

  const current = data?.cases.find((c) => c.id === selected) ?? visible[0] ?? data?.cases[0];
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

  const hasShuffled = Boolean(current.arms.shuffled);
  const arm = current.arms[hasShuffled ? mode : "retrieval"];

  return (
    <div className="page">
      <header className="top">
        <div>
          <h1>Eye-scan RAG: one image, start to end</h1>
          <p className="sub">
            {data.cases.length} RFMiD {data.split} images · local Qwen3-VL-8B · labels shown are the dataset's, not a diagnosis
          </p>
        </div>
        <p className="notice">Research demo, not a medical device.</p>
      </header>

      <Summary summary={data.summary} />

      <div className="layout">
        <aside className="picker">
          <input type="search" placeholder="Image number or label (e.g. 205, DR)" value={search} onChange={(e) => setSearch(e.target.value)} />
          <div className="filters">
            {FILTERS.map((f) => (
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
                  <span className="num">#{number(c.id)}</span>
                  <span className="codes">{c.truth.join(" · ")}</span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <main className="steps">
          <div className="nav">
            <button onClick={() => step(-1)}>← Previous</button>
            <span>
              Image #{number(current.id)}
              {position >= 0 && ` · ${position + 1} of ${visible.length}`}
            </span>
            <button onClick={() => step(1)}>Next →</button>
          </div>

          <Step n="1" title="Start: the query photo" note="One retinal photo from the test split. The dataset labels are hidden from the model.">
            <div className="query">
              <img src={current.image} alt={`Retinal photo, test image ${number(current.id)}`} />
              <div>
                <h3>Dataset labels</h3>
                <Labels labels={current.truth} conditions={data.conditions} long />
              </div>
            </div>
          </Step>

          <Step n="2" title="Retrieve: the 3 most similar labelled cases" note="Training photos found by the hybrid index. The model sees each photo with its recorded labels.">
            {hasShuffled && (
              <div className="toggle" role="group" aria-label="Labels shown to the model">
                <button className={mode === "retrieval" ? "on" : ""} onClick={() => setMode("retrieval")}>
                  True labels
                </button>
                <button className={mode === "shuffled" ? "on" : ""} onClick={() => setMode("shuffled")}>
                  Wrong labels (same photos)
                </button>
              </div>
            )}
            <div className="cases">
              {arm.cases.map((k, i) => (
                <figure key={k.id} className={arm.cited_cases.includes(i + 1) ? "cited" : ""}>
                  <img src={k.image} alt={`Case ${i + 1}, training image ${number(k.id)}`} loading="lazy" />
                  <figcaption>
                    <strong>
                      Case {i + 1} <span className="muted">· train #{number(k.id)}</span>
                    </strong>
                    <Labels labels={k.labels} conditions={data.conditions} />
                    {k.true_labels && <span className="really">really: {k.true_labels.join(", ")}</span>}
                    {arm.cited_cases.includes(i + 1) && <span className="tag">cited by the model</span>}
                  </figcaption>
                </figure>
              ))}
            </div>
          </Step>

          <Step n="3" title="Diagnose: what the model answered" note="The same photo, three ways. ✓ is in the dataset labels, ✗ is not.">
            <div className="answers">
              {Object.keys(ARM_NAMES)
                .filter((a) => current.arms[a])
                .map((a) => (
                  <Answer key={a} name={ARM_NAMES[a]} arm={current.arms[a]} truth={current.truth} conditions={data.conditions} active={a === mode} />
                ))}
            </div>
          </Step>

          <Step
            n="4"
            title="Explain and check the citations"
            note={`A second call explains each label and cites cases; code then checks every cited case really carries that label. Showing: ${ARM_NAMES[hasShuffled ? mode : "retrieval"].toLowerCase()}.`}
          >
            <Explanation explanation={arm.explanation} conditions={data.conditions} />
          </Step>

          <Step n="5" title="End: how it turned out" note="Each answer against the dataset labels for this image.">
            <Result current={current} />
          </Step>
        </main>
      </div>
    </div>
  );
}

function Summary({ summary }) {
  const f1 = summary.macro_f1_frequent ?? {};
  const tiles = [
    ["Photo only", f1.vlm_zero_shot, "macro-F1"],
    ["Photo + 3 cases", f1.vlm_retrieval, "macro-F1"],
    ["Same cases, wrong labels", f1.vlm_shuffled, "macro-F1"],
    ["Plain kNN vote, no VLM", f1.knn_weighted, "macro-F1"],
    ["Citation check passes", summary.verified?.retrieval, "true labels", true],
    ["Citation check passes", summary.verified?.shuffled, "wrong labels", true],
  ].filter(([, v]) => v != null);
  if (!tiles.length) return null;
  return (
    <section className="summary" aria-label="Scores over all images">
      {tiles.map(([label, value, unit, percent], i) => (
        <div className="tile" key={i}>
          <span className="tile-label">{label}</span>
          <span className="tile-value">{percent ? `${(value * 100).toFixed(1)}%` : value.toFixed(3)}</span>
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

function Labels({ labels, conditions, long, truth }) {
  return (
    <span className="labels">
      {labels.map((code) => {
        const info = conditions[code];
        const hit = truth ? truth.includes(code) : null;
        return (
          <span key={code} className={hit === null ? "label" : hit ? "label hit" : "label miss"} title={info ? `${info.name}: ${info.description}` : code}>
            {hit !== null && <span aria-hidden="true">{hit ? "✓ " : "✗ "}</span>}
            <b>{code}</b>
            {(long || truth) && info && <span className="name"> {info.name}</span>}
            {hit !== null && <span className="sr">{hit ? " (in the dataset labels)" : " (not in the dataset labels)"}</span>}
          </span>
        );
      })}
    </span>
  );
}

function Answer({ name, arm, truth, conditions, active }) {
  const c = compare(arm.labels, truth);
  return (
    <article className={active ? "answer active" : "answer"}>
      <h3>{name}</h3>
      <Labels labels={arm.labels} conditions={conditions} truth={truth} />
      <blockquote>{arm.rationale}</blockquote>
      <p className="muted">
        {arm.cases.length === 0 ? "No cases shown." : arm.cited_cases.length ? `Cites case ${arm.cited_cases.join(", ")}.` : "Cites no case."} {c.found.length} of{" "}
        {truth.length} dataset labels found
        {c.extra.length > 0 && `, ${c.extra.length} extra`}.
      </p>
    </article>
  );
}

function Explanation({ explanation, conditions }) {
  if (!explanation) return <p className="muted">No explanation run for this image.</p>;
  const retried = explanation.attempts > 1;
  return (
    <div>
      <p className={explanation.verified ? "verdict ok" : "verdict bad"}>
        <span aria-hidden="true">{explanation.verified ? "✓" : "✗"}</span> {explanation.verified ? "Citations verified" : "Citations not verified"}
        <span className="muted">
          {" "}
          · {explanation.attempts} {explanation.attempts === 1 ? "attempt" : "attempts"}
        </span>
      </p>
      <table className="findings">
        <thead>
          <tr>
            <th>Label</th>
            <th>Based on</th>
            <th>Cited cases</th>
            <th>Reason given</th>
          </tr>
        </thead>
        <tbody>
          {explanation.findings.map((f, i) => (
            <tr key={i}>
              <td>
                <Labels labels={[f.label]} conditions={conditions} />
              </td>
              <td>{f.source === "both" ? "photo and cases" : f.source === "image" ? "photo" : "cases"}</td>
              <td>{f.cases.length ? f.cases.join(", ") : "—"}</td>
              <td>{f.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {explanation.problems.length > 0 && <Problems title="Still wrong after the retries" items={explanation.problems} />}
      {retried && explanation.first_problems.length > 0 && <Problems title="What the check rejected on the first attempt" items={explanation.first_problems} />}
    </div>
  );
}

function Problems({ title, items }) {
  return (
    <div className="problems">
      <h3>{title}</h3>
      <ul>
        {items.map((p, i) => (
          <li key={i}>{p}</li>
        ))}
      </ul>
    </div>
  );
}

function Result({ current }) {
  const arms = Object.keys(ARM_NAMES).filter((a) => current.arms[a]);
  const shuffled = current.arms.shuffled;
  return (
    <div>
      <table className="result">
        <thead>
          <tr>
            <th>Run</th>
            <th>Answer</th>
            <th>Found</th>
            <th>Missed</th>
            <th>Extra</th>
            <th>Citation check</th>
          </tr>
        </thead>
        <tbody>
          {arms.map((a) => {
            const c = compare(current.arms[a].labels, current.truth);
            const e = current.arms[a].explanation;
            return (
              <tr key={a}>
                <th scope="row">{ARM_NAMES[a]}</th>
                <td>{current.arms[a].labels.join(", ")}</td>
                <td>{c.found.join(", ") || "—"}</td>
                <td>{c.missed.join(", ") || "—"}</td>
                <td>{c.extra.join(", ") || "—"}</td>
                <td>{e ? (e.verified ? "✓ passed" : "✗ failed") : "not run"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {shuffled && (
        <p className="takeaway">
          {answerChanged(current)
            ? "The answer changed when only the case labels changed: the model followed the text next to the photos."
            : "The answer stayed the same when the case labels were swapped for wrong ones."}
          {shuffled.explanation?.verified && compare(shuffled.labels, current.truth).extra.length > 0 && " The citation check still passed on the wrong-label run: it checks consistency with the labels shown, not correctness."}
        </p>
      )}
    </div>
  );
}
