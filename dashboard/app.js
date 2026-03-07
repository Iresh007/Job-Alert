const api = {
  jobs: '/api/jobs?min_score=70&limit=200',
  jobsExcel: '/api/jobs/export/excel?min_score=70&limit=2000',
  superJobs: '/api/jobs?min_score=70&super_only=true&limit=25',
  top3: '/api/jobs/top3',
  analytics: '/api/analytics',
  nextRuns: '/api/scheduler/next-runs',
  settings: '/api/settings',
  runScan: '/api/scan/run',
};
const API_FALLBACK_BASE = 'http://127.0.0.1:5050';

const el = (id) => document.getElementById(id);

function metricCard(label, value) {
  return `<div class="metric"><div>${label}</div><strong>${value}</strong></div>`;
}

function jobCard(job) {
  const flags = [];
  if (job.is_ultra_low_competition) flags.push('ULTRA LOW COMPETITION');
  if (job.apply_within_6_hours) flags.push('Apply within 6 hours');
  return `<article class="card">
    <h3>${job.title}</h3>
    <p>${job.company} • ${job.location}</p>
    <p>Score: <strong>${job.interview_probability}</strong> | Salary fit: <strong>${job.salary_fit_probability}</strong></p>
    <p>${flags.join(' | ')}</p>
    <a href="${job.url}" target="_blank" rel="noopener">Open Application</a>
  </article>`;
}

function nextRunCard(item) {
  const dt = item.next_run_time ? new Date(item.next_run_time) : null;
  const local = dt ? dt.toLocaleString() : 'N/A';
  return `<article class="card">
    <h3>${item.job_id}</h3>
    <p>Next: <strong>${local}</strong></p>
    <p>${item.trigger}</p>
  </article>`;
}

function populateHeatmap(map) {
  const host = el('heatmap');
  host.innerHTML = '';
  for (let i = 0; i < 24; i += 1) {
    const count = map[String(i)] || 0;
    const intensity = Math.min(0.15 + count * 0.12, 0.95);
    const color = `rgba(0,95,115,${intensity})`;
    host.innerHTML += `<div class="heat" style="background:${color};color:#fff">${String(i).padStart(2, '0')}h<br>${count}</div>`;
  }
}

async function fetchJson(url, options = {}) {
  const primaryUrl = (window.location.protocol === 'file:' && url.startsWith('/'))
    ? `${API_FALLBACK_BASE}${url}`
    : url;

  try {
    const res = await fetch(primaryUrl, options);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  } catch (primaryErr) {
    if (url.startsWith('/')) {
      const fallbackUrl = `${API_FALLBACK_BASE}${url}`;
      const res = await fetch(fallbackUrl, options);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    }
    throw primaryErr;
  }
}

async function loadDashboard() {
  const defaults = {
    roles: ['Data Engineer', 'Databricks Engineer', 'Azure Data Engineer', 'Snowflake Data Engineer'],
    locations: ['India', 'Remote'],
    skills: ['Azure Databricks', 'Snowflake', 'Azure Data Factory', 'ADLS Gen2', 'PySpark', 'SQL'],
    experience_min: 2,
    experience_max: 5,
    salary_min_lpa: 18,
    salary_max_lpa: 25,
    scan_times: ['08:00', '12:00', '16:00', '23:00'],
    scan_interval_hours: 6,
    auto_run_enabled: true,
    excluded_companies: ['EXL Services'],
  };

  const [jobsRes, superJobsRes, top3Res, analyticsRes, nextRunsRes, settingsRes] = await Promise.allSettled([
    fetchJson(api.jobs),
    fetchJson(api.superJobs),
    fetchJson(api.top3),
    fetchJson(api.analytics),
    fetchJson(api.nextRuns),
    fetchJson(api.settings),
  ]);
  const jobs = jobsRes.status === 'fulfilled' ? jobsRes.value : [];
  const superJobs = superJobsRes.status === 'fulfilled' ? superJobsRes.value : [];
  const top3 = top3Res.status === 'fulfilled' ? top3Res.value : [];
  const analytics = analyticsRes.status === 'fulfilled' ? analyticsRes.value : {
    total_jobs: 0,
    qualified_jobs: 0,
    average_interview_probability: 0,
    average_salary_fit: 0,
    super_priority_count: 0,
    posting_heatmap: {},
  };
  const nextRuns = nextRunsRes.status === 'fulfilled' ? nextRunsRes.value : [];
  const settings = settingsRes.status === 'fulfilled' ? settingsRes.value : defaults;

  el('metrics').innerHTML = [
    metricCard('Total Jobs', analytics.total_jobs),
    metricCard('Qualified', analytics.qualified_jobs),
    metricCard('Avg Interview Probability', analytics.average_interview_probability),
    metricCard('Avg Salary Fit', analytics.average_salary_fit),
    metricCard('Super Priority', analytics.super_priority_count),
  ].join('');

  el('superPriority').innerHTML = superJobs.length ? superJobs.map(jobCard).join('') : '<p>No super-priority jobs currently.</p>';
  el('nextRuns').innerHTML = nextRuns.length ? nextRuns.map(nextRunCard).join('') : '<p>No scheduled runs configured.</p>';
  el('topThree').innerHTML = top3.length ? top3.map(jobCard).join('') : '<p>No top roles currently.</p>';

  el('jobsBody').innerHTML = jobs.map((job) => {
    const flags = [job.is_super_priority ? 'SUPER PRIORITY' : '', job.is_ultra_low_competition ? 'ULTRA' : '']
      .filter(Boolean)
      .join(' | ');
    return `<tr>
      <td><a href="${job.url}" target="_blank" rel="noopener">${job.title}</a></td>
      <td>${job.company}</td>
      <td>${job.location}</td>
      <td>${job.interview_probability}</td>
      <td>${job.salary_fit_probability}</td>
      <td>${job.source}</td>
      <td>${flags}</td>
    </tr>`;
  }).join('');

  populateHeatmap(analytics.posting_heatmap);

  const form = el('settingsForm');
  form.roles.value = (settings.roles || []).join(', ');
  form.locations.value = (settings.locations || []).join(', ');
  form.skills.value = (settings.skills || []).join(', ');
  form.experience_min.value = settings.experience_min ?? 2;
  form.experience_max.value = settings.experience_max ?? 5;
  form.salary_min_lpa.value = settings.salary_min_lpa ?? 18;
  form.salary_max_lpa.value = settings.salary_max_lpa ?? 25;
  form.scan_times.value = (settings.scan_times || []).join(', ');
  form.scan_interval_hours.value = settings.scan_interval_hours ?? 6;
  form.auto_run_enabled.checked = settings.auto_run_enabled ?? true;
  form.excluded_companies.value = (settings.excluded_companies || []).join(', ');

  if (jobsRes.status !== 'fulfilled' || settingsRes.status !== 'fulfilled') {
    el('runStatus').textContent = 'Backend not reachable for some APIs. Ensure server is running at http://127.0.0.1:5050.';
  }
}

el('runScan').addEventListener('click', async () => {
  const status = el('runStatus');
  status.textContent = 'Running...';
  try {
    const result = await fetchJson(api.runScan, { method: 'POST' });
    status.textContent = `Done: +${result.inserted} net-new (${result.super_priority} super)`;
    await loadDashboard();
  } catch (err) {
    status.textContent = `Run failed: ${err.message}`;
  }
});

el('downloadExcel').addEventListener('click', async () => {
  const status = el('runStatus');
  status.textContent = 'Preparing Excel...';
  try {
    const primaryUrl = (window.location.protocol === 'file:' && api.jobsExcel.startsWith('/'))
      ? `${API_FALLBACK_BASE}${api.jobsExcel}`
      : api.jobsExcel;
    const finalUrl = `${primaryUrl}${primaryUrl.includes('?') ? '&' : '?'}ts=${Date.now()}`;
    const link = document.createElement('a');
    link.href = finalUrl;
    link.download = '';
    document.body.appendChild(link);
    link.click();
    link.remove();
    status.textContent = 'Excel download started.';
  } catch (err) {
    status.textContent = `Download failed: ${err.message}`;
  }
});

el('settingsForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = {
    roles: form.roles.value.split(',').map((x) => x.trim()).filter(Boolean),
    locations: form.locations.value.split(',').map((x) => x.trim()).filter(Boolean),
    skills: form.skills.value.split(',').map((x) => x.trim()).filter(Boolean),
    experience_min: Number(form.experience_min.value),
    experience_max: Number(form.experience_max.value),
    salary_min_lpa: Number(form.salary_min_lpa.value),
    salary_max_lpa: Number(form.salary_max_lpa.value),
    scan_times: form.scan_times.value.split(',').map((x) => x.trim()).filter(Boolean),
    scan_interval_hours: Number(form.scan_interval_hours.value),
    auto_run_enabled: Boolean(form.auto_run_enabled.checked),
    excluded_companies: form.excluded_companies.value.split(',').map((x) => x.trim()).filter(Boolean),
  };
  await fetchJson(api.settings, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  await loadDashboard();
});

loadDashboard().catch((err) => {
  el('runStatus').textContent = `Load error: ${err.message}`;
});
