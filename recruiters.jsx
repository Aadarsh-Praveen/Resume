// Recruiters page
const { useState: useStateR, useMemo: useMemoR } = React;

const RECRUITER_ROWS = (() => {
  const companies = [
    { name: 'Monolith AI',       domain: 'monolith.ai' },
    { name: 'Helix Systems',     domain: 'helixsys.com' },
    { name: 'Cedar Analytics',   domain: 'cedar-an.com' },
    { name: 'Bluewave Robotics', domain: 'bluewave.ai' },
    { name: 'Copper Cloud',      domain: 'coppercloud.dev' },
    { name: 'Northwind Labs',    domain: 'northwind.io' },
    { name: 'Quartz Mobility',   domain: 'quartz.app' },
    { name: 'Lumen Commerce',    domain: 'lumencom.com' },
    { name: 'Obsidian Research', domain: 'obsidian-r.ai' },
    { name: 'Ember Security',    domain: 'ember-sec.io' },
    { name: 'Harbor Logistics',  domain: 'harborlog.com' },
    { name: 'Tessellate',        domain: 'tessellate.xyz' },
    { name: 'Halcyon Audio',     domain: 'halcyon.fm' },
    { name: 'Prism Education',   domain: 'prismed.org' }
  ];
  const firsts = ['Priya','Marcus','Elena','Darius','Sana','Jordan','Yuki','Noah','Amelia','Theo','Rina','Kwame','Ava','Oliver','Isha','Felix','Leila','Arjun'];
  const lasts = ['Patel','Rivera','Kowalski','Bennett','Okafor','Chen','Nakamura','Whitfield','Hartley','Lindgren','Saito','Mensah','Silva','Brooks','Kapoor','Müller','Haddad','Shah'];
  const titles = [
    'Technical Recruiter', 'Sr. Technical Recruiter', 'Talent Partner',
    'Head of Talent', 'Recruiting Lead', 'Sourcer, Design',
    'People Ops Lead', 'University Recruiter', 'Principal Recruiter'
  ];
  const positions = [
    'Senior Product Designer','Staff UX Designer','Design Systems Lead',
    'Sr. Frontend Engineer','Full-Stack Engineer','Design Engineer',
    'Product Manager, Growth','Principal Designer','Senior UX Researcher'
  ];
  const replyIn = ['—','LinkedIn','Mail','Both'];

  const out = [];
  for (let i = 0; i < 18; i++) {
    const co = companies[i % companies.length];
    const first = firsts[i % firsts.length];
    const last = lasts[(i * 3) % lasts.length];
    const pos = positions[i % positions.length];
    const title = titles[i % titles.length];
    const cold = i % 3 !== 2;           // mostly sent
    const linked = i % 4 !== 3;         // mostly sent
    const replied = (cold || linked) && (i % 3 === 0 || i % 5 === 0);
    const via = replied ? replyIn[1 + (i % 3)] : '—';
    const handle = (first + last).toLowerCase();
    out.push({
      id: `REC-${3000 + i}`,
      name: `${first} ${last}`,
      company: co.name,
      companyDomain: co.domain,
      recruiterTitle: title,
      position: pos,
      email: `${first.toLowerCase()}.${last.toLowerCase()}@${co.domain}`,
      linkedin: `linkedin.com/in/${handle}`,
      cold,
      linkedinMsg: linked,
      replied,
      repliedIn: via
    });
  }
  return out;
})();

const SentPill = ({ sent }) => (
  <span className={`pill ${sent ? 'success' : 'warn'}`}>
    <span className="pill-dot"></span>{sent ? 'Sent' : 'Not sent'}
  </span>
);
const YesNoReplied = ({ yes }) => (
  <span className={`pill ${yes ? 'success' : ''}`}>
    <span className="pill-dot"></span>{yes ? 'Yes' : 'No'}
  </span>
);
const ViaPill = ({ via }) => {
  if (via === '—') return <span style={{ color: 'var(--text-3)' }}>—</span>;
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
  const [q, setQ] = useStateR('');
  const [company, setCompany] = useStateR('all');
  const [replyFilter, setReplyFilter] = useStateR('all');
  const [sort, setSort] = useStateR({ key: 'name', dir: 'asc' });

  const companies = useMemoR(() => ['all', ...Array.from(new Set(RECRUITER_ROWS.map(r => r.company)))], []);

  const filtered = useMemoR(() => {
    let out = RECRUITER_ROWS;
    if (q) {
      const lc = q.toLowerCase();
      out = out.filter(r =>
        r.name.toLowerCase().includes(lc) ||
        r.company.toLowerCase().includes(lc) ||
        r.position.toLowerCase().includes(lc) ||
        r.recruiterTitle.toLowerCase().includes(lc) ||
        r.email.toLowerCase().includes(lc)
      );
    }
    if (company !== 'all') out = out.filter(r => r.company === company);
    if (replyFilter === 'replied') out = out.filter(r => r.replied);
    if (replyFilter === 'pending') out = out.filter(r => !r.replied);
    const { key, dir } = sort;
    const mult = dir === 'asc' ? 1 : -1;
    out = [...out].sort((a, b) => String(a[key]).localeCompare(String(b[key])) * mult);
    return out;
  }, [q, company, replyFilter, sort]);

  const totalReplies = RECRUITER_ROWS.filter(r => r.replied).length;
  const coldSent = RECRUITER_ROWS.filter(r => r.cold).length;
  const liSent = RECRUITER_ROWS.filter(r => r.linkedinMsg).length;

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
          <div className="kpi-val">{RECRUITER_ROWS.length}</div>
          <div className="kpi-sub">across {companies.length - 1} companies</div>
        </div>
        <div className="card kpi">
          <div className="card-title">Cold emails sent</div>
          <div className="kpi-val">{coldSent}</div>
          <div className="kpi-sub">{Math.round(coldSent/RECRUITER_ROWS.length*100)}% coverage</div>
        </div>
        <div className="card kpi">
          <div className="card-title">LinkedIn messages</div>
          <div className="kpi-val">{liSent}</div>
          <div className="kpi-sub">{Math.round(liSent/RECRUITER_ROWS.length*100)}% coverage</div>
        </div>
        <div className="card kpi">
          <div className="card-title">Replies received</div>
          <div className="kpi-val">{totalReplies}</div>
          <div className="kpi-sub"><span className="kpi-delta up">▲ {Math.round(totalReplies/RECRUITER_ROWS.length*100)}%</span> reply rate</div>
        </div>
      </div>

      <div className="toolbar">
        <div className="search">
          <Icon name="search" size={14} />
          <input placeholder="Search recruiter, company, role…" value={q} onChange={e => setQ(e.target.value)} />
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
          Showing {filtered.length} of {RECRUITER_ROWS.length}
        </div>
      </div>

      <div className="table-wrap">
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <SortHeaderR label="Recruiter"        k="name"            sort={sort} setSort={setSort} />
                <SortHeaderR label="Company"          k="company"         sort={sort} setSort={setSort} />
                <SortHeaderR label="Recruiter Title"  k="recruiterTitle"  sort={sort} setSort={setSort} />
                <SortHeaderR label="Applied Position" k="position"        sort={sort} setSort={setSort} />
                <th>Email</th>
                <th>LinkedIn</th>
                <SortHeaderR label="Cold Email"       k="cold"            sort={sort} setSort={setSort} />
                <SortHeaderR label="LinkedIn Message" k="linkedinMsg"     sort={sort} setSort={setSort} />
                <SortHeaderR label="Replied"          k="replied"         sort={sort} setSort={setSort} />
                <SortHeaderR label="Replied In"       k="repliedIn"       sort={sort} setSort={setSort} />
              </tr>
            </thead>
            <tbody>
              {filtered.map(r => {
                const initials = r.name.split(' ').map(s => s[0]).slice(0,2).join('');
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
                    <td className="truncate col-dim" title={r.position}>{r.position}</td>
                    <td className="col-mono col-dim">{r.email}</td>
                    <td>
                      <a className="ext-link" href={`https://${r.linkedin}`} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}>
                        {r.linkedin.replace('linkedin.com/in/', '@')} <Icon name="external" size={11} />
                      </a>
                    </td>
                    <td><SentPill sent={r.cold} /></td>
                    <td><SentPill sent={r.linkedinMsg} /></td>
                    <td><YesNoReplied yes={r.replied} /></td>
                    <td><ViaPill via={r.repliedIn} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

window.RecruitersView = RecruitersView;
