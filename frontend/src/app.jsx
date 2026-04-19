// Root app — routing + state + data loading
const { useState: useStateApp, useEffect: useEffectApp } = React;

const App = () => {
  const defaults = window.__TWEAKS__ || { theme: 'light', sidebarCollapsed: false };
  const saved = (() => { try { return JSON.parse(localStorage.getItem('applyflow_state') || '{}'); } catch { return {}; } })();

  const [authed, setAuthed]                 = useStateApp(true); // local tool — no login needed
  const [page, setPage]                     = useStateApp(saved.page || 'dashboard');
  const [theme, setTheme]                   = useStateApp(saved.theme || defaults.theme);
  const [sidebarCollapsed, setSidebarCollapsed] = useStateApp(saved.sidebarCollapsed ?? defaults.sidebarCollapsed);
  const [tweaksVisible, setTweaksVisible]   = useStateApp(false);

  // Global data loaded once after login
  const [profile, setProfile] = useStateApp(null);
  const [stats, setStats]     = useStateApp({ total: 0, pending: 0, applied: 0, rejected: 0 });
  const [activity, setActivity] = useStateApp([]);

  // persist nav/theme
  useEffectApp(() => {
    localStorage.setItem('applyflow_state', JSON.stringify({ authed, page, theme, sidebarCollapsed }));
  }, [authed, page, theme, sidebarCollapsed]);

  useEffectApp(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  // Load profile + stats after login
  useEffectApp(() => {
    if (!authed) return;
    const api = window.__API__;
    api.profile().then(setProfile).catch(console.warn);
    api.stats().then(setStats).catch(console.warn);
    api.recentJobs(5).then(jobs => {
      setActivity(jobs.map(j => ({
        type: j.approval_status === 'applied' ? 'applied' : 'resume',
        title: j.approval_status === 'applied'
          ? `Applied to ${j.title}`
          : `Resume tailored for ${j.title}`,
        sub: [j.company, j.source, j.ats_score ? `ATS ${Math.round(j.ats_score)}` : null]
          .filter(Boolean).join(' · '),
        time: api.relTime(j.applied_at || j.created_at),
        icon: j.approval_status === 'applied' ? 'check' : 'file',
      })));
    }).catch(console.warn);
  }, [authed]);

  // Tweaks bridge
  useEffectApp(() => {
    const handler = (e) => {
      if (!e.data) return;
      if (e.data.type === '__activate_edit_mode')   setTweaksVisible(true);
      if (e.data.type === '__deactivate_edit_mode') setTweaksVisible(false);
    };
    window.addEventListener('message', handler);
    window.parent.postMessage({ type: '__edit_mode_available' }, '*');
    return () => window.removeEventListener('message', handler);
  }, []);

  const persistTweak = (edits) => {
    window.parent.postMessage({ type: '__edit_mode_set_keys', edits }, '*');
  };
  const updateTheme   = (t) => { setTheme(t);   persistTweak({ theme: t }); };
  const updateSidebar = (c) => { setSidebarCollapsed(c); persistTweak({ sidebarCollapsed: c }); };

  if (!authed) {
    return (
      <>
        <LoginView onLogin={() => { setAuthed(true); setPage('dashboard'); }} />
        <TweaksPanel
          theme={theme} setTheme={updateTheme}
          sidebarCollapsed={sidebarCollapsed} setSidebarCollapsed={updateSidebar}
          visible={tweaksVisible}
        />
      </>
    );
  }

  return (
    <div className={`app ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <Sidebar
        page={page}
        onNav={setPage}
        collapsed={sidebarCollapsed}
        onLogout={() => setAuthed(false)}
        profile={profile}
      />
      <main className="main">
        <Topbar
          page={page}
          onToggleSidebar={() => updateSidebar(!sidebarCollapsed)}
          theme={theme}
          onToggleTheme={() => updateTheme(theme === 'light' ? 'dark' : 'light')}
        />
        <div className="content">
          {page === 'dashboard'  && <DashboardView profile={profile} stats={stats} activity={activity} onNav={setPage} />}
          {page === 'tracker'    && <TrackerView />}
          {page === 'recruiters' && <RecruitersView />}
          {page === 'analytics'  && <AnalyticsView />}
        </div>
      </main>
      <TweaksPanel
        theme={theme} setTheme={updateTheme}
        sidebarCollapsed={sidebarCollapsed} setSidebarCollapsed={updateSidebar}
        visible={tweaksVisible}
      />
    </div>
  );
};

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
