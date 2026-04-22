// Recruiters page
const { useState: useStateR, useMemo: useMemoR, useEffect: useEffectR } = React;

const SentPill = ({ sent, onToggle }) => (
  <button
    className={`pill ${sent ? 'success' : 'warn'}`}
    onClick={onToggle}
    style={{ border: 'none', cursor: 'pointer', background: 'transparent', padding: 0, font: 'inherit' }}
    title={sent ? 'Click to mark as not sent' : 'Click to mark as sent'}
  >
    <span className="pill-dot"></span>{sent ? 'Sent' : 'Not sent'}
  </button>
);
const YesNoReplied = ({ yes, onToggle }) => (
  <button
    className={`pill ${yes ? 'success' : ''}`}
    onClick={onToggle}
    style={{ border: 'none', cursor: 'pointer', background: 'transparent', padding: 0, font: 'inherit' }}
    title={yes ? 'Click to mark as not replied' : 'Click to mark as replied'}
  >
    <span className="pill-dot"></span>{yes ? 'Yes' : 'No'}
  </button>
);
const ViaPill = ({ via }) => {
  if (!via || via === '—') return <span style={{ color: 'var(--text-3)' }}>—</span>;
  const cls = via === 'Both' ? 'accent' : via === 'LinkedIn' ? 'info' : 'success';
  return <span className={`pill ${cls}`}><span className="pill-dot"></span>{via}</span>;
};

const SortHeaderR = ({ label, k, sort, setSort }) => {
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

const RecruitersView = () => {
  const [rows, setRows]         = useStateR([]);
  const [stats, setStats]       = useStateR({ tracked: 0, companies: 0, emails_sent: 0, linkedin_sent: 0, replied: 0 });
  const [loading, setLoading]   = useStateR(true);
  const [q, setQ]               = useStateR('');
  const [company, setCompany]   = useStateR('all');
  const [replyFilter, setReplyFilter] = useStateR('all');
  const [sort, setSort]         = useStateR({ key: 'name', dir: 'asc' });

  useEffectR(() => {
    window.__API__.recruiters()
      .then(({ rows: r, stats: s }) => { setRows(r); setStats(s); })
      .catch(console.warn)
      .finally(() => setLoading(false));
  }, []);

  // fieldMap: DB field name → row key
  const _fieldMap = { email_sent: 'cold', linkedin_sent: 'linkedinMsg', replied: 'replied' };

  const handleToggle = async (dbId, field) => {
    const rowKey = _fieldMap[field];
    // Optimistic update
    setRows(prev => prev.map(r => r.dbId === dbId ? { ...r, [rowKey]: !r[rowKey] } : r));
    try {
      const res = await fetch(
        `${window.__API__.base}/api/recruiters/${dbId}/toggle/${field}`,
        { method: 'POST' }
      );
      if (!res.ok) throw new Error('failed');
      const data = await res.json();
      setRows(prev => prev.map(r => r.dbId === dbId ? { ...r, [rowKey]: !!data.value } : r));
    } catch {
      // Revert
      setRows(prev => prev.map(r => r.dbId === dbId ? { ...r, [rowKey]: !r[rowKey] } : r));
    }
  };

  const companies = useMemoR(() => ['all', ...Array.from(new Set(rows.map(r => r.company)))], [rows]);

  const filtered = useMemoR(() => {
    let out = rows;
    if (q) {
      const lc = q.toLowerCase();
      out = out.filter(r =>
        r.name.toLowerCase().includes(lc) ||
        r.company.toLowerCase().includes(lc) ||
        r.recruiterTitle.toLowerCase().includes(lc) ||
        (r.email && r.email.toLowerCase().includes(lc))
      );
    }
    if (company !== 'all') out = out.filter(r => r.company === company);
    if (replyFilter === 'replied') out = out.filter(r => r.replied);
    if (replyFilter === 'pending') out = out.filter(r => !r.replied);
    const { key, dir } = sort;
    const mult = dir === 'asc' ? 1 : -1;
    out = [...out].sort((a, b) => String(a[key]).localeCompare(String(b[key])) * mult);
    return out;
  }, [rows, q, company, replyFilter, sort]);

  return (
    <div data-screen-label="Recruiters">
      <div className="page-head">
        <div>
          <h1>Recruiters</h1>
          <p>Every recruiter the agent reached out to, plus who replied back.</p>
        </div>
      </div>

      <div className="kpi-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        <div className="card kpi">
          <div className="card-title">Recruiters tracked</div>
          <div className="kpi-val">{stats.tracked}</div>
          <div className="kpi-sub">across {stats.companies} companies</div>
        </div>
        <div className="card kpi">
          <div className="card-title">Cold emails sent</div>
          <div className="kpi-val">{stats.emails_sent}</div>
          <div className="kpi-sub">{stats.tracked > 0 ? Math.round(stats.emails_sent / stats.tracked * 100) : 0}% coverage</div>
        </div>
        <div className="card kpi">
          <div className="card-title">LinkedIn messages</div>
          <div className="kpi-val">{stats.linkedin_sent}</div>
          <div className="kpi-sub">{stats.tracked > 0 ? Math.round(stats.linkedin_sent / stats.tracked * 100) : 0}% coverage</div>
        </div>
        <div className="card kpi">
          <div className="card-title">Replies received</div>
          <div className="kpi-val">{stats.replied}</div>
          <div className="kpi-sub">
            {stats.tracked > 0 ? (
              <span className="kpi-delta up">▲ {Math.round(stats.replied / stats.tracked * 100)}%</span>
            ) : '—'} reply rate
          </div>
        </div>
      </div>

      <div className="toolbar">
        <div className="search">
          <Icon name="search" size={14} />
          <input placeholder="Search recruiter, company, email…" value={q} onChange={e => setQ(e.target.value)} />
        </div>
        <select className="sel" value={company} onChange={e => setCompany(e.target.value)}>
          {companies.map(c => <option key={c} value={c}>{c === 'all' ? 'All companies' : c}</option>)}
        </select>
        <select className="sel" value={replyFilter} onChange={e => setReplyFilter(e.target.value)}>
          <option value="all">All recruiters</option>
          <option value="replied">Replied</option>
          <option value="pending">Awaiting reply</option>
        </select>
        <div style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-3)' }}>
          Showing {filtered.length} of {rows.length}
        </div>
      </div>

      <div className="table-wrap">
        <div className="table-scroll">
          {rows.length === 0 ? (
            <div style={{ padding: '48px 20px', textAlign: 'center', color: 'var(--text-3)', fontSize: 13 }}>
              {loading ? 'Loading…' : 'No recruiters tracked yet — run the agent to find and email recruiters.'}
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <SortHeaderR label="Recruiter"        k="name"           sort={sort} setSort={setSort} />
                  <SortHeaderR label="Company"          k="company"        sort={sort} setSort={setSort} />
                  <SortHeaderR label="Recruiter Title"  k="recruiterTitle" sort={sort} setSort={setSort} />
                  <th>Email</th>
                  <th>LinkedIn</th>
                  <SortHeaderR label="Cold Email"       k="cold"           sort={sort} setSort={setSort} />
                  <SortHeaderR label="LinkedIn Message" k="linkedinMsg"    sort={sort} setSort={setSort} />
                  <SortHeaderR label="Replied"          k="replied"        sort={sort} setSort={setSort} />
                  <SortHeaderR label="Replied In"       k="repliedIn"      sort={sort} setSort={setSort} />
                </tr>
              </thead>
              <tbody>
                {filtered.map(r => {
                  const initials = r.name.split(' ').map(s => s[0]).filter(Boolean).slice(0, 2).join('');
                  return (
                    <tr key={r.id}>
                      <td>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10 }}>
                          <span className="avatar" style={{ width: 28, height: 28, fontSize: 11, borderRadius: 8 }}>{initials}</span>
                          <span style={{ fontWeight: 500 }}>{r.name}</span>
                        </span>
                      </td>
                      <td>{r.company}</td>
                      <td className="col-dim">{r.recruiterTitle}</td>
                      <td className="col-mono col-dim">{r.email !== '—' ? r.email : <span style={{ color: 'var(--text-3)' }}>—</span>}</td>
                      <td>
                        {r.linkedin !== '—' ? (
                          <a className="ext-link" href={`https://${r.linkedin}`} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}>
                            {r.linkedin.replace('linkedin.com/in/', '@')} <Icon name="external" size={11} />
                          </a>
                        ) : <span style={{ color: 'var(--text-3)' }}>—</span>}
                      </td>
                      <td><SentPill sent={r.cold}       onToggle={() => handleToggle(r.dbId, 'email_sent')} /></td>
                      <td><SentPill sent={r.linkedinMsg} onToggle={() => handleToggle(r.dbId, 'linkedin_sent')} /></td>
                      <td><YesNoReplied yes={r.replied}  onToggle={() => handleToggle(r.dbId, 'replied')} /></td>
                      <td><ViaPill via={r.repliedIn} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
};

window.RecruitersView = RecruitersView;
