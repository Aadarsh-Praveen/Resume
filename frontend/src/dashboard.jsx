// Dashboard page
const DashboardView = ({ profile, stats, activity, onNav }) => {
  const name     = profile ? profile.name     : '…';
  const role     = profile ? profile.role     : '';
  const email    = profile ? profile.email    : '';
  const location = profile ? profile.location : '';
  const phone    = profile ? profile.phone    : '';
  const initials = name.split(' ').map(s => s[0]).filter(Boolean).slice(0, 2).join('');

  const applied  = stats ? stats.applied  : 0;
  const pending  = stats ? stats.pending  : 0;
  const total    = stats ? stats.total    : 0;

  return (
    <div data-screen-label="Dashboard">
      <div className="page-head">
        <div>
          <h1>Welcome back, {name.split(' ')[0] || '…'}</h1>
          <p>Here's what your apply agent has been doing.</p>
        </div>
        <button className="btn btn-primary" onClick={() => onNav('tracker')}>
          Open Tracker <Icon name="chevron-right" size={14} />
        </button>
      </div>

      <div className="dash-hero">
        <div className="profile-card">
          <div className="profile-avatar">{initials || '?'}</div>
          <div className="profile-info" style={{ flex: 1 }}>
            <h2>{name}</h2>
            {role     && <p className="role">{role}</p>}
            <div className="profile-meta">
              {email    && <span><Icon name="mail"  size={13} /> {email}</span>}
              {location && <span><Icon name="map"   size={13} /> {location}</span>}
              {phone    && <span><Icon name="phone" size={13} /> {phone}</span>}
              {profile && profile.linkedin && (
                <span><Icon name="id" size={13} /> <a href={profile.linkedin} target="_blank" rel="noreferrer" style={{ color: 'inherit' }}>{profile.linkedin.replace('https://', '')}</a></span>
              )}
            </div>
          </div>
        </div>
        <div className="card session-card">
          <div className="card-title">Jobs in pipeline</div>
          <div className="session-clock" style={{ fontSize: 36, letterSpacing: '-0.03em' }}>{total}</div>
          <div className="session-sub">total discovered · {pending} awaiting review</div>
          <div className="session-progress"><span style={{ width: total > 0 ? `${Math.min(100, Math.round(applied / total * 100))}%` : '0%' }}></span></div>
          <div className="session-foot">
            <span>{applied} applied</span>
            <span>{total > 0 ? Math.round(applied / total * 100) : 0}% converted</span>
          </div>
        </div>
      </div>

      <div className="kpi-grid">
        <div className="card kpi">
          <div className="card-title">Applications submitted</div>
          <div className="kpi-val">{applied}</div>
          <div className="kpi-sub">jobs applied via agent</div>
        </div>
        <div className="card kpi">
          <div className="card-title">Resumes prepared</div>
          <div className="kpi-val">{pending}</div>
          <div className="kpi-sub">awaiting your review</div>
        </div>
        <div className="card kpi">
          <div className="card-title">Total discovered</div>
          <div className="kpi-val">{total}</div>
          <div className="kpi-sub">across all sources</div>
        </div>
        <div className="card kpi">
          <div className="card-title">Conversion rate</div>
          <div className="kpi-val">{total > 0 ? Math.round(applied / total * 100) : 0}%</div>
          <div className="kpi-sub">discovered → applied</div>
        </div>
      </div>

      <div className="dash-row-2">
        <div className="card">
          <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 14 }}>Recent activity</div>
              <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>Latest jobs the agent processed</div>
            </div>
            <button className="btn btn-ghost" onClick={() => onNav('tracker')} style={{ height: 32, padding: '0 12px', fontSize: 12 }}>View all</button>
          </div>
          <div className="timeline-list">
            {activity.length === 0 ? (
              <div style={{ padding: '32px 20px', textAlign: 'center', color: 'var(--text-3)', fontSize: 13 }}>
                No activity yet — run the agent to start collecting jobs.
              </div>
            ) : activity.map((a, i) => (
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
          <h3>Target roles</h3>
          {profile && profile.target_roles && profile.target_roles.length > 0 ? (
            profile.target_roles.map((role, i) => (
              <div key={i} className="skill-row">
                <span className="skill-name">{role}</span>
                <div className="skill-bar"><span style={{ width: '100%' }}></span></div>
              </div>
            ))
          ) : (
            <div style={{ color: 'var(--text-3)', fontSize: 13 }}>
              Set TARGET_ROLES in config.py
            </div>
          )}
          {profile && profile.years_experience > 0 && (
            <div style={{ marginTop: 18, padding: 12, background: 'var(--accent-soft)', borderRadius: 'var(--radius)', fontSize: 12.5, color: 'var(--accent-text)', display: 'flex', gap: 8, alignItems: 'flex-start' }}>
              <Icon name="sparkles" size={14} />
              <span>{profile.years_experience} years of experience · agent filters jobs accordingly.</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

window.DashboardView = DashboardView;
