// Root app — routing + state + tweaks wiring
const { useState: useStateApp, useEffect: useEffectApp } = React;

const App = () => {
  const defaults = window.__TWEAKS__ || { theme: 'light', sidebarCollapsed: false };
  const saved = (() => { try { return JSON.parse(localStorage.getItem('applyflow_state') || '{}'); } catch { return {}; } })();

  const [authed, setAuthed] = useStateApp(saved.authed || false);
  const [page, setPage] = useStateApp(saved.page || 'dashboard');
  const [theme, setTheme] = useStateApp(saved.theme || defaults.theme);
  const [sidebarCollapsed, setSidebarCollapsed] = useStateApp(
    saved.sidebarCollapsed ?? defaults.sidebarCollapsed
  );
  const [tweaksVisible, setTweaksVisible] = useStateApp(false);
  const [data, setData] = useStateApp(window.__DATA__);

  // persist
  useEffectApp(() => {
    localStorage.setItem('applyflow_state', JSON.stringify({ authed, page, theme, sidebarCollapsed }));
  }, [authed, page, theme, sidebarCollapsed]);

  // apply theme
  useEffectApp(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  // Tweaks bridge
  useEffectApp(() => {
    const handler = (e) => {
      if (!e.data) return;
      if (e.data.type === '__activate_edit_mode') setTweaksVisible(true);
      if (e.data.type === '__deactivate_edit_mode') setTweaksVisible(false);
    };
    window.addEventListener('message', handler);
    window.parent.postMessage({ type: '__edit_mode_available' }, '*');
    return () => window.removeEventListener('message', handler);
  }, []);

  const persistTweak = (edits) => {
    window.parent.postMessage({ type: '__edit_mode_set_keys', edits }, '*');
  };
  const updateTheme = (t) => { setTheme(t); persistTweak({ theme: t }); };
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
        profile={data.profile}
      />
      <main className="main">
        <Topbar
          page={page}
          onToggleSidebar={() => updateSidebar(!sidebarCollapsed)}
          theme={theme}
          onToggleTheme={() => updateTheme(theme === 'light' ? 'dark' : 'light')}
        />
        <div className="content">
          {page === 'dashboard' && <DashboardView profile={data.profile} data={data} onNav={setPage} />}
          {page === 'tracker'   && <TrackerView data={data} setData={setData} />}
          {page === 'recruiters' && <RecruitersView />}
          {page === 'analytics' && <AnalyticsView data={data} />}
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
