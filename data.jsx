// Mock data generator for tracker
(function(){
  const PORTALS = ['LinkedIn', 'Indeed', 'Wellfound', 'Glassdoor', 'Company Site', 'Hacker News', 'Ladders', 'BuiltIn', 'Lever', 'Greenhouse'];
  const COMPANIES = [
    { name: 'Northwind Labs', domain: 'northwind.io' },
    { name: 'Helix Systems', domain: 'helixsys.com' },
    { name: 'Bluewave Robotics', domain: 'bluewave.ai' },
    { name: 'Pinecone Health', domain: 'pineconehealth.co' },
    { name: 'Cedar Analytics', domain: 'cedar-an.com' },
    { name: 'Arcadia Finance', domain: 'arcadiafin.com' },
    { name: 'Meridian Energy', domain: 'meridian-e.com' },
    { name: 'Copper Cloud', domain: 'coppercloud.dev' },
    { name: 'Fernlight Media', domain: 'fernlight.tv' },
    { name: 'Quartz Mobility', domain: 'quartz.app' },
    { name: 'Lumen Commerce', domain: 'lumencom.com' },
    { name: 'Tessellate', domain: 'tessellate.xyz' },
    { name: 'Obsidian Research', domain: 'obsidian-r.ai' },
    { name: 'Harbor Logistics', domain: 'harborlog.com' },
    { name: 'Juniper Foods', domain: 'juniperfoods.co' },
    { name: 'Monolith AI', domain: 'monolith.ai' },
    { name: 'Ember Security', domain: 'ember-sec.io' },
    { name: 'Prism Education', domain: 'prismed.org' },
    { name: 'Savannah Biotech', domain: 'savannahbio.com' },
    { name: 'Granite Ventures', domain: 'granite.vc' },
    { name: 'Halcyon Audio', domain: 'halcyon.fm' },
    { name: 'Riverstone Games', domain: 'riverstone.gg' },
    { name: 'Echo Networks', domain: 'echo-net.com' },
    { name: 'Verdant Agri', domain: 'verdantag.com' }
  ];
  const POSITIONS = [
    'Senior Product Designer', 'Staff UX Designer', 'Design Systems Lead',
    'Product Designer II', 'Sr. Frontend Engineer', 'Full-Stack Engineer',
    'Design Engineer', 'Senior UX Researcher', 'Principal Designer',
    'Product Manager, Growth', 'UX/UI Designer', 'Design Manager',
    'Senior Motion Designer', 'Frontend Platform Engineer', 'Staff Product Designer',
    'Associate Product Designer', 'Design Technologist', 'Sr. Content Designer'
  ];

  function seedRand(seed) {
    let s = seed;
    return () => {
      s = (s * 9301 + 49297) % 233280;
      return s / 233280;
    };
  }
  const rand = seedRand(42);
  const pick = (arr) => arr[Math.floor(rand() * arr.length)];
  const pad = (n) => String(n).padStart(2, '0');

  function fmtDateTime(d) {
    const m = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return `${m[d.getMonth()]} ${pad(d.getDate())}, ${d.getFullYear()} · ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
  function fmtDate(d) {
    const m = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return `${m[d.getMonth()]} ${pad(d.getDate())}, ${d.getFullYear()}`;
  }

  // reference "now"
  const NOW = new Date('2026-04-18T10:30:00');

  function genAppliedRow(i) {
    const co = COMPANIES[i % COMPANIES.length];
    const pos = pick(POSITIONS);
    const postedDaysAgo = 1 + Math.floor(rand() * 14);
    const posted = new Date(NOW.getTime() - postedDaysAgo * 86400000);
    const appliedHoursAfter = 2 + Math.floor(rand() * 60);
    const applied = new Date(posted.getTime() + appliedHoursAfter * 3600000);
    const ats = 58 + Math.floor(rand() * 42);
    const notified = rand() > 0.2;
    const manualReview = rand() > 0.55;
    const isApplied = rand() > 0.15;
    const appStatusRoll = rand();
    const appStatus = !isApplied ? 'Pending' : (appStatusRoll > 0.7 ? 'Rejected' : appStatusRoll > 0.35 ? 'Interviewing' : appStatusRoll > 0.2 ? 'Accepted' : 'Pending');
    const slug = co.name.toLowerCase().replace(/[^a-z]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
    return {
      id: `APP-${1000 + i}`,
      portal: pick(PORTALS),
      company: co.name,
      companyDomain: co.domain,
      position: pos,
      jobPosted: fmtDate(posted),
      jobPostedRaw: posted.getTime(),
      agentTime: fmtDateTime(applied),
      agentTimeRaw: applied.getTime(),
      ats,
      email: `careers@${co.domain}`,
      jdUrl: `https://jobs.${co.domain}/req-${2400 + i}`,
      notified,
      resume: `resume_${slug}_${2026}.pdf`,
      manualReview,
      status: isApplied ? 'Applied' : 'Not Applied',
      appStatus
    };
  }

  function genPreparedRow(i) {
    const co = COMPANIES[(i + 7) % COMPANIES.length];
    const pos = pick(POSITIONS);
    const postedDaysAgo = 0 + Math.floor(rand() * 10);
    const posted = new Date(NOW.getTime() - postedDaysAgo * 86400000);
    const prepHoursAfter = 1 + Math.floor(rand() * 40);
    const prepared = new Date(posted.getTime() + prepHoursAfter * 3600000);
    const ats = 62 + Math.floor(rand() * 38);
    const notified = rand() > 0.25;
    const ready = rand() > 0.18;
    const manuallyApplied = rand() > 0.5;
    const appStatusRoll = rand();
    const appStatus = !manuallyApplied ? 'Pending' : (appStatusRoll > 0.7 ? 'Rejected' : appStatusRoll > 0.4 ? 'Interviewing' : appStatusRoll > 0.2 ? 'Accepted' : 'Pending');
    const slug = co.name.toLowerCase().replace(/[^a-z]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
    return {
      id: `RES-${2000 + i}`,
      portal: pick(PORTALS),
      company: co.name,
      companyDomain: co.domain,
      position: pos,
      jobPosted: fmtDate(posted),
      jobPostedRaw: posted.getTime(),
      agentTime: fmtDateTime(prepared),
      agentTimeRaw: prepared.getTime(),
      ats,
      email: `talent@${co.domain}`,
      jdUrl: `https://careers.${co.domain}/posting-${3100 + i}`,
      notified,
      resume: `resume_${slug}_v2.pdf`,
      status: ready ? 'Resume Ready' : 'Drafting',
      manuallyApplied,
      appStatus
    };
  }

  const ROW_COUNT = 22;
  const appliedRows = Array.from({ length: ROW_COUNT }, (_, i) => genAppliedRow(i));
  const preparedRows = Array.from({ length: ROW_COUNT }, (_, i) => genPreparedRow(i));

  // Analytics data (last 30 days, weekly)
  const weekLabels = ['Wk 11', 'Wk 12', 'Wk 13', 'Wk 14', 'Wk 15', 'Wk 16'];
  const appliedSeries = [14, 19, 22, 17, 26, 31];
  const preparedSeries = [22, 28, 30, 26, 34, 39];
  const atsBuckets = [
    { label: '< 60', value: 4 },
    { label: '60–69', value: 9 },
    { label: '70–79', value: 18 },
    { label: '80–89', value: 24 },
    { label: '90+', value: 11 }
  ];
  const portalMix = [
    { label: 'LinkedIn', value: 34 },
    { label: 'Indeed', value: 22 },
    { label: 'Company Site', value: 18 },
    { label: 'Wellfound', value: 12 },
    { label: 'Other', value: 14 }
  ];
  const funnelStages = [
    { label: 'Jobs Discovered', value: 312 },
    { label: 'Resumes Prepared', value: 186 },
    { label: 'Applications Sent', value: 132 },
    { label: 'Recruiter Reply', value: 41 },
    { label: 'Screens Scheduled', value: 18 },
    { label: 'Onsites',          value: 6 }
  ];
  const topCompanies = [
    { name: 'Monolith AI',       applied: 4, replies: 2 },
    { name: 'Helix Systems',     applied: 3, replies: 2 },
    { name: 'Cedar Analytics',   applied: 3, replies: 1 },
    { name: 'Bluewave Robotics', applied: 2, replies: 1 },
    { name: 'Copper Cloud',      applied: 2, replies: 1 },
    { name: 'Northwind Labs',    applied: 2, replies: 0 }
  ];

  // Dashboard timeline
  const activity = [
    { type: 'applied', title: 'Applied to Senior Product Designer', sub: 'Monolith AI · via LinkedIn', time: '10 min ago', icon: 'check' },
    { type: 'resume',  title: 'Resume tailored for Staff UX Designer', sub: 'Helix Systems · ATS 92', time: '42 min ago', icon: 'file' },
    { type: 'reply',   title: 'Recruiter reply received', sub: 'Bluewave Robotics · careers@bluewave.ai', time: '2 hr ago', icon: 'mail' },
    { type: 'applied', title: 'Applied to Design Systems Lead', sub: 'Cedar Analytics · via Company Site', time: '5 hr ago', icon: 'check' },
    { type: 'resume',  title: 'Resume queued for 4 new postings', sub: 'Auto-prep batch · 21:04', time: 'Yesterday', icon: 'file' }
  ];

  const profile = {
    name: 'Morgan Shaw',
    email: 'morgan.shaw@mailbox.com',
    role: 'Senior Product Designer · 7 yrs',
    location: 'Austin, TX',
    phone: '+1 (512) 555-0117',
    agentId: 'agent-mshaw-7f3a',
    plan: 'Pro',
    joined: 'Mar 2024',
    skills: [
      { name: 'Product Design', v: 92 },
      { name: 'Design Systems', v: 86 },
      { name: 'Prototyping',    v: 78 },
      { name: 'UX Research',    v: 71 },
      { name: 'Frontend (HTML/CSS)', v: 64 }
    ]
  };

  window.__DATA__ = {
    appliedRows, preparedRows,
    weekLabels, appliedSeries, preparedSeries,
    atsBuckets, portalMix, funnelStages, topCompanies,
    activity, profile
  };
})();
