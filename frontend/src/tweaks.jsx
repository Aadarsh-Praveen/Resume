// Tweaks panel
const { useEffect: useEffectT } = React;

const TweaksPanel = ({ theme, setTheme, sidebarCollapsed, setSidebarCollapsed, visible }) => {
  if (!visible) return null;
  return (
    <div className="tweaks-panel">
      <h4>Tweaks</h4>
      <div className="tweak-row">
        <span>Theme</span>
        <div className="seg">
          <button className={theme === 'light' ? 'on' : ''} onClick={() => setTheme('light')}>Light</button>
          <button className={theme === 'dark' ? 'on' : ''} onClick={() => setTheme('dark')}>Dark</button>
        </div>
      </div>
      <div className="tweak-row">
        <span>Sidebar</span>
        <div className="seg">
          <button className={!sidebarCollapsed ? 'on' : ''} onClick={() => setSidebarCollapsed(false)}>Expanded</button>
          <button className={sidebarCollapsed ? 'on' : ''} onClick={() => setSidebarCollapsed(true)}>Collapsed</button>
        </div>
      </div>
    </div>
  );
};

window.TweaksPanel = TweaksPanel;
