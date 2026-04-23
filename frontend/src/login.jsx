// Login + Signup + OTP flows
const { useState, useRef, useEffect } = React;

const OtpInput = ({ otp, setOtp, cellRefs }) => {
  const handleCell = (i, e) => {
    const v = e.target.value.replace(/\D/g, '').slice(-1);
    const next = otp.slice(); next[i] = v; setOtp(next);
    if (v && i < 5) cellRefs.current[i+1]?.focus();
  };
  const handleKey = (i, e) => {
    if (e.key === 'Backspace' && !otp[i] && i > 0) cellRefs.current[i-1]?.focus();
    if (e.key === 'ArrowLeft' && i > 0) cellRefs.current[i-1]?.focus();
    if (e.key === 'ArrowRight' && i < 5) cellRefs.current[i+1]?.focus();
  };
  const handlePaste = (e) => {
    const pasted = e.clipboardData.getData('text').replace(/\D/g,'').slice(0,6);
    if (pasted.length) {
      const next = pasted.split('').concat(Array(6).fill('')).slice(0,6);
      setOtp(next);
      cellRefs.current[Math.min(pasted.length, 5)]?.focus();
      e.preventDefault();
    }
  };
  return (
    <div className="otp-row" onPaste={handlePaste}>
      {otp.map((v, i) => (
        <input key={i}
          ref={el => cellRefs.current[i] = el}
          className={`otp-cell ${v ? 'filled' : ''}`}
          inputMode="numeric" maxLength={1} value={v}
          onChange={e => handleCell(i, e)} onKeyDown={e => handleKey(i, e)} />
      ))}
    </div>
  );
};

const LoginHero = () => {
  const [heroStats, setHeroStats] = React.useState(null);

  React.useEffect(() => {
    Promise.all([
      window.__API__.stats().catch(() => null),
      window.__API__.ats().catch(() => null),
    ]).then(([stats, ats]) => {
      if (!stats) return;
      const avgAts = ats && ats.length
        ? Math.round(ats.reduce((sum, b, _, arr) => {
            const mid = { '< 60': 55, '60–69': 65, '70–79': 75, '80–89': 85, '90+': 93 };
            return sum + (mid[b.label] || 75) * b.value;
          }, 0) / Math.max(1, ats.reduce((s, b) => s + b.value, 0)))
        : null;
      setHeroStats({
        applied: stats.applied || 0,
        total: stats.total || 0,
        avgAts,
      });
    });
  }, []);

  return (
    <div className="login-hero">
      <div className="login-hero-inner">
        <div style={{ display:'flex', alignItems:'center', gap: 10, fontWeight: 600 }}>
          <div style={{ width: 32, height: 32, borderRadius: 8, background: 'rgba(255,255,255,0.18)', display:'grid', placeItems: 'center', fontSize: 14, fontWeight: 700 }}>A</div>
          <span>Applyflow</span>
        </div>
        <div style={{ marginTop: 96 }}>
          <h1>Your AI apply<br/>agent, organized.</h1>
          <p>Applyflow tailors your resume, submits applications and tracks every outcome — so you can focus on interviews, not forms.</p>
        </div>
      </div>
      {heroStats && (heroStats.total > 0 || heroStats.applied > 0) && (
        <div className="hero-stat-grid">
          <div className="hero-stat"><div className="hero-stat-num">{heroStats.total}</div><div className="hero-stat-lbl">jobs discovered</div></div>
          <div className="hero-stat"><div className="hero-stat-num">{heroStats.applied}</div><div className="hero-stat-lbl">apps submitted</div></div>
          {heroStats.avgAts && <div className="hero-stat"><div className="hero-stat-num">{heroStats.avgAts}</div><div className="hero-stat-lbl">avg ATS score</div></div>}
        </div>
      )}
    </div>
  );
};

const LoginView = ({ onLogin }) => {
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!password.trim()) { setError('Enter your dashboard password'); return; }
    setError(''); setSubmitting(true);
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      });
      if (res.ok) {
        onLogin();
      } else {
        setError('Incorrect password. Check your DASHBOARD_PASSWORD env var.');
      }
    } catch {
      setError('Cannot reach server — is it running?');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-page" data-screen-label="Login">
      <LoginHero />
      <div className="login-form-wrap">
        <form className="login-form" onSubmit={handleSubmit}>
          <div className="login-brand"><div className="login-brand-mark">A</div><span>Applyflow</span></div>
          <h2>Welcome back</h2>
          <p className="login-form-sub">Enter your dashboard password to continue.</p>
          <label className="field-label">Password</label>
          <input
            className="field-input"
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            placeholder="Your DASHBOARD_PASSWORD"
            autoFocus
            style={{ marginBottom: error ? 6 : 20 }}
          />
          {error && <div style={{ color: 'var(--danger)', fontSize: 12, marginBottom: 16 }}>{error}</div>}
          <button className="btn btn-primary btn-block" type="submit" disabled={submitting}>
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  );
};

window.LoginView = LoginView;
