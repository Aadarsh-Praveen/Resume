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

const LoginHero = () => (
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
    <div className="hero-stat-grid">
      <div className="hero-stat"><div className="hero-stat-num">342</div><div className="hero-stat-lbl">apps submitted</div></div>
      <div className="hero-stat"><div className="hero-stat-num">28%</div><div className="hero-stat-lbl">reply rate</div></div>
      <div className="hero-stat"><div className="hero-stat-num">84</div><div className="hero-stat-lbl">avg ATS score</div></div>
    </div>
  </div>
);

const LoginView = ({ onLogin }) => {
  const [mode, setMode] = useState('login'); // login | signup
  const [step, setStep] = useState('email'); // email | otp (login) ; form | otp | verified (signup)
  const [email, setEmail] = useState('morgan.shaw@mailbox.com');
  const [otp, setOtp] = useState(['', '', '', '', '', '']);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const cellRefs = useRef([]);

  // signup state
  const [form, setForm] = useState({ firstName: '', lastName: '', email: '', phone: '' });
  const [channel, setChannel] = useState('email'); // email | phone
  const [otpVerified, setOtpVerified] = useState(false);

  const reset = (m) => {
    setMode(m); setStep(m === 'login' ? 'email' : 'form');
    setOtp(['','','','','','']); setError(''); setOtpVerified(false);
  };

  // ---- LOGIN ----
  const handleSendOtp = (e) => {
    e.preventDefault();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { setError('Enter a valid email'); return; }
    setError(''); setSubmitting(true);
    setTimeout(() => { setSubmitting(false); setStep('otp'); setTimeout(() => cellRefs.current[0]?.focus(), 50); }, 600);
  };
  const handleVerify = (e) => {
    e.preventDefault();
    if (otp.some(c => c === '')) { setError('Enter all 6 digits'); return; }
    setError(''); setSubmitting(true);
    setTimeout(() => { setSubmitting(false); onLogin({ email }); }, 600);
  };

  // ---- SIGNUP ----
  const updateForm = (k, v) => setForm({ ...form, [k]: v });
  const signupDone = form.firstName.trim() && form.lastName.trim()
    && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)
    && form.phone.replace(/\D/g,'').length >= 7;

  const handleSignupSubmit = (e) => {
    e.preventDefault();
    if (!signupDone) { setError('Please fill every field correctly'); return; }
    setError(''); setSubmitting(true);
    setTimeout(() => { setSubmitting(false); setStep('channel'); }, 500);
  };
  const sendSignupOtp = () => {
    setSubmitting(true);
    setTimeout(() => {
      setSubmitting(false); setStep('otp');
      setOtp(['','','','','','']); setOtpVerified(false);
      setTimeout(() => cellRefs.current[0]?.focus(), 50);
    }, 600);
  };
  const handleSignupVerify = () => {
    if (otp.some(c => c === '')) { setError('Enter all 6 digits'); return; }
    setError(''); setSubmitting(true);
    setTimeout(() => { setSubmitting(false); setOtpVerified(true); }, 500);
  };
  const handleCreateAccount = () => {
    setSubmitting(true);
    setTimeout(() => { setSubmitting(false); onLogin({ email: form.email }); }, 500);
  };

  return (
    <div className="login-page" data-screen-label="Login">
      <LoginHero />
      <div className="login-form-wrap">
        {mode === 'login' && step === 'email' && (
          <form className="login-form" onSubmit={handleSendOtp}>
            <div className="login-brand"><div className="login-brand-mark">A</div><span>Applyflow</span></div>
            <h2>Welcome back</h2>
            <p className="login-form-sub">Enter your email and we'll send a one-time code.</p>
            <label className="field-label">Login email</label>
            <input className="field-input" type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@company.com" autoFocus style={{ marginBottom: error ? 6 : 20 }} />
            {error && <div style={{ color: 'var(--danger)', fontSize: 12, marginBottom: 16 }}>{error}</div>}
            <button className="btn btn-primary btn-block" type="submit" disabled={submitting}>
              {submitting ? 'Sending code…' : 'Send one-time code'}
            </button>
            <div className="resend-row" style={{ marginTop: 24 }}>
              New to Applyflow? <button type="button" onClick={() => reset('signup')}>Sign up</button>
            </div>
          </form>
        )}

        {mode === 'login' && step === 'otp' && (
          <form className="login-form" onSubmit={handleVerify}>
            <button type="button" className="back-link" onClick={() => setStep('email')}><Icon name="arrow-left" size={14} /> Back</button>
            <div className="login-brand"><div className="login-brand-mark">A</div><span>Applyflow</span></div>
            <h2>Check your inbox</h2>
            <p className="login-form-sub">We sent a 6-digit code to <strong style={{ color:'var(--text)' }}>{email}</strong></p>
            <div className="otp-notice"><Icon name="mail" size={16} /><span>Demo code: <strong>482 915</strong> — any 6 digits will work.</span></div>
            <label className="field-label">One-time code</label>
            <OtpInput otp={otp} setOtp={setOtp} cellRefs={cellRefs} />
            {error && <div style={{ color: 'var(--danger)', fontSize: 12, marginBottom: 10 }}>{error}</div>}
            <button className="btn btn-primary btn-block" type="submit" disabled={submitting}>
              {submitting ? 'Verifying…' : 'Verify & sign in'}
            </button>
            <div className="resend-row">Didn't get it? <button type="button">Resend code</button></div>
          </form>
        )}

        {mode === 'signup' && step === 'form' && (
          <form className="login-form" onSubmit={handleSignupSubmit}>
            <button type="button" className="back-link" onClick={() => reset('login')}><Icon name="arrow-left" size={14} /> Back to sign in</button>
            <div className="login-brand"><div className="login-brand-mark">A</div><span>Applyflow</span></div>
            <h2>Create your account</h2>
            <p className="login-form-sub">Takes under a minute.</p>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap: 12, marginBottom: 14 }}>
              <div>
                <label className="field-label">First name</label>
                <input className="field-input" value={form.firstName} onChange={e => updateForm('firstName', e.target.value)} placeholder="Morgan" autoFocus />
              </div>
              <div>
                <label className="field-label">Last name</label>
                <input className="field-input" value={form.lastName} onChange={e => updateForm('lastName', e.target.value)} placeholder="Shaw" />
              </div>
            </div>
            <label className="field-label">Email ID</label>
            <input className="field-input" type="email" value={form.email} onChange={e => updateForm('email', e.target.value)} placeholder="you@company.com" style={{ marginBottom: 14 }} />
            <label className="field-label">Phone number</label>
            <input className="field-input" type="tel" value={form.phone} onChange={e => updateForm('phone', e.target.value)} placeholder="+1 (555) 000-0000" style={{ marginBottom: error ? 6 : 20 }} />
            {error && <div style={{ color: 'var(--danger)', fontSize: 12, marginBottom: 16 }}>{error}</div>}
            <button className="btn btn-primary btn-block" type="submit" disabled={submitting || !signupDone}>
              {submitting ? 'Please wait…' : 'Done'}
            </button>
          </form>
        )}

        {mode === 'signup' && step === 'channel' && (
          <div className="login-form">
            <button type="button" className="back-link" onClick={() => setStep('form')}><Icon name="arrow-left" size={14} /> Back</button>
            <div className="login-brand"><div className="login-brand-mark">A</div><span>Applyflow</span></div>
            <h2>Where should we send the code?</h2>
            <p className="login-form-sub">Pick how to receive your 6-digit verification code.</p>
            <div style={{ display:'grid', gap: 10, marginBottom: 20 }}>
              <button type="button" onClick={() => setChannel('email')}
                className="channel-card" data-on={channel === 'email'}>
                <div style={{ width: 34, height: 34, borderRadius: 8, background:'var(--accent-soft)', color:'var(--accent-text)', display:'grid', placeItems:'center' }}>
                  <Icon name="mail" size={16} />
                </div>
                <div style={{ flex: 1, textAlign: 'left' }}>
                  <div style={{ fontSize: 13.5, fontWeight: 500 }}>Email</div>
                  <div style={{ fontSize: 12, color: 'var(--text-3)' }}>{form.email}</div>
                </div>
                <span className="radio-dot" data-on={channel === 'email'}></span>
              </button>
              <button type="button" onClick={() => setChannel('phone')}
                className="channel-card" data-on={channel === 'phone'}>
                <div style={{ width: 34, height: 34, borderRadius: 8, background:'var(--accent-soft)', color:'var(--accent-text)', display:'grid', placeItems:'center' }}>
                  <Icon name="phone" size={16} />
                </div>
                <div style={{ flex: 1, textAlign: 'left' }}>
                  <div style={{ fontSize: 13.5, fontWeight: 500 }}>Phone (SMS)</div>
                  <div style={{ fontSize: 12, color: 'var(--text-3)' }}>{form.phone}</div>
                </div>
                <span className="radio-dot" data-on={channel === 'phone'}></span>
              </button>
            </div>
            <button className="btn btn-primary btn-block" onClick={sendSignupOtp} disabled={submitting}>
              {submitting ? 'Sending…' : `Send code to ${channel === 'email' ? 'email' : 'phone'}`}
            </button>
          </div>
        )}

        {mode === 'signup' && step === 'otp' && (
          <div className="login-form">
            <button type="button" className="back-link" onClick={() => setStep('channel')}><Icon name="arrow-left" size={14} /> Back</button>
            <div className="login-brand"><div className="login-brand-mark">A</div><span>Applyflow</span></div>
            <h2>Verify your {channel === 'email' ? 'email' : 'phone'}</h2>
            <p className="login-form-sub">We sent a 6-digit code to <strong style={{ color:'var(--text)' }}>{channel === 'email' ? form.email : form.phone}</strong></p>
            <div className="otp-notice"><Icon name={channel === 'email' ? 'mail' : 'phone'} size={16} /><span>Demo code: <strong>482 915</strong> — any 6 digits will work.</span></div>
            <label className="field-label">One-time code</label>
            <OtpInput otp={otp} setOtp={setOtp} cellRefs={cellRefs} />
            {otpVerified && (
              <div style={{ display:'flex', gap: 8, alignItems:'center', color:'var(--success)', fontSize: 13, marginBottom: 14 }}>
                <Icon name="check-circle" size={14} /> Code verified successfully.
              </div>
            )}
            {error && <div style={{ color: 'var(--danger)', fontSize: 12, marginBottom: 10 }}>{error}</div>}
            {!otpVerified ? (
              <button className="btn btn-ghost btn-block" onClick={handleSignupVerify} disabled={submitting || otp.some(c => c === '')}>
                {submitting ? 'Verifying…' : 'Verify code'}
              </button>
            ) : (
              <button className="btn btn-primary btn-block" onClick={handleCreateAccount} disabled={submitting}>
                {submitting ? 'Creating account…' : 'Create Account'}
              </button>
            )}
            <div className="resend-row">Didn't get it? <button type="button" onClick={sendSignupOtp}>Resend code</button></div>
          </div>
        )}
      </div>
    </div>
  );
};

window.LoginView = LoginView;
