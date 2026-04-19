// Icons (inline SVG)
const Icon = ({ name, size = 16, stroke = 1.75, ...rest }) => {
  const s = size;
  const props = {
    width: s, height: s, viewBox: '0 0 24 24',
    fill: 'none', stroke: 'currentColor', strokeWidth: stroke,
    strokeLinecap: 'round', strokeLinejoin: 'round',
    ...rest
  };
  switch (name) {
    case 'dashboard':
      return <svg {...props}><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/></svg>;
    case 'tracker':
      return <svg {...props}><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M8 4v16"/></svg>;
    case 'analytics':
      return <svg {...props}><path d="M4 19V5M4 19h16"/><path d="M8 15v-4M12 15V9M16 15v-6"/></svg>;
    case 'logout':
      return <svg {...props}><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><path d="M10 17l-5-5 5-5M5 12h12"/></svg>;
    case 'bell':
      return <svg {...props}><path d="M6 8a6 6 0 1 1 12 0c0 7 3 7 3 9H3c0-2 3-2 3-9z"/><path d="M10 21a2 2 0 0 0 4 0"/></svg>;
    case 'search':
      return <svg {...props}><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>;
    case 'menu':
      return <svg {...props}><path d="M4 6h16M4 12h16M4 18h16"/></svg>;
    case 'sliders':
      return <svg {...props}><path d="M4 6h10M20 6h-2M4 12h4M20 12H14M4 18h10M20 18h-2"/><circle cx="17" cy="6" r="2"/><circle cx="11" cy="12" r="2"/><circle cx="17" cy="18" r="2"/></svg>;
    case 'download':
      return <svg {...props}><path d="M12 4v11M7 10l5 5 5-5M5 19h14"/></svg>;
    case 'external':
      return <svg {...props}><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>;
    case 'mail':
      return <svg {...props}><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 7 9-7"/></svg>;
    case 'check':
      return <svg {...props}><path d="m5 12 5 5L20 7"/></svg>;
    case 'check-circle':
      return <svg {...props}><circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/></svg>;
    case 'x':
      return <svg {...props}><path d="M6 6l12 12M18 6 6 18"/></svg>;
    case 'arrow-left':
      return <svg {...props}><path d="M19 12H5M12 5l-7 7 7 7"/></svg>;
    case 'arrow-up':
      return <svg {...props}><path d="M12 19V5M5 12l7-7 7 7"/></svg>;
    case 'arrow-down':
      return <svg {...props}><path d="M12 5v14M5 12l7 7 7-7"/></svg>;
    case 'sort':
      return <svg {...props}><path d="M8 4v16M4 8l4-4 4 4M16 20V4M20 16l-4 4-4-4"/></svg>;
    case 'sun':
      return <svg {...props}><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>;
    case 'moon':
      return <svg {...props}><path d="M20 14.5A8 8 0 1 1 9.5 4a6 6 0 0 0 10.5 10.5z"/></svg>;
    case 'chevron-left':
      return <svg {...props}><path d="m15 6-6 6 6 6"/></svg>;
    case 'chevron-right':
      return <svg {...props}><path d="m9 6 6 6-6 6"/></svg>;
    case 'chevron-down':
      return <svg {...props}><path d="m6 9 6 6 6-6"/></svg>;
    case 'calendar':
      return <svg {...props}><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 9h18M8 3v4M16 3v4"/></svg>;
    case 'user':
      return <svg {...props}><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-7 8-7s8 3 8 7"/></svg>;
    case 'shield':
      return <svg {...props}><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z"/></svg>;
    case 'file':
      return <svg {...props}><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-6-6z"/><path d="M14 3v6h6"/></svg>;
    case 'sparkles':
      return <svg {...props}><path d="M12 3v3M12 18v3M3 12h3M18 12h3M6 6l2 2M16 16l2 2M6 18l2-2M16 8l2-2"/></svg>;
    case 'briefcase':
      return <svg {...props}><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>;
    case 'map':
      return <svg {...props}><path d="M12 21s-7-6-7-11a7 7 0 0 1 14 0c0 5-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/></svg>;
    case 'phone':
      return <svg {...props}><path d="M22 16.9V21a1 1 0 0 1-1.1 1 19 19 0 0 1-8.4-3 19 19 0 0 1-6-6A19 19 0 0 1 3.5 4.6 1 1 0 0 1 4.5 3.5h4a1 1 0 0 1 1 .7c.2.9.4 1.8.8 2.6a1 1 0 0 1-.2 1.1l-1.7 1.6a16 16 0 0 0 6 6l1.6-1.7a1 1 0 0 1 1.1-.2c.8.4 1.7.6 2.6.8a1 1 0 0 1 .7 1z"/></svg>;
    case 'id':
      return <svg {...props}><rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="12" r="2.5"/><path d="M14 10h5M14 14h3"/></svg>;
    default: return null;
  }
};

window.Icon = Icon;
