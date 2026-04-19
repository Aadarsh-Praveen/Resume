// Analytics page with charts
const { useState: useStateA, useMemo: useMemoA, useEffect: useEffectA } = React;

const LineChart = ({ labels, seriesA, seriesB, labelA, labelB }) => {
  if (!labels || labels.length < 2) return (
    <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--text-3)', fontSize: 13 }}>
      Not enough data yet — run the agent a few times to see trends.
    </div>
  );
  const W = 560, H = 220, P = { t: 20, r: 16, b: 28, l: 36 };
  const max = Math.max(...seriesA, ...seriesB, 1) * 1.15;
  const step = (W - P.l - P.r) / (labels.length - 1);
  const y = v => H - P.b - (v / max) * (H - P.t - P.b);
  const path = (s) => s.map((v, i) => `${i === 0 ? 'M' : 'L'} ${P.l + i * step} ${y(v)}`).join(' ');
  const area = (s) => path(s) + ` L ${P.l + (s.length-1) * step} ${H - P.b} L ${P.l} ${H - P.b} Z`;
  const gridY = [0, 0.25, 0.5, 0.75, 1].map(f => {
    const v = Math.round(max * f);
    return { v, y: y(v) };
  });
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block' }}>
      <defs>
        <linearGradient id="gradA" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.22" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="gradB" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="var(--success)" stopOpacity="0.18" />
          <stop offset="100%" stopColor="var(--success)" stopOpacity="0" />
        </linearGradient>
      </defs>
      {gridY.map((g, i) => (
        <g key={i}>
          <line x1={P.l} x2={W - P.r} y1={g.y} y2={g.y} stroke="var(--border)" strokeDasharray="3 3" />
          <text x={P.l - 8} y={g.y + 4} fontSize="10" textAnchor="end" fill="var(--text-3)">{g.v}</text>
        </g>
      ))}
      {labels.map((l, i) => (
        <text key={l} x={P.l + i * step} y={H - 8} fontSize="10" textAnchor="middle" fill="var(--text-3)">{l}</text>
      ))}
      <path d={area(seriesB)} fill="url(#gradB)" />
      <path d={path(seriesB)} fill="none" stroke="var(--success)" strokeWidth="2" />
      <path d={area(seriesA)} fill="url(#gradA)" />
      <path d={path(seriesA)} fill="none" stroke="var(--accent)" strokeWidth="2" />
      {seriesA.map((v, i) => <circle key={'a'+i} cx={P.l + i * step} cy={y(v)} r="3" fill="var(--surface)" stroke="var(--accent)" strokeWidth="2" />)}
      {seriesB.map((v, i) => <circle key={'b'+i} cx={P.l + i * step} cy={y(v)} r="3" fill="var(--surface)" stroke="var(--success)" strokeWidth="2" />)}
    </svg>
  );
};

const BarChart = ({ data, color='var(--accent)' }) => {
  if (!data || data.every(d => d.value === 0)) return (
    <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--text-3)', fontSize: 13 }}>
      No ATS scores yet.
    </div>
  );
  const W = 420, H = 200, P = { t: 12, r: 12, b: 28, l: 28 };
  const max = Math.max(...data.map(d => d.value), 1) * 1.15;
  const bw = (W - P.l - P.r) / data.length;
  const y = v => H - P.b - (v / max) * (H - P.t - P.b);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block' }}>
      {[0, 0.5, 1].map((f, i) => (
        <line key={i} x1={P.l} x2={W - P.r}
          y1={H - P.b - f * (H - P.t - P.b)}
          y2={H - P.b - f * (H - P.t - P.b)}
          stroke="var(--border)" strokeDasharray="3 3" />
      ))}
      {data.map((d, i) => {
        const x = P.l + i * bw + 6;
        const yy = y(d.value);
        return (
          <g key={d.label}>
            <rect x={x} y={yy} width={bw - 12} height={H - P.b - yy} rx="4" fill={color} opacity="0.9" />
            <text x={x + (bw - 12)/2} y={H - 10} fontSize="10" textAnchor="middle" fill="var(--text-3)">{d.label}</text>
            <text x={x + (bw - 12)/2} y={yy - 6} fontSize="11" textAnchor="middle" fill="var(--text-2)" fontWeight="500">{d.value}</text>
          </g>
        );
      })}
    </svg>
  );
};

const DonutChart = ({ data }) => {
  if (!data || data.length === 0 || data.every(d => d.value === 0)) return (
    <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--text-3)', fontSize: 13 }}>
      No application data yet.
    </div>
  );
  const S = 200, cx = S/2, cy = S/2, r = 72, rw = 20;
  const total = data.reduce((s, d) => s + d.value, 0);
  const colors = ['var(--accent)', '#10b981', '#f59e0b', '#06b6d4', '#94a3b8'];
  let angle = -Math.PI / 2;
  const arcs = data.map((d, i) => {
    const a0 = angle;
    const a1 = angle + (d.value / total) * Math.PI * 2;
    angle = a1;
    const large = a1 - a0 > Math.PI ? 1 : 0;
    const p = (a, rad) => [cx + Math.cos(a) * rad, cy + Math.sin(a) * rad];
    const [x0, y0] = p(a0, r);
    const [x1, y1] = p(a1, r);
    const [x2, y2] = p(a1, r - rw);
    const [x3, y3] = p(a0, r - rw);
    return {
      d: `M ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1} L ${x2} ${y2} A ${r - rw} ${r - rw} 0 ${large} 0 ${x3} ${y3} Z`,
      color: colors[i % colors.length],
      label: d.label, value: d.value
    };
  });
  return (
    <div style={{ display: 'flex', gap: 20, alignItems: 'center' }}>
      <svg viewBox={`0 0 ${S} ${S}`} width="180" height="180">
        {arcs.map((a, i) => <path key={i} d={a.d} fill={a.color} />)}
        <text x={cx} y={cy - 4} textAnchor="middle" fontSize="22" fontWeight="600" fill="var(--text)">{total}</text>
        <text x={cx} y={cy + 14} textAnchor="middle" fontSize="11" fill="var(--text-3)">applications</text>
      </svg>
      <div style={{ flex: 1 }}>
        {arcs.map((a, i) => (
          <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0', fontSize: 13, borderBottom: '1px solid var(--border)' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              <i style={{ display: 'inline-block', width: 9, height: 9, borderRadius: 2, background: a.color }}></i>
              {a.label}
            </span>
            <span style={{ color: 'var(--text-3)', fontVariantNumeric: 'tabular-nums' }}>{a.value} · {Math.round(a.value/total*100)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
};

const AnalyticsView = () => {
  const [weekly,  setWeekly]  = useStateA(null);
  const [ats,     setAts]     = useStateA([]);
  const [funnel,  setFunnel]  = useStateA([]);
  const [portals, setPortals] = useStateA([]);
  const [loading, setLoading] = useStateA(true);

  useEffectA(() => {
    const api = window.__API__;
    setLoading(true);
    Promise.all([api.weekly(), api.ats(), api.funnel(), api.portals()])
      .then(([w, a, f, p]) => {
        setWeekly(w);
        setAts(a);
        setFunnel(f);
        setPortals(p);
      })
      .catch(console.warn)
      .finally(() => setLoading(false));
  }, []);

  const weekLabels    = weekly ? weekly.weekLabels    : [];
  const appliedSeries = weekly ? weekly.appliedSeries : [];
  const preparedSeries = weekly ? weekly.preparedSeries : [];
  const totalApplied  = appliedSeries.reduce((s, v) => s + v, 0);
  const totalPrep     = preparedSeries.reduce((s, v) => s + v, 0);
  const avgAts = (() => {
    if (!ats || ats.length === 0) return 0;
    const total = ats.reduce((s, b) => s + b.value, 0);
    if (total === 0) return 0;
    const midpoints = { '< 60': 55, '60–69': 65, '70–79': 75, '80–89': 85, '90+': 93 };
    const weighted = ats.reduce((s, b) => s + (midpoints[b.label] || 75) * b.value, 0);
    return Math.round(weighted / total);
  })();

  return (
    <div data-screen-label="Analytics">
      <div className="analytics-head">
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 600, letterSpacing: '-0.02em', margin: '0 0 4px' }}>Analytics</h1>
          <p style={{ margin: 0, color: 'var(--text-2)', fontSize: 13.5 }}>How your apply agent is performing across portals and roles.</p>
        </div>
      </div>

      <div className="an-kpi-grid">
        <div className="card kpi">
          <div className="card-title">Applications submitted</div>
          <div className="kpi-val">{totalApplied}</div>
          <div className="kpi-sub">last 8 weeks</div>
        </div>
        <div className="card kpi">
          <div className="card-title">Resumes prepared</div>
          <div className="kpi-val">{totalPrep}</div>
          <div className="kpi-sub">last 8 weeks</div>
        </div>
        <div className="card kpi">
          <div className="card-title">Avg ATS score</div>
          <div className="kpi-val">{avgAts || '—'}</div>
          <div className="kpi-sub">across tailored resumes</div>
        </div>
        <div className="card kpi">
          <div className="card-title">Sources active</div>
          <div className="kpi-val">{portals.length}</div>
          <div className="kpi-sub">job portals with results</div>
        </div>
      </div>

      <div className="an-row an-row-2">
        <div className="card chart-card">
          <div className="chart-head">
            <div>
              <h3>Submissions over time</h3>
              <p className="sub">Applied vs. prepared · last 8 weeks</p>
            </div>
            <div className="legend">
              <span><i style={{ background: 'var(--accent)' }}></i>Applied</span>
              <span><i style={{ background: 'var(--success)' }}></i>Prepared</span>
            </div>
          </div>
          <LineChart labels={weekLabels} seriesA={appliedSeries} seriesB={preparedSeries} />
        </div>
        <div className="card chart-card">
          <div className="chart-head">
            <div>
              <h3>ATS score distribution</h3>
              <p className="sub">Across {totalApplied + totalPrep} tailored resumes</p>
            </div>
          </div>
          <BarChart data={ats} />
        </div>
      </div>

      <div className="an-row an-row-3">
        <div className="card chart-card">
          <div className="chart-head">
            <div>
              <h3>Application funnel</h3>
              <p className="sub">From discovery to application</p>
            </div>
          </div>
          {funnel.length === 0 || funnel[0].value === 0 ? (
            <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--text-3)', fontSize: 13 }}>
              No data yet.
            </div>
          ) : funnel.map((s, i) => {
            const pct = (s.value / funnel[0].value) * 100;
            return (
              <div key={i} className="funnel-row">
                <div className="funnel-label">{s.label}</div>
                <div className="funnel-bar"><span style={{ width: `${pct}%` }}></span></div>
                <div className="funnel-val">{s.value}<small>{Math.round(pct)}%</small></div>
              </div>
            );
          })}
        </div>
        <div className="card chart-card">
          <div className="chart-head">
            <div>
              <h3>Portal mix</h3>
              <p className="sub">Where jobs were sourced from</p>
            </div>
          </div>
          <DonutChart data={portals} />
        </div>
      </div>
    </div>
  );
};

window.AnalyticsView = AnalyticsView;
