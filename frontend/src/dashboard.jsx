// Dashboard page
const DashboardView = ({ profile, data, onNav }) => {
  const initials = profile.name.split(' ').map(s => s[0]).slice(0,2).join('');
  return (
    <div data-screen-label="Dashboard">
      <div className="page-head">
        <div>
          <h1>Welcome back, {profile.name.split(' ')[0]}</h1>
          <p>Here's what your apply agent has been doing.</p>
        </div>
        <button className="btn btn-primary" onClick={() => onNav('tracker')}>
          Open Tracker <Icon name="chevron-right" size={14} />
        </button>
      </div>

      <div className="dash-hero">
        <div className="profile-card">
          <div className="profile-avatar">{initials}</div>
          <div className="profile-info" style={{ flex: 1 }}>
            <h2>{profile.name}</h2>
            <p className="role">{profile.role}</p>
            <div className="profile-meta">
              <span><Icon name="mail" size={13} /> {profile.email}</span>
              <span><Icon name="map" size={13} /> {profile.location}</span>
              <span><Icon name="phone" size={13} /> {profile.phone}</span>
              <span><Icon name="id" size={13} /> {profile.agentId}</span>
              <span><Icon name="shield" size={13} /> {profile.plan} plan · joined {profile.joined}</span>
            </div>
          </div>
        </div>
        <div className="card session-card">
          <div className="card-title">Agent session</div>
          <div className="session-clock">02:47:18</div>
          <div className="session-sub">Running since 07:43 · scanning 4 portals</div>
          <div className="session-progress"><span style={{ width: '62%' }}></span></div>
          <div className="session-foot"><span>Next sweep in 9m</span><span>62% of daily budget</span></div>
        </div>
      </div>

      <div className="kpi-grid">
        <div className="card kpi">
          <div className="card-title">Applications submitted</div>
          <div className="kpi-val">132</div>
          <div className="kpi-sub"><span className="kpi-delta up">▲ 18%</span> vs. last week</div>
        </div>
        <div className="card kpi">
          <div className="card-title">Resumes prepared</div>
          <div className="kpi-val">186</div>
          <div className="kpi-sub"><span className="kpi-delta up">▲ 12%</span> vs. last week</div>
        </div>
        <div className="card kpi">
          <div className="card-title">Reply rate</div>
          <div className="kpi-val">28%</div>
          <div className="kpi-sub"><span className="kpi-delta up">▲ 3.2pp</span> vs. last week</div>
        </div>
        <div className="card kpi">
          <div className="card-title">Avg ATS score</div>
          <div className="kpi-val">84</div>
          <div className="kpi-sub"><span className="kpi-delta down">▼ 1</span> vs. last week</div>
        </div>
      </div>

      <div className="dash-row-2">
        <div className="card">
          <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 14 }}>Recent activity</div>
              <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>Last 24 hours</div>
            </div>
            <button className="btn btn-ghost" onClick={() => onNav('tracker')} style={{ height: 32, padding: '0 12px', fontSize: 12 }}>View all</button>
          </div>
          <div className="timeline-list">
            {data.activity.map((a, i) => (
              <div key={i} className="timeline-item">
                <div className={`timeline-ic ${a.type === 'applied' ? 'success' : a.type === 'reply' ? 'accent' : 'warn'}`}>
                  <Icon name={a.icon} size={14} />
                </div>
                <div>
                  <div className="timeline-title">{a.title}</div>
                  <div className="timeline-sub">{a.sub}</div>
                </div>
                <div className="timeline-time">{a.time}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="card skills-wrap">
          <h3>Skill coverage</h3>
          {profile.skills.map((s, i) => (
            <div key={i} className="skill-row">
              <span className="skill-name">{s.name}</span>
              <div className="skill-bar"><span style={{ width: `${s.v}%` }}></span></div>
              <span className="skill-val">{s.v}</span>
            </div>
          ))}
          <div style={{ marginTop: 18, padding: 12, background: 'var(--accent-soft)', borderRadius: 'var(--radius)', fontSize: 12.5, color: 'var(--accent-text)', display: 'flex', gap: 8, alignItems: 'flex-start' }}>
            <Icon name="sparkles" size={14} />
            <span>Agent suggests adding "Figma Advanced Prototyping" — 12 open roles match.</span>
          </div>
        </div>
      </div>
    </div>
  );
};

window.DashboardView = DashboardView;
