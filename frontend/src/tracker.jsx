// Tracker page — two tabs with tables
const { useState: useStateT, useMemo, useEffect: useEffectT } = React;

const ATSCell = ({ score }) => {
  const r = 9;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score));
  const off = c * (1 - pct / 100);
  const color = pct >= 85 ? 'var(--success)' : pct >= 70 ? 'var(--accent)' : pct >= 60 ? 'var(--warn)' : 'var(--danger)';
  return (
    <span className="ats">
      <svg className="ats-ring" viewBox="0 0 22 22">
        <circle className="bg" cx="11" cy="11" r={r} strokeWidth="2.5" fill="none" />
        <circle className="fg" cx="11" cy="11" r={r} strokeWidth="2.5" fill="none"
          stroke={color} strokeDasharray={c} strokeDashoffset={off} strokeLinecap="round" />
      </svg>
      <span>{score}</span>
    </span>
  );
};

const YesNoPill = ({ yes, labelYes='Sent', labelNo='Pending' }) => (
  <span className={`pill ${yes ? 'success' : 'warn'}`}>
    <span className="pill-dot"></span>{yes ? labelYes : labelNo}
  </span>
);

const StatusPill = ({ status }) => {
  const map = {
    'Applied': 'success',
    'Not Applied': 'warn',
    'Resume Ready': 'success',
    'Drafting': 'info'
  };
  return <span className={`pill ${map[status] || ''}`}><span className="pill-dot"></span>{status}</span>;
};

const AppStatusPill = ({ status }) => {
  const map = {
    'Accepted': 'success',
    'Interviewing': 'accent',
    'Rejected': 'danger',
    'Pending': ''
  };
  return <span className={`pill ${map[status] || ''}`}><span className="pill-dot"></span>{status}</span>;
};

const ManualAppliedPill = ({ applied }) => (
  <span className={`pill ${applied ? 'success' : 'warn'}`}>
    <span className="pill-dot"></span>{applied ? 'Applied' : 'Not Applied'}
  </span>
);

const SortHeader = ({ label, k, sort, setSort }) => {
  const active = sort.key === k;
  const dir = active ? sort.dir : null;
  return (
    <th className={`sortable ${active ? 'sorted' : ''}`}
        onClick={() => setSort({ key: k, dir: active && sort.dir === 'asc' ? 'desc' : 'asc' })}>
      {label}
      <span className="sort-ic">
        {dir === 'asc' ? <Icon name="arrow-up" size={11} stroke={2} />
         : dir === 'desc' ? <Icon name="arrow-down" size={11} stroke={2} />
         : <Icon name="sort" size={11} stroke={2} />}
      </span>
    </th>
  );
};

const Drawer = ({ row, kind, onClose, onDownload, onToggleReview }) => {
  if (!row) return null;
  return (
    <>
      <div className="drawer-backdrop" onClick={onClose}></div>
      <aside className="drawer" role="dialog">
        <div className="drawer-head">
          <div style={{ minWidth: 0 }}>
            <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
              <span className="pill accent">{row.portal}</span>
              <StatusPill status={row.status} />
            </div>
            <h3>{row.position}</h3>
            <p className="sub">{row.company} · {row.id}</p>
          </div>
          <button className="icon-btn" onClick={onClose}><Icon name="x" size={16} /></button>
        </div>
        <div className="drawer-body">
          <div className="drawer-meta-grid">
            <div>
              <div className="meta-k">Job posted</div>
              <div className="meta-v">{row.jobPosted}</div>
            </div>
            <div>
              <div className="meta-k">{kind === 'applied' ? 'Applied at' : 'Resume prepared'}</div>
              <div className="meta-v">{row.agentTime}</div>
            </div>
            <div>
              <div className="meta-k">ATS score</div>
              <div className="meta-v"><ATSCell score={row.ats} /></div>
            </div>
            <div>
              <div className="meta-k">Notification</div>
              <div className="meta-v"><YesNoPill yes={row.notified} /></div>
            </div>
            {row.email && (
              <div>
                <div className="meta-k">Contact email</div>
                <div className="meta-v mono">{row.email}</div>
              </div>
            )}
            <div>
              <div className="meta-k">Job description</div>
              <div className="meta-v">
                <a className="ext-link" href={row.jdUrl} target="_blank" rel="noreferrer">
                  Open posting <Icon name="external" size={12} />
                </a>
              </div>
            </div>
            {kind === 'applied' && (
              <div style={{ gridColumn: '1 / -1' }}>
                <div className="meta-k">Manual review</div>
                <div className="meta-v">
                  <button className={`check-pill ${row.manualReview ? 'done' : ''}`} onClick={() => onToggleReview(row)}>
                    <Icon name={row.manualReview ? 'check-circle' : 'check'} size={12} />
                    {row.manualReview ? 'Reviewed' : 'Mark as reviewed'}
                  </button>
                </div>
              </div>
            )}
          </div>

          {row.hasPdf && (
            <>
              <div className="drawer-section-title">Resume</div>
              <div style={{ display: 'flex', gap: 10, alignItems: 'center', padding: 12, background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
                <div style={{ width: 36, height: 44, borderRadius: 6, background: 'var(--accent-soft)', color: 'var(--accent-text)', display: 'grid', placeItems: 'center' }}>
                  <Icon name="file" size={18} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, fontFamily: 'var(--font-mono)' }}>{row.resume}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-3)' }}>tailored resume · PDF</div>
                </div>
                <button className="btn btn-ghost" onClick={() => onDownload(row)} style={{ height: 32, padding: '0 12px', fontSize: 12 }}>
                  <Icon name="download" size={13} /> Download
                </button>
              </div>
            </>
          )}
        </div>
        <div className="drawer-foot">
          <button className="btn btn-ghost" onClick={onClose}>Close</button>
          {row.hasPdf && (
            <button className="btn btn-primary" onClick={() => onDownload(row)}>
              <Icon name="download" size={13} /> Download resume
            </button>
          )}
        </div>
      </aside>
    </>
  );
};

const TrackerView = () => {
  const [tab, setTab]         = useStateT('applied');
  const [appliedRows, setAppliedRows] = useStateT([]);
  const [preparedRows, setPreparedRows] = useStateT([]);
  const [loading, setLoading] = useStateT(true);
  const [q, setQ]             = useStateT('');
  const [portal, setPortal]   = useStateT('all');
  const [status, setStatus]   = useStateT('all');
  const [sort, setSort]       = useStateT({ key: 'agentTimeRaw', dir: 'desc' });
  const [selected, setSelected] = useStateT(null);
  const [toast, setToast]     = useStateT('');
  const [appFilter, setAppFilter] = useStateT('all');

  useEffectT(() => {
    const api = window.__API__;
    setLoading(true);
    Promise.all([api.appliedRows(), api.preparedRows()])
      .then(([a, p]) => { setAppliedRows(a); setPreparedRows(p); })
      .catch(console.warn)
      .finally(() => setLoading(false));
  }, []);

  const rows = tab === 'applied' ? appliedRows : preparedRows;

  const portals  = useMemo(() => ['all', ...Array.from(new Set(rows.map(r => r.portal)))], [rows]);
  const statuses = tab === 'applied' ? ['all', 'Applied', 'Not Applied'] : ['all', 'Resume Ready', 'Drafting'];
  const appStatuses = ['all', 'Pending', 'Interviewing', 'Accepted', 'Rejected'];

  const filtered = useMemo(() => {
    let out = rows;
    if (q) {
      const lc = q.toLowerCase();
      out = out.filter(r =>
        r.company.toLowerCase().includes(lc) ||
        r.position.toLowerCase().includes(lc) ||
        r.portal.toLowerCase().includes(lc)
      );
    }
    if (portal !== 'all') out = out.filter(r => r.portal === portal);
    if (status !== 'all') out = out.filter(r => r.status === status);
    if (appFilter !== 'all') out = out.filter(r => r.appStatus === appFilter);
    const { key, dir } = sort;
    const mult = dir === 'asc' ? 1 : -1;
    out = [...out].sort((a, b) => {
      const av = a[key], bv = b[key];
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * mult;
      return String(av).localeCompare(String(bv)) * mult;
    });
    return out;
  }, [rows, q, portal, status, appFilter, sort]);

  const flash = (m) => { setToast(m); setTimeout(() => setToast(''), 1600); };

  const handleDownload = (row) => {
    if (row.hasPdf) {
      flash(`Opening ${row.resume}…`);
      window.open(`${window.__API__.base}/job/${row.dbId}/resume`, '_blank');
    } else {
      flash('No PDF available for this job.');
    }
  };

  const handleToggleReview = (row) => {
    const updater = rows.map(r => r.id === row.id ? { ...r, manualReview: !r.manualReview } : r);
    if (tab === 'applied') setAppliedRows(updater);
    else setPreparedRows(updater);
    if (selected && selected.id === row.id) setSelected({ ...row, manualReview: !row.manualReview });
  };

  const emptyMsg = loading
    ? 'Loading…'
    : tab === 'applied'
      ? 'No applied jobs yet — run the agent and approve some jobs.'
      : 'No resumes prepared yet — run the agent to get started.';

  return (
    <div data-screen-label="Tracker">
      <div className="page-head">
        <div>
          <h1>Application Tracker</h1>
          <p>Every job your agent touched — where it applied, and where it only prepared a resume.</p>
        </div>
      </div>

      <div className="tab-bar">
        <button className={tab === 'applied' ? 'active' : ''} onClick={() => setTab('applied')}>
          <Icon name="check-circle" size={13} />
          Applied by Agent
          <span className="tab-count">{appliedRows.length}</span>
        </button>
        <button className={tab === 'prepared' ? 'active' : ''} onClick={() => setTab('prepared')}>
          <Icon name="file" size={13} />
          Resume Prepared Only
          <span className="tab-count">{preparedRows.length}</span>
        </button>
      </div>

      <div className="toolbar">
        <div className="search">
          <Icon name="search" size={14} />
          <input placeholder="Search company, role, portal…" value={q} onChange={e => setQ(e.target.value)} />
        </div>
        <select className="sel" value={portal} onChange={e => setPortal(e.target.value)}>
          {portals.map(p => <option key={p} value={p}>{p === 'all' ? 'All portals' : p}</option>)}
        </select>
        <select className="sel" value={status} onChange={e => setStatus(e.target.value)}>
          {statuses.map(s => <option key={s} value={s}>{s === 'all' ? 'All statuses' : s}</option>)}
        </select>
        <select className="sel" value={appFilter} onChange={e => setAppFilter(e.target.value)}>
          {appStatuses.map(s => <option key={s} value={s}>{s === 'all' ? 'All outcomes' : s}</option>)}
        </select>
        <div style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-3)' }}>
          Showing {filtered.length} of {rows.length}
        </div>
      </div>

      <div className="table-wrap">
        <div className="table-scroll">
          {filtered.length === 0 ? (
            <div style={{ padding: '48px 20px', textAlign: 'center', color: 'var(--text-3)', fontSize: 13 }}>
              {emptyMsg}
            </div>
          ) : tab === 'applied' ? (
            <table className="data-table">
              <thead>
                <tr>
                  <SortHeader label="Portal"        k="portal"       sort={sort} setSort={setSort} />
                  <SortHeader label="Company"        k="company"      sort={sort} setSort={setSort} />
                  <SortHeader label="Position"       k="position"     sort={sort} setSort={setSort} />
                  <SortHeader label="Job Posted"     k="jobPostedRaw" sort={sort} setSort={setSort} />
                  <SortHeader label="Agent Applied"  k="agentTimeRaw" sort={sort} setSort={setSort} />
                  <SortHeader label="ATS"            k="ats"          sort={sort} setSort={setSort} />
                  <th>JD</th>
                  <th>Resume</th>
                  <th>Manual Review</th>
                  <SortHeader label="Status"         k="status"       sort={sort} setSort={setSort} />
                </tr>
              </thead>
              <tbody>
                {filtered.map(r => (
                  <tr key={r.id} onClick={() => setSelected(r)}>
                    <td><span className="pill">{r.portal}</span></td>
                    <td style={{ fontWeight: 500 }}>{r.company}</td>
                    <td className="truncate" title={r.position}>{r.position}</td>
                    <td className="col-dim">{r.jobPosted}</td>
                    <td className="col-dim col-mono">{r.agentTime}</td>
                    <td><ATSCell score={r.ats} /></td>
                    <td onClick={e => e.stopPropagation()}>
                      <a className="ext-link" href={r.jdUrl} target="_blank" rel="noreferrer">
                        Open <Icon name="external" size={11} />
                      </a>
                    </td>
                    <td onClick={e => e.stopPropagation()}>
                      {r.hasPdf ? (
                        <span className="resume-cell">
                          <span title={r.resume} style={{ maxWidth: 160, overflow:'hidden', textOverflow:'ellipsis', display:'inline-block', verticalAlign:'middle' }}>{r.resume}</span>
                          <button className="dl-btn" onClick={() => handleDownload(r)} aria-label={`Download ${r.resume}`}>
                            <Icon name="download" size={13} />
                          </button>
                        </span>
                      ) : <span style={{ color: 'var(--text-3)' }}>—</span>}
                    </td>
                    <td onClick={e => e.stopPropagation()}>
                      <button className={`check-pill ${r.manualReview ? 'done' : ''}`} onClick={() => handleToggleReview(r)}>
                        <Icon name={r.manualReview ? 'check-circle' : 'check'} size={12} />
                        {r.manualReview ? 'Done' : 'Pending'}
                      </button>
                    </td>
                    <td><StatusPill status={r.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <SortHeader label="Portal"          k="portal"       sort={sort} setSort={setSort} />
                  <SortHeader label="Company"          k="company"      sort={sort} setSort={setSort} />
                  <SortHeader label="Position"         k="position"     sort={sort} setSort={setSort} />
                  <SortHeader label="Job Posted"       k="jobPostedRaw" sort={sort} setSort={setSort} />
                  <SortHeader label="Resume Prepared"  k="agentTimeRaw" sort={sort} setSort={setSort} />
                  <SortHeader label="ATS"              k="ats"          sort={sort} setSort={setSort} />
                  <th>JD</th>
                  <th>Resume</th>
                  <SortHeader label="Status"           k="status"       sort={sort} setSort={setSort} />
                </tr>
              </thead>
              <tbody>
                {filtered.map(r => (
                  <tr key={r.id} onClick={() => setSelected(r)}>
                    <td><span className="pill">{r.portal}</span></td>
                    <td style={{ fontWeight: 500 }}>{r.company}</td>
                    <td className="truncate" title={r.position}>{r.position}</td>
                    <td className="col-dim">{r.jobPosted}</td>
                    <td className="col-dim col-mono">{r.agentTime}</td>
                    <td><ATSCell score={r.ats} /></td>
                    <td onClick={e => e.stopPropagation()}>
                      <a className="ext-link" href={r.jdUrl} target="_blank" rel="noreferrer">
                        Open <Icon name="external" size={11} />
                      </a>
                    </td>
                    <td onClick={e => e.stopPropagation()}>
                      {r.hasPdf ? (
                        <span className="resume-cell">
                          <span title={r.resume} style={{ maxWidth: 160, overflow:'hidden', textOverflow:'ellipsis', display:'inline-block', verticalAlign:'middle' }}>{r.resume}</span>
                          <button className="dl-btn" onClick={() => handleDownload(r)} aria-label={`Download ${r.resume}`}>
                            <Icon name="download" size={13} />
                          </button>
                        </span>
                      ) : <span style={{ color: 'var(--text-3)' }}>—</span>}
                    </td>
                    <td><StatusPill status={r.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <Drawer
        row={selected}
        kind={tab}
        onClose={() => setSelected(null)}
        onDownload={handleDownload}
        onToggleReview={handleToggleReview}
      />

      {toast && (
        <div style={{
          position: 'fixed', bottom: 24, left: '50%', transform: 'translateX(-50%)',
          background: 'var(--text)', color: 'var(--surface)',
          padding: '10px 16px', borderRadius: 10, fontSize: 13, boxShadow: 'var(--shadow-lg)', zIndex: 70
        }}>{toast}</div>
      )}
    </div>
  );
};

window.TrackerView = TrackerView;
