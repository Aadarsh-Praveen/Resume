// Analytics page with charts
const { useState: useStateA, useMemo: useMemoA } = React;

const LineChart = ({ labels, seriesA, seriesB, labelA, labelB }) => {
  const W = 560, H = 220, P = { t: 20, r: 16, b: 28, l: 36 };
  const max = Math.max(...seriesA, ...seriesB) * 1.15;
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
  const W = 420, H = 200, P = { t: 12, r: 12, b: 28, l: 28 };
  const max = Math.max(...data.map(d => d.value)) * 1.15;
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

const AnalyticsView = ({ data }) => {
  const [range, setRange] = useStateA('30d');
  const ranges = [
    { k: '7d', label: '7D' },
    { k: '30d', label: '30D' },
    { k: '90d', label: '90D' },
    { k: 'all', label: 'All' }
  ];
  // scale series gently per range for realism
  const scale = range === '7d' ? 0.35 : range === '30d' ? 1 : range === '90d' ? 2.4 : 3.6;
  const scaleArr = (a) => a.map(v => Math.round(v * scale));
  const seriesA = useMemoA(() => scaleArr(data.appliedSeries), [range]);
  const seriesB = useMemoA(() => scaleArr(data.preparedSeries), [range]);
  const totalApplied = seriesA.reduce((s,v)=>s+v,0);
  const totalPrep = seriesB.reduce((s,v)=>s+v,0);

  return (
    <div data-screen-label="Analytics">
      <div className="analytics-head">
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 600, letterSpacing: '-0.02em', margin: '0 0 4px' }}>Analytics</h1>
          <p style={{ margin: 0, color: 'var(--text-2)', fontSize: 13.5 }}>How your apply agent is performing across portals and roles.</p>
        </div>
        <div className="range-bar">
          {ranges.map(r => (
            <button key={r.k} className={range === r.k ? 'active' : ''} onClick={() => setRange(r.k)}>{r.label}</button>
          ))}
        </div>
      </div>

      <div className="an-kpi-grid">
        <div className="card kpi">
          <div className="card-title">Applications submitted</div>
          <div className="kpi-val">{totalApplied}</div>
          <div className="kpi-sub"><span className="kpi-delta up">▲ 22%</span> vs. prior period</div>
        </div>
        <div className="card kpi">
          <div className="card-title">Resumes prepared</div>
          <div className="kpi-val">{totalPrep}</div>
          <div className="kpi-sub"><span className="kpi-delta up">▲ 14%</span> vs. prior period</div>
        </div>
        <div className="card kpi">
          <div className="card-title">Avg ATS score</div>
          <div className="kpi-val">82</div>
          <div className="kpi-sub"><span className="kpi-delta up">▲ 3</span> vs. prior period</div>
        </div>
        <div className="card kpi">
          <div className="card-title">Recruiter reply rate</div>
          <div className="kpi-val">28.4%</div>
          <div className="kpi-sub"><span className="kpi-delta down">▼ 0.6pp</span> vs. prior period</div>
        </div>
      </div>

      <div className="an-row an-row-2">
        <div className="card chart-card">
          <div className="chart-head">
            <div>
              <h3>Submissions over time</h3>
              <p className="sub">Applied vs. prepared</p>
            </div>
            <div className="legend">
              <span><i style={{ background: 'var(--accent)' }}></i>Applied</span>
              <span><i style={{ background: 'var(--success)' }}></i>Prepared</span>
            </div>
          </div>
          <LineChart labels={data.weekLabels} seriesA={seriesA} seriesB={seriesB} />
        </div>
        <div className="card chart-card">
          <div className="chart-head">
            <div>
              <h3>ATS score distribution</h3>
              <p className="sub">Across {totalApplied + totalPrep} tailored resumes</p>
            </div>
          </div>
          <BarChart data={data.atsBuckets} />
        </div>
      </div>

      <div className="an-row an-row-3">
        <div className="card chart-card">
          <div className="chart-head">
            <div>
              <h3>Application funnel</h3>
              <p className="sub">From discovery to onsite</p>
            </div>
          </div>
          {data.funnelStages.map((s, i) => {
            const first = data.funnelStages[0].value;
            const pct = (s.value / first) * 100;
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
              <p className="sub">Where applications went</p>
            </div>
          </div>
          <DonutChart data={data.portalMix} />
        </div>
      </div>

      <div className="an-row">
        <div className="card chart-card">
          <div className="chart-head">
            <div>
              <h3>Top companies</h3>
              <p className="sub">Most active targets this period</p>
            </div>
          </div>
          {data.topCompanies.map((c, i) => (
            <div key={i} className="co-row">
              <span className="co-name">
                <span className="co-mark">{c.name.split(' ').map(w=>w[0]).slice(0,2).join('')}</span>
                {c.name}
              </span>
              <span style={{ display: 'inline-flex', gap: 18, alignItems:'center', fontVariantNumeric:'tabular-nums' }}>
                <span style={{ color:'var(--text-2)' }}>{c.applied} applied</span>
                <span className={`pill ${c.replies > 0 ? 'success' : ''}`}><span className="pill-dot"></span>{c.replies} replies</span>
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

window.AnalyticsView = AnalyticsView;
