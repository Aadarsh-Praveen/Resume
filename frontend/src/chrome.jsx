// App shell: sidebar + topbar
const Sidebar = ({ page, onNav, collapsed, onLogout, profile }) => {
  const items = [
    { key: 'dashboard', label: 'Dashboard', icon: 'dashboard' },
    { key: 'tracker',   label: 'Application Tracker', icon: 'tracker' },
    { key: 'recruiters', label: 'Recruiters', icon: 'user' },
    { key: 'analytics', label: 'Analytics', icon: 'analytics' },
  ];
  const initials = profile.name.split(' ').map(s => s[0]).slice(0,2).join('');
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-brand-mark">A</div>
        <span className="sidebar-brand-text">Applyflow</span>
      </div>
      <div className="sidebar-section-label">Workspace</div>
      {items.map(it => (
        <button key={it.key}
          className={`nav-item ${page === it.key ? 'active' : ''}`}
          onClick={() => onNav(it.key)}>
          <Icon name={it.icon} size={16} />
          <span className="nav-label">{it.label}</span>
        </button>
      ))}
      <div className="sidebar-section-label">Account</div>
      <button className="nav-item" onClick={onLogout}>
        <Icon name="logout" size={16} />
        <span className="nav-label">Sign out</span>
      </button>
      <div className="sidebar-foot">
        <div className="user-card">
          <div className="avatar">{initials}</div>
          <div className="user-card-text">
            <div className="user-card-name">{profile.name}</div>
            <div className="user-card-mail">{profile.email}</div>
          </div>
        </div>
      </div>
    </aside>
  );
};

const Topbar = ({ page, onToggleSidebar, theme, onToggleTheme }) => {
  const titles = {
    dashboard: 'Dashboard',
    tracker: 'Application Tracker',
    recruiters: 'Recruiters',
    analytics: 'Analytics'
  };
  return (
    <div className="topbar">
      <div className="topbar-left">
        <button className="icon-btn" onClick={onToggleSidebar} aria-label="Toggle sidebar">
          <Icon name="menu" size={16} />
        </button>
        <span className="page-title">{titles[page]}</span>
        <span className="crumb-sep">/</span>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>Workspace · Morgan</span>
      </div>
      <div className="topbar-right">
        <button className="icon-btn" onClick={onToggleTheme} aria-label="Toggle theme">
          <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={16} />
        </button>
        <button className="icon-btn" aria-label="Notifications"><Icon name="bell" size={16} /></button>
      </div>
    </div>
  );
};

window.Sidebar = Sidebar;
window.Topbar = Topbar;
