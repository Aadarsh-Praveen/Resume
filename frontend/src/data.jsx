// API fetch functions — connects to FastAPI backend at http://localhost:8000
// Every piece of data in the frontend comes from here; no hardcoded values.
(function () {
  // Empty string = same origin (when served by FastAPI on port 8000).
  // Override with full URL only when running frontend separately.
  const API = window.__API_BASE__ || '';

  async function apiFetch(path) {
    const res = await fetch(API + path);
    if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
    return res.json();
  }

  // ── Formatters ──────────────────────────────────────────────────────────────

  function fmtDate(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return '—';
    const m = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const pad = n => String(n).padStart(2, '0');
    return `${m[d.getMonth()]} ${pad(d.getDate())}, ${d.getFullYear()}`;
  }

  function fmtDateTime(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return '—';
    const m = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const pad = n => String(n).padStart(2, '0');
    return `${m[d.getMonth()]} ${pad(d.getDate())}, ${d.getFullYear()} · ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  function relTime(iso) {
    if (!iso) return '—';
    const diff = Date.now() - new Date(iso).getTime();
    const min = Math.floor(diff / 60000);
    if (min < 60) return min <= 1 ? 'Just now' : `${min} min ago`;
    const hr = Math.floor(min / 60);
    if (hr < 24) return `${hr} hr ago`;
    const days = Math.floor(hr / 24);
    if (days === 1) return 'Yesterday';
    return `${days} days ago`;
  }

  function capitalize(s) {
    if (!s) return s;
    return s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, ' ');
  }

  // ── Mappers ─────────────────────────────────────────────────────────────────

  function mapJobToRow(job) {
    const appStatus = job.approval_status || 'pending_review';
    const isApplied  = appStatus === 'applied' || appStatus === 'approved';
    const isRejected = appStatus === 'rejected';
    const pdfFile = job.pdf_path ? job.pdf_path.split('/').pop() : null;
    const dbStatus = job.status || '';

    let displayStatus;
    if (isApplied) {
      displayStatus = 'Applied';
    } else if (isRejected) {
      displayStatus = 'Not Applied';
    } else if (dbStatus === 'ready') {
      displayStatus = 'Resume Ready';
    } else if (dbStatus === 'low_ats') {
      displayStatus = 'Low ATS';
    } else if (dbStatus === 'high_ats') {
      displayStatus = 'High ATS';
    } else if (dbStatus === 'failed') {
      displayStatus = 'Failed';
    } else if (dbStatus === 'jd_failed') {
      displayStatus = 'No JD';
    } else if (dbStatus === 'skipped_unqualified' || dbStatus === 'skipped_irrelevant') {
      displayStatus = 'Skipped';
    } else if (job.processed === 1) {
      displayStatus = 'Resume Ready';
    } else {
      displayStatus = 'Drafting';
    }

    return {
      id: (isApplied ? 'APP-' : 'RES-') + job.id,
      dbId: job.id,
      portal: capitalize(job.source) || 'Unknown',
      company: job.company || '—',
      companyDomain: '',
      position: job.title || '—',
      jobPosted: fmtDate(job.posted_date || job.created_at),
      jobPostedRaw: new Date(job.posted_date || job.created_at || 0).getTime(),
      agentTime: fmtDateTime(job.applied_at || job.created_at),
      agentTimeRaw: new Date(job.applied_at || job.created_at || 0).getTime(),
      ats: job.ats_score ? Math.round(job.ats_score) : 0,
      email: '',
      jdUrl: job.url || '#',
      notified: false,
      resume: pdfFile || '—',
      hasPdf: !!pdfFile,
      manualReview: !!job.manual_review,
      approvalStatus: appStatus,
      status: displayStatus,
      appStatus: job.application_status || '',
    };
  }

  function mapRecruiter(r) {
    return {
      id: 'REC-' + r.id,
      dbId: r.id,
      name: r.name || 'Unknown',
      company: r.company || '—',
      companyDomain: '',
      recruiterTitle: r.title || '—',
      position: '—',
      email: r.email || '—',
      linkedin: r.linkedin_url ? r.linkedin_url.replace(/^https?:\/\//, '') : '—',
      cold: !!r.email_sent,
      linkedinMsg: !!r.linkedin_sent,
      replied: !!r.replied,
      repliedIn: r.replied_via || '—',
    };
  }

  // ── Public API ───────────────────────────────────────────────────────────────

  window.__API__ = {
    base: API,

    async profile()  { return apiFetch('/api/profile'); },
    async stats()    { return apiFetch('/api/stats'); },

    async recentJobs(limit = 5) {
      return apiFetch(`/api/jobs?limit=${limit}`);
    },

    async appliedRows() {
      const [applied, approved] = await Promise.all([
        apiFetch('/api/jobs?approval_status=applied&limit=500'),
        apiFetch('/api/jobs?approval_status=approved&limit=500'),
      ]);
      return [...applied, ...approved].map(mapJobToRow);
    },

    async preparedRows() {
      const jobs = await apiFetch('/api/jobs?limit=500');
      return jobs.filter(j => j.processed === 1).map(mapJobToRow);
    },

    async recruiters() {
      const { recruiters, stats } = await apiFetch('/api/recruiters');
      return { rows: recruiters.map(mapRecruiter), stats };
    },

    async weekly() {
      const data = await apiFetch('/api/analytics/weekly');
      return {
        weekLabels:    data.map(d => d.week),
        appliedSeries: data.map(d => d.applied),
        preparedSeries: data.map(d => d.prepared),
      };
    },

    async ats() {
      const data = await apiFetch('/api/analytics/ats');
      const labelMap = { '<60': '< 60', '60-69': '60–69', '70-79': '70–79', '80-89': '80–89', '90+': '90+' };
      return data.map(d => ({ label: labelMap[d.bucket] || d.bucket, value: d.count }));
    },

    async funnel() {
      const d = await apiFetch('/api/analytics/funnel');
      return [
        { label: 'Jobs Discovered',  value: d.discovered || 0 },
        { label: 'Resumes Prepared', value: d.prepared   || 0 },
        { label: 'Applications Sent', value: d.applied   || 0 },
      ];
    },

    async portals() {
      const data = await apiFetch('/api/analytics/portals');
      return data.map(d => ({ label: capitalize(d.source), value: d.count }));
    },

    relTime,
    fmtDate,
    fmtDateTime,
  };
})();
