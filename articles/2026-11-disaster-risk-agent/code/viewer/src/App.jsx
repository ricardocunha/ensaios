import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const SOURCE = { ana_level: "River level (ANA)", ana_rain: "Rain at the gauge (ANA)", inmet_rain: "Rain station (INMET)" };
const ROLE = { gauge: "own gauge", upstream: "upstream or neighbour gauge", rain: "rain in the catchment" };
const KIND = { first_alert: "first alert", own_gauge_silent: "own gauge silent" };
const MODES = { tool: "Tool output", "tool+audit_retry": "Tool output + audit retry", prompted: "Prompted output" };
const LANGS = { pt: "Portuguese (pt-BR)", en: "English" };
const PROBLEMS = {
  ungrounded_numbers: "Numbers not in the input",
  unknown_stations: "Station codes not in the input",
  unknown_places: "Places not in the input",
  silent_not_mentioned: "Silent gauges not mentioned",
  silent_field_mismatch: "Silent-gauge field differs from the input",
  wrong_level: "Risk level differs from the fused one",
};

const FILTERS = [
  { key: "all", label: "All hours", test: () => true },
  { key: "alert", label: "Hours with an alert text", test: (h) => Boolean(h.alert) },
  { key: "raised", label: "Attention or above", test: (h) => h.level !== "normal" },
  { key: "silent", label: "A gauge is silent", test: (h) => h.silent.length > 0 },
];

const ms = (t) => Date.parse(t);

function pct(p) {
  if (p < 0.001) return "<0.1%";
  if (p > 0.999) return ">99.9%";
  return `${(p * 100).toFixed(1)}%`;
}

function num(x, digits = 3) {
  return x == null ? "—" : String(Number(x.toPrecision(digits)));
}

function age(h) {
  return h == null ? "no reading in 72 h" : h === 0 ? "this hour" : `${num(h)} h old`;
}

function readHash() {
  const [place, t] = decodeURIComponent(window.location.hash.slice(1)).split("/");
  return { place, t };
}

export default function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(readHash);
  const [filter, setFilter] = useState("all");
  const [mode, setMode] = useState("tool");

  useEffect(() => {
    fetch("data.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`data.json: HTTP ${r.status}`))))
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  const place = data?.places.find((p) => p.name === selected.place) ?? data?.places[0];
  const keyHours = useMemo(() => (place ? place.hours.filter((h) => h.alert) : []), [place]);
  const visible = useMemo(() => (place ? place.hours.filter(FILTERS.find((f) => f.key === filter).test) : []), [place, filter]);
  const current = place?.hours.find((h) => h.t === selected.t) ?? keyHours[0] ?? place?.hours[0];
  const position = current ? visible.findIndex((h) => h.t === current.t) : -1;

  const go = (name, t) => {
    setSelected({ place: name, t });
    window.history.replaceState(null, "", `#${encodeURIComponent(name)}/${t ?? ""}`);
  };
  const step = (delta) => {
    if (!visible.length) return;
    const next = visible[position === -1 ? 0 : (position + delta + visible.length) % visible.length];
    go(place.name, next.t);
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

  const listRef = useRef(null);
  useEffect(() => {
    const list = listRef.current;
    const row = list?.querySelector(".row.on");
    if (row) list.scrollTop = row.offsetTop - list.offsetTop - list.clientHeight / 2;
  }, [current?.t, place?.name, filter]);

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

  const offset = data.utc_offset_h;
  const local = (t, day = true) => {
    const d = new Date(ms(t) + offset * 3600e3);
    const time = `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
    return day ? `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${time}` : time;
  };
  const event = data.summary.event[place.name] ?? {};
  const index = place.hours.indexOf(current);
  const total = place.hours.length;
  const pick = (h) => go(place.name, h.t);

  return (
    <div className="page">
      <header className="top">
        <div>
          <h1>Flood-risk replay: one place and hour, start to end</h1>
          <p className="sub">
            Rio Grande do Sul floods, April–May 2024 · {data.places.length} gauges × {total} hourly steps · times are local (UTC{offset})
          </p>
        </div>
        <p className="notice">A backtest of one 2024 event, not an operational warning system.</p>
      </header>

      <Summary summary={data.summary} />

      <div className="layout">
        <aside className="picker">
          <h3>Place</h3>
          <div className="places">
            {data.places.map((p) => (
              <button key={p.name} className={p.name === place.name ? "chip on" : "chip"} onClick={() => go(p.name, current.t)}>
                {p.name}
              </button>
            ))}
          </div>
          {keyHours.length > 0 && (
            <>
              <h3>Key hours with an alert text</h3>
              <div className="keys">
                {keyHours.map((h) => (
                  <HourRow key={h.t} h={h} on={h.t === current.t} label={`${local(h.t)} · ${KIND[h.alert.kind] ?? h.alert.kind}`} onClick={() => pick(h)} />
                ))}
              </div>
            </>
          )}
          <h3>Hour of the replay</h3>
          <div className="filters">
            {FILTERS.map((f) => (
              <button key={f.key} className={f.key === filter ? "chip on" : "chip"} onClick={() => setFilter(f.key)}>
                {f.label}
              </button>
            ))}
          </div>
          <p className="count">{visible.length} hours</p>
          <ul ref={listRef}>
            {visible.map((h) => (
              <li key={h.t}>
                <HourRow h={h} on={h.t === current.t} label={local(h.t)} onClick={() => pick(h)} />
              </li>
            ))}
          </ul>
        </aside>

        <main className="steps">
          <div className="nav">
            <button onClick={() => step(-1)}>← Previous</button>
            <span>
              {place.name} · {local(current.t)}
              {position >= 0 && ` · ${position + 1} of ${visible.length}`}
            </span>
            <button onClick={() => step(1)}>Next →</button>
          </div>

          <section className="step charts">
            <h2>{place.name}: fused probability over the replay</h2>
            <p className="muted">
              Probability that gauge {place.gauge} reaches its flood level ({place.flood_cm} cm) within 24 h. The line is fainter after the
              selected hour. Click the chart to select an hour.
            </p>
            <Chart
              hours={place.hours}
              get={(h) => h.p}
              yMax={1}
              ticks={[0, 1]}
              refs={data.levels.filter(([, lo]) => lo > 0).map(([name, lo]) => ({ y: lo, label: `${name} ${lo.toFixed(2)}` }))}
              fmt={(v, h) => `${pct(v)} · ${h.level}`}
              selected={index}
              cross={event.crossing}
              crossLabel={event.crossing && `flood level reached ${local(event.crossing)}`}
              onSelect={pick}
              local={local}
              offset={offset}
              height={230}
              name="Fused probability"
            />
            <h3>Gauge level, cm</h3>
            <Chart
              hours={place.hours}
              get={(h) => h.cm}
              yMax={Math.ceil(Math.max(place.flood_cm, ...place.hours.map((h) => h.cm ?? 0)) / 500) * 500}
              ticks={[0, Math.ceil(Math.max(place.flood_cm, ...place.hours.map((h) => h.cm ?? 0)) / 500) * 500]}
              refs={[{ y: place.flood_cm, label: `flood level ${place.flood_cm} cm` }]}
              fmt={(v) => (v == null ? "no reading this hour" : `${v} cm`)}
              selected={index}
              cross={event.crossing}
              onSelect={pick}
              local={local}
              offset={offset}
              height={150}
              name="Gauge level"
            />
            <p className="muted small">Last reading of each hour; gaps are hours with no reading.</p>
          </section>

          <Step n="1" title="Start: the readings known at this hour" note="Only readings that had arrived by this hour. Nothing is interpolated; each reading says how old it is.">
            <Readings place={place} hour={current} data={data} local={local} />
          </Step>

          <Step
            n="2"
            title="Signals: each reading as evidence"
            note="A rule turns each reading into a likelihood ratio (above 1 points to a flood, below 1 away from it). Its effect on the log-odds is weight × reliability × ln(LR)."
          >
            <Signals place={place} hour={current} />
          </Step>

          <Step n="3" title="Fuse: probability and risk level" note="Plain Python adds the effects to the prior's log-odds. The risk level follows from fixed thresholds on the probability.">
            <Fused place={place} hour={current} levels={data.levels} llm={data.summary.llm_fusion} />
          </Step>

          <Step
            n="4"
            title="Alert text and audit"
            note="A local LLM writes the text for civil defence from the fused state; it has no field for the probability or the level. Code then checks every number, station and silent gauge against the input."
          >
            {current.alert ? (
              <AlertTexts alert={current.alert} mode={mode} setMode={setMode} />
            ) : (
              <div>
                <p className="muted">No alert text was written for this hour. The agent ran on the key hours only{keyHours.length > 0 && "; for this place:"}</p>
                <div className="jump">
                  {keyHours.map((h) => (
                    <button key={h.t} className="chip" onClick={() => pick(h)}>
                      {local(h.t)} · {KIND[h.alert.kind] ?? h.alert.kind}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </Step>

          <Step n="5" title="End: what happened in the next 24 h (hindsight)" note="Readings from after this hour. The pipeline could not see them; they are used only to score it.">
            <Outcome place={place} hour={current} event={event} local={local} />
          </Step>
        </main>
      </div>
    </div>
  );
}

function Summary({ summary }) {
  const leads = Object.values(summary.event)
    .map((e) => e.lead_h)
    .filter((x) => x != null);
  const handset = Object.values(summary.event).filter((e) => e.handset_lead_h != null && e.handset_lead_h > 0).length;
  const places = Object.keys(summary.event).length;
  const fa = summary.false_alarms_test;
  const cal = summary.calibration_test;
  const audit = (lang) => {
    const rows = Object.values(summary.alert_audit?.[lang] ?? {});
    return rows.length ? [rows.reduce((a, r) => a + r.audit_ok, 0), rows.reduce((a, r) => a + r.runs, 0)] : null;
  };
  const pt = audit("pt");
  const en = audit("en");
  const brier = summary.llm_fusion?.brier.all;
  const tiles = [
    leads.length && ["Alert before the flood-level crossing", `${Math.min(...leads)}–${Math.max(...leads)} h`, `calibrated fusion, ${leads.length} places, 2024`],
    leads.length && ["Hand-set likelihood ratios: alert before the crossing", `${handset} of ${places}`, "places, 2024"],
    fa && ["False alarms, out of sample", fa.per_place_year.toFixed(2), `per place-year (${fa.false} false of ${fa.episodes} alert episodes)`],
    cal && ["Brier skill score, out of sample", cal.bss.toFixed(2), `vs climatology, ${cal.n.toLocaleString("en-US")} place-hours`],
    pt && ["Alert texts passing the audit, pt-BR", `${pt[0]} of ${pt[1]}`, "key hours × output modes"],
    en && ["Alert texts passing the audit, English", `${en[0]} of ${en[1]}`, "key hours × output modes"],
    brier && ["Brier score, Bayesian fusion", brier.fusion.toFixed(3), `${brier.n} pre-registered hours; lower is better`],
    brier && ["Brier score, LLM-only fusion", brier.llm_mean_p.toFixed(3), `same ${brier.n} hours, mean of 3 samples`],
  ].filter(Boolean);
  if (!tiles.length) return null;
  return (
    <section className="summary" aria-label="Scores from the run files">
      {tiles.map(([label, value, unit], i) => (
        <div className="tile" key={i}>
          <span className="tile-label">{label}</span>
          <span className="tile-value">{value}</span>
          <span className="tile-unit">{unit}</span>
        </div>
      ))}
    </section>
  );
}

function Level({ level }) {
  return (
    <span className={`lvl lvl-${level}`}>
      <i aria-hidden="true" />
      {level}
    </span>
  );
}

function HourRow({ h, on, label, onClick }) {
  return (
    <button className={on ? "row on" : "row"} onClick={onClick}>
      <span className="when">{label}</span>
      <span className="prob">{pct(h.p)}</span>
      <Level level={h.level} />
    </button>
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

function useWidth() {
  const ref = useRef(null);
  const [width, setWidth] = useState(900);
  useLayoutEffect(() => {
    const el = ref.current;
    setWidth(el.clientWidth);
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

function linePath(hours, get, x, y, end) {
  let d = "";
  let pen = false;
  for (let i = 0; i <= end; i++) {
    const v = get(hours[i]);
    if (v == null) {
      pen = false;
      continue;
    }
    d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
    pen = true;
  }
  return d;
}

function Chart({ hours, get, yMax, ticks, refs, fmt, selected, cross, crossLabel, onSelect, local, offset, height, name }) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState(null);
  const m = { l: 44, r: 12, t: 22, b: 24 };
  const n = hours.length;
  const plotW = Math.max(width - m.l - m.r, 10);
  const plotH = height - m.t - m.b;
  const x = (i) => m.l + (n > 1 ? i / (n - 1) : 0) * plotW;
  const y = (v) => m.t + (1 - v / yMax) * plotH;
  const first = ms(hours[0].t);
  const span = ms(hours[n - 1].t) - first || 1;
  const xCross = cross ? m.l + ((ms(cross) - first) / span) * plotW : null;
  const days = hours
    .map((h, i) => ({ i, d: new Date(ms(h.t) + offset * 3600e3) }))
    .filter(({ d }) => d.getUTCHours() === 0 && d.getUTCDate() % 5 === 0);
  const at = (e) => {
    const box = e.currentTarget.getBoundingClientRect();
    return Math.min(n - 1, Math.max(0, Math.round(((e.clientX - box.left - m.l) / plotW) * (n - 1))));
  };
  const value = get(hours[selected]);
  const shown = hover ?? null;

  return (
    <div className="chart" ref={ref}>
      <svg
        width={width}
        height={height}
        role="img"
        aria-label={`${name} over the replay; selected hour ${local(hours[selected].t)}`}
        onMouseMove={(e) => setHover(at(e))}
        onMouseLeave={() => setHover(null)}
        onClick={(e) => onSelect(hours[at(e)])}
      >
        {ticks.map((v) => (
          <g key={v}>
            <line className="grid" x1={m.l} x2={m.l + plotW} y1={y(v)} y2={y(v)} />
            <text className="axis" x={m.l - 6} y={y(v) + 4} textAnchor="end">
              {v}
            </text>
          </g>
        ))}
        {days.map(({ i, d }) => (
          <g key={i}>
            <line className="grid" x1={x(i)} x2={x(i)} y1={m.t + plotH} y2={m.t + plotH + 4} />
            <text className="axis" x={x(i)} y={height - 6} textAnchor="middle">
              {MONTHS[d.getUTCMonth()]} {d.getUTCDate()}
            </text>
          </g>
        ))}
        {refs.map((r) => (
          <g key={r.label}>
            <line className="ref" x1={m.l} x2={m.l + plotW} y1={y(r.y)} y2={y(r.y)} />
          </g>
        ))}
        <path className="series faint" d={linePath(hours, get, x, y, n - 1)} />
        <path className="series" d={linePath(hours, get, x, y, selected)} />
        {refs.map((r) => (
          <text key={r.label} className="axis halo" x={m.l + plotW - 4} y={y(r.y) - 4} textAnchor="end">
            {r.label}
          </text>
        ))}
        {xCross != null && (
          <g>
            <line className="cross" x1={xCross} x2={xCross} y1={m.t - 6} y2={m.t + plotH} />
            {crossLabel && (
              <text className="axis strong halo" x={xCross + (xCross > width * 0.6 ? -5 : 5)} y={m.t - 9} textAnchor={xCross > width * 0.6 ? "end" : "start"}>
                {crossLabel}
              </text>
            )}
          </g>
        )}
        <line className="pick" x1={x(selected)} x2={x(selected)} y1={m.t} y2={m.t + plotH} />
        {value != null && <circle className="dot" cx={x(selected)} cy={y(value)} r="5" />}
        {shown != null && <line className="hover" x1={x(shown)} x2={x(shown)} y1={m.t} y2={m.t + plotH} />}
        {shown != null && get(hours[shown]) != null && <circle className="dot small" cx={x(shown)} cy={y(get(hours[shown]))} r="3.5" />}
      </svg>
      {shown != null && (
        <div className="tip" style={x(shown) > width / 2 ? { right: width - x(shown) + 10 } : { left: x(shown) + 10 }}>
          <b>{local(hours[shown].t)}</b>
          <span>{fmt(get(hours[shown]), hours[shown])}</span>
        </div>
      )}
    </div>
  );
}

function rows(place, hour) {
  return hour.signals.map(([i, status, value, ageH, extra, handset, lr, reliability, effect, reason]) => ({
    ...place.signals[i],
    status,
    value,
    ageH,
    extra,
    handset,
    lr,
    reliability,
    effect,
    reason,
  }));
}

function reading(s) {
  if (s.value == null) return "—";
  if (s.source === "ana_level") return `${s.value} cm${s.extra != null ? ` · ${s.extra >= 0 ? "+" : ""}${s.extra} cm in 6 h` : ""}`;
  return `${s.value} mm in 24 h${s.extra != null ? ` · ${s.extra} mm in 72 h` : ""}`;
}

function Status({ status }) {
  const mark = { fresh: "●", stale: "◐", missing: "○" }[status];
  return (
    <span className={`status ${status}`}>
      <span aria-hidden="true">{mark}</span> {status}
    </span>
  );
}

function Readings({ place, hour, data, local }) {
  const all = rows(place, hour);
  if (!all.length) return <p className="muted">No signals file for this replay: run `make backtest`.</p>;
  const own = all.find((s) => s.role === "gauge");
  const station = data.stations[place.gauge] ?? {};
  const scale = Math.max(place.flood_cm * 1.5, own?.value ?? 0);
  const maps = data.maps.filter((p) => ms(p.visible_from) <= ms(hour.t));
  return (
    <div>
      {own && (
        <div className="gauge">
          <h3>
            {place.name} gauge {place.gauge}
          </h3>
          {own.value == null ? (
            <p>No level reading in the last 72 h.</p>
          ) : (
            <>
              <p>
                <b className="big">{own.value} cm</b> · {Math.round((own.value / place.flood_cm) * 100)}% of the {place.flood_cm} cm flood level ·{" "}
                {own.ageH === 0 ? "read this hour" : `reading ${num(own.ageH)} h old`}
              </p>
              <div className="meter" role="img" aria-label={`Level ${own.value} cm against a flood level of ${place.flood_cm} cm`}>
                <div className="fill" style={{ width: `${(own.value / scale) * 100}%` }} />
                <div className="mark" style={{ left: `${(place.flood_cm / scale) * 100}%` }}>
                  <span>flood level {place.flood_cm} cm</span>
                </div>
              </div>
            </>
          )}
          {station.p90 != null && (
            <p className="muted small">
              In the 2019–2024 record of this gauge: 90% of readings are below {station.p90} cm, 99% below {station.p99} cm.
            </p>
          )}
        </div>
      )}
      <table>
        <thead>
          <tr>
            <th>Station</th>
            <th>What it measures</th>
            <th>Latest reading</th>
            <th>Age</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {all.map((s) => (
            <tr key={s.source + s.station}>
              <th scope="row">
                {s.place} <span className="muted">{s.station}</span>
              </th>
              <td>
                {SOURCE[s.source]} <span className="muted">· {ROLE[s.role]}</span>
              </td>
              <td className="n">{reading(s)}</td>
              <td className="n">{age(s.ageH)}</td>
              <td>
                <Status status={s.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className={hour.silent.length ? "callout warn" : "callout"}>
        {hour.silent.length ? (
          <>
            <b>Silent gauges</b> (level reading older than {data.silent_after_h} h, or none):{" "}
            {hour.silent.map((code) => `${data.stations[code]?.place ?? ""} ${code}`).join(", ")}.
          </>
        ) : (
          "No silent gauge: every level gauge for this place has a reading from the last 3 h."
        )}
      </p>
      <p className="muted small">
        Copernicus EMS flood maps delivered by this hour:{" "}
        {maps.length
          ? maps.map((p) => `${p.place} (${p.ha} ha flooded, visible from ${local(p.visible_from)})`).join("; ")
          : "none"}
        . They confirm flooding after the fact and are not used in the probability.
      </p>
    </div>
  );
}

function Signals({ place, hour }) {
  const all = rows(place, hour).sort((a, b) => Math.abs(b.effect) - Math.abs(a.effect));
  if (!all.length) return <p className="muted">No signals file for this replay.</p>;
  const widest = Math.max(...all.map((s) => Math.abs(s.effect)), 0.01);
  return (
    <table className="signals">
      <thead>
        <tr>
          <th>Signal</th>
          <th>Rule that applied</th>
          <th className="n">Hand-set LR</th>
          <th className="n">Calibrated LR</th>
          <th className="n">Reliability</th>
          <th className="n">Weight</th>
          <th>Effect on log-odds</th>
        </tr>
      </thead>
      <tbody>
        {all.map((s) => (
          <tr key={s.source + s.station}>
            <th scope="row">
              {s.place} <span className="muted">{s.station}</span>
              <br />
              <span className="muted plain">{SOURCE[s.source]}</span>
            </th>
            <td>{s.reason}</td>
            <td className="n">{num(s.handset)}</td>
            <td className="n">{num(s.lr)}</td>
            <td className="n">{num(s.reliability)}</td>
            <td className="n">{num(s.weight)}</td>
            <td>
              <span className="effect">
                <span className="n">
                  {s.effect >= 0 ? "+" : "−"}
                  {Math.abs(s.effect).toFixed(2)}
                </span>
                <span className="bar">
                  <i className={s.effect >= 0 ? "up" : "down"} style={{ width: `${(Math.abs(s.effect) / widest) * 100}%` }} />
                </span>
                <span className="muted">{s.effect > 0 ? "raises" : s.effect < 0 ? "lowers" : "no effect"}</span>
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Track({ p, levels }) {
  return (
    <div className="track" role="img" aria-label={`Probability ${pct(p)} on a scale from 0 to 1`}>
      <div className="fill" style={{ width: `${p * 100}%` }} />
      {levels
        .filter(([, lo]) => lo > 0)
        .map(([name, lo]) => (
          <div className="mark" key={name} style={{ left: `${lo * 100}%` }}>
            <span>
              {name} {lo.toFixed(2)}
            </span>
          </div>
        ))}
    </div>
  );
}

function Fused({ place, hour, levels, llm }) {
  const priorLogOdds = Math.log(place.prior / (1 - place.prior));
  const samples = hour.llm ?? [];
  const mean = samples.reduce((a, s) => a + s.probability, 0) / (samples.length || 1);
  return (
    <div className="answers">
      <article className="answer active">
        <h3>Bayesian fusion (plain code)</h3>
        <p className="headline">
          <b className="big">{pct(hour.p)}</b> <Level level={hour.level} />
        </p>
        <Track p={hour.p} levels={levels} />
        <p className="muted">
          Prior {pct(place.prior)} (log-odds {priorLogOdds.toFixed(2)}) {hour.log_odds - priorLogOdds >= 0 ? "+" : "−"}{" "}
          {Math.abs(hour.log_odds - priorLogOdds).toFixed(2)} from the signals = log-odds {hour.log_odds.toFixed(2)}.
        </p>
      </article>
      {samples.length > 0 ? (
        <article className="answer">
          <h3>LLM-only fusion (same signals, {samples.length} samples)</h3>
          <p className="headline">
            <b className="big">{pct(mean)}</b> <span className="muted">mean of the samples</span>
          </p>
          <Track p={mean} levels={levels} />
          <ul className="samples">
            {samples.map((s) => (
              <li key={s.sample}>
                <b>{pct(s.probability)}</b> <Level level={s.level} />
                <blockquote>{s.reason}</blockquote>
              </li>
            ))}
          </ul>
        </article>
      ) : (
        llm && (
          <article className="answer">
            <h3>LLM-only fusion</h3>
            <p className="muted">Not run for this hour. The baseline ran on {llm.hours} pre-registered hours: every 3 h from 48 h before to 12 h after each place's crossing, plus quiet hours of 2023–2024.</p>
          </article>
        )
      )}
    </div>
  );
}

function AlertTexts({ alert, mode, setMode }) {
  const modes = Object.keys(MODES).filter((m) => Object.values(alert.texts).some((list) => list.some((t) => t.mode === m)));
  const active = modes.includes(mode) ? mode : modes[0];
  return (
    <div>
      <div className="toggle" role="group" aria-label="Output mode of the agent">
        {modes.map((m) => (
          <button key={m} className={m === active ? "on" : ""} onClick={() => setMode(m)}>
            {MODES[m]}
          </button>
        ))}
      </div>
      <div className="answers">
        {Object.keys(LANGS)
          .filter((lang) => alert.texts[lang])
          .map((lang) => {
            const text = alert.texts[lang].find((t) => t.mode === active);
            return (
              <article className="answer" key={lang} lang={lang === "pt" ? "pt-BR" : "en"}>
                <h3 lang="en">{LANGS[lang]}</h3>
                {text ? (
                  <>
                    <p className="alert-head">{text.headline}</p>
                    <blockquote>{text.explanation}</blockquote>
                    <Audit text={text} />
                  </>
                ) : (
                  <p className="muted">No text in this mode.</p>
                )}
              </article>
            );
          })}
      </div>
    </div>
  );
}

function Audit({ text }) {
  const problems = Object.entries(text.problems);
  return (
    <div lang="en">
      <p className={text.audit_ok ? "verdict ok" : "verdict bad"}>
        <span aria-hidden="true">{text.audit_ok ? "✓" : "✗"}</span> {text.audit_ok ? "Audit passed" : "Audit failed"}
        <span className="muted">
          {" "}
          · {text.numbers_checked} numbers checked
          {text.requests != null && ` · ${text.requests} model ${text.requests === 1 ? "request" : "requests"}`}
        </span>
      </p>
      {problems.length > 0 && (
        <ul className="plain-list">
          {problems.map(([kind, items]) => (
            <li key={kind}>
              {PROBLEMS[kind] ?? kind}: {items.map(String).join(", ")}
            </li>
          ))}
        </ul>
      )}
      <p className="muted small">The audit checks that numbers, stations and silent gauges come from the input, not that each number is attached to the right station.</p>
    </div>
  );
}

function Outcome({ place, hour, event, local }) {
  const next = hour.next_24h;
  const hoursTo = (t) => (ms(t) - ms(hour.t)) / 3600e3;
  const gap = event.crossing ? hoursTo(event.crossing) : null;
  return (
    <div>
      {!next ? (
        <p className="muted">No hourly dataset found: run `make dataset`.</p>
      ) : next.verdict === "reached" ? (
        <p className="verdict">
          <span aria-hidden="true">▲</span> The gauge was at or above its flood level within 24 h
          <span className="muted"> · first such reading {local(next.reached_at)}, {num(Math.max(hoursTo(next.reached_at), 0))} h after this hour</span>
        </p>
      ) : next.verdict === "not_reached" ? (
        <p className="verdict">
          <span aria-hidden="true">▽</span> The gauge stayed below its flood level in the next 24 h
        </p>
      ) : (
        <p className="verdict">
          <span aria-hidden="true">?</span> Unknown: the gauge sent too few readings in the next 24 h
        </p>
      )}
      <table className="result">
        <tbody>
          <tr>
            <th scope="row">Fusion at this hour</th>
            <td>
              {pct(hour.p)} <Level level={hour.level} />
            </td>
          </tr>
          {next && (
            <tr>
              <th scope="row">Hours with a level reading, next 24 h</th>
              <td>{next.hours_with_reading} of 24</td>
            </tr>
          )}
          {next?.max_cm != null && (
            <tr>
              <th scope="row">Highest reading, next 24 h</th>
              <td>
                {next.max_cm} cm ({Math.round((next.max_cm / place.flood_cm) * 100)}% of the {place.flood_cm} cm flood level) at {local(next.max_at)}
              </td>
            </tr>
          )}
          {event.crossing && (
            <tr>
              <th scope="row">First reading at flood level in the whole replay</th>
              <td>
                {local(event.crossing)} · {gap >= 0 ? `${num(gap)} h after this hour` : `${num(-gap)} h before this hour`}
              </td>
            </tr>
          )}
          {event.alert_onset && (
            <tr>
              <th scope="row">Fusion alert began</th>
              <td>
                {local(event.alert_onset)}
                {event.lead_h != null && ` · ${event.lead_h} h before the crossing`}
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <p className="muted small">Next-24 h rows use the last reading of each hour; the crossing time uses the 15-minute readings.</p>
    </div>
  );
}
