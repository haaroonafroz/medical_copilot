const labels = {
  patient_id: 'Patient ID', patient_name: 'Patient name', birth_date: 'Date of birth',
  admitted: 'Admission date', discharged: 'Discharge date', disposition: 'Discharge disposition',
  diagnoses: 'Diagnoses', medications: 'Current medications', allergies: 'Allergies',
  follow_up: 'Follow-up plan', clinical_note: 'Clinician-approved note'
};
const descriptions = {
  complete: 'Complete discharge record',
  missing_followup: 'Missing follow-up plan',
  conflicting_medication: 'Conflicting medication entries'
};
const state = { run: null, patients: [], dirty: false, poller: null, lastStatus: null };
const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(typeof detail === 'string' ? detail : (detail?.message ? `${detail.message}: ${detail.fields.join(', ')}` : `Request failed (${response.status})`));
  }
  return data;
}
function notice(message, error = false) {
  const el = $('notice'); el.textContent = message; el.className = `show${error ? ' error' : ''}`;
  clearTimeout(notice.timer); notice.timer = setTimeout(() => { el.className = ''; }, 7000);
}
function setStep(step) {
  document.querySelectorAll('.step').forEach(el => {
    const value = Number(el.dataset.step);
    el.classList.toggle('active', value === step);
    el.classList.toggle('done', value < step);
  });
}
function renderPatient() {
  const chosen = state.patients.find(p => p.id === $('patient-select').value);
  $('patient-summary').classList.remove('empty');
  $('patient-summary').innerHTML = chosen ? `<strong>${escapeHtml(chosen.name)}</strong><div class="meta">${escapeHtml(chosen.id)} · ${escapeHtml(descriptions[chosen.scenario] || 'FHIR patient')}</div><div class="source-tags"><span>Patient</span><span>Encounter</span><span>Condition</span><span>Medication</span><span>Allergy</span><span>Observation</span><span>CarePlan</span></div>` : 'No patient selected.';
}
function renderSheet() {
  if (!state.run) return;
  const draft = state.run.draft;
  $('sheet-card').hidden = false; $('target-card').hidden = !draft.approved;
  $('sheet-fields').innerHTML = Object.entries(labels).map(([key,label]) => {
    const field = draft.fields[key];
    const wide = ['diagnoses','medications','allergies','follow_up','clinical_note'].includes(key);
    const status = field.status;
    const control = wide ? `<textarea id="draft-${key}" data-field="${key}" rows="2" ${key === 'patient_id' ? 'readonly' : ''}>${escapeHtml(field.value)}</textarea>`
                         : `<input id="draft-${key}" data-field="${key}" value="${escapeHtml(field.value)}" ${key === 'patient_id' ? 'readonly' : ''}>`;
    const sourceChips = field.source.map(ref => ref === 'Clinician review'
      ? '<span class="source-chip">Clinician review</span>'
      : `<button type="button" class="source-chip" data-source="${escapeHtml(ref)}">${escapeHtml(ref)}</button>`).join('');
    return `<div class="sheet-field ${wide ? 'wide' : ''} ${status === 'missing' ? 'warning' : status === 'conflict' ? 'conflict' : ''}">
      <label for="draft-${key}">${escapeHtml(label)}</label>${control}
      <div class="field-status ${status === 'ready' ? '' : status === 'conflict' ? 'conflict' : 'warn'}">${escapeHtml(status === 'ready' ? 'Ready for review' : field.reason || status)}</div>
      <div class="sources">${sourceChips || '<span class="source-chip">Awaiting clinician input</span>'}</div></div>`;
  }).join('');
  $('draft-state').textContent = draft.approved ? 'Approved' : 'Needs review';
  $('draft-state').className = `pill ${draft.approved ? 'green' : 'amber'}`;
  const active = ['running','paused'].includes(state.run.cua_status);
  $('approve-btn').disabled = state.dirty || draft.approved || active;
  $('save-btn').disabled = active;
  document.querySelectorAll('#sheet-fields input, #sheet-fields textarea').forEach(el => { if (el.dataset.field !== 'patient_id') el.disabled = active; });
  $('execute-btn').disabled = !draft.approved || active;
  $('execute-scripted-btn').disabled = !draft.approved || active || state.run.layout !== 'standard';
  $('execute-scripted-btn').title = state.run.layout === 'standard' ? 'Compare fixed Playwright selectors with the AI Operator' : 'Scripted baseline supports only the standard layout';
  $('target-state').textContent = draft.verified ? 'Verified' : state.run.cua_status === 'paused' ? 'Needs human review' : state.run.cua_status === 'running' ? 'Operator running' : state.run.cua_status === 'failed' ? 'Run failed' : draft.approved ? 'Approved for entry' : 'Awaiting approval';
  $('target-state').className = `pill ${draft.verified ? 'green' : draft.approved ? 'amber' : ''}`;
  if (draft.approved && $('target-frame').getAttribute('src')?.split('?')[0] !== `/his/${state.run.id}`) $('target-frame').src = `/his/${state.run.id}`;
  $('open-target').href = `/his/${state.run.id}`;
  $('resource-list').innerHTML = Object.keys(draft.source_resources).sort().map(ref => `<button type="button" class="source-chip" data-source="${escapeHtml(ref)}">${escapeHtml(ref)}</button>`).join('');
  setStep(draft.verified ? 3 : draft.approved ? 3 : 2);
}
function renderEvents() {
  const events = state.run?.events || [];
  $('event-count').textContent = String(events.length);
  $('session-id').textContent = state.run?.id || 'Prepare a handoff';
  $('copy-session').disabled = !state.run;
  $('event-list').innerHTML = events.length ? [...events].reverse().map(e => {
    const details = Object.keys(e.details || {}).length ? `<pre>${escapeHtml(JSON.stringify(e.details, null, 2))}</pre>` : '';
    return `<div class="event"><small>${escapeHtml(new Date(e.at).toLocaleTimeString())}</small><strong>${escapeHtml(e.kind.replaceAll('_',' '))}</strong><p>${escapeHtml(e.message)}</p>${details}</div>`;
  }).join('') : '<div class="empty-events">Events appear as the workflow runs.</div>';
  const result = state.run?.result;
  const status = state.run?.cua_status || 'idle';
  $('operator-status').textContent = status === 'verified' ? 'Verified' : status === 'paused' ? 'Human review' : status === 'running' ? 'Running' : status === 'failed' ? 'Failed' : 'Idle';
  $('operator-status').className = `pill ${status === 'verified' ? 'green' : status === 'paused' ? 'amber' : status === 'failed' ? 'red' : ''}`;
  $('operator-help').textContent = state.run?.cua_mode === 'scripted' ? 'This comparison used fixed Playwright selectors. No model browser was started.' : status === 'running' ? 'GPT-6 Luna is observing the screen and choosing browser actions.' : status === 'paused' ? 'The browser remains open while the operator waits for your guidance.' : status === 'verified' ? 'The browser saved a draft and all values matched after reload.' : status === 'failed' ? 'The operator stopped. Review the event log for the cause.' : 'The latest browser screenshot appears here when the run starts.';
  $('cancel-btn').hidden = !['running','paused'].includes(status);
  $('human-review').hidden = status !== 'paused';
  $('pause-reason').textContent = state.run?.cua_pause || '';
  if (state.run?.cua_mode === 'model' && status !== 'idle') $('operator-frame').src = `/api/handoff/${state.run.id}/frame?t=${Date.now()}`;
  if (state.run?.cua_mode !== 'model') $('operator-frame').hidden = true;
  $('view-screenshot').hidden = !result?.verified;
  if (result?.verified) $('view-screenshot').href = `/api/handoff/${state.run.id}/screenshot`;
  if (result) {
    $('verification').hidden = false;
    $('verification').className = `verification${result.verified ? '' : ' failed'}`;
    $('verification').textContent = result.verified ? `Verified ${result.matched}/${result.total} persisted fields after reload. Final sign-off remains manual.`
      : `Verification failed: ${result.error || (result.mismatches || []).join(', ')}`;
  }
}
function render() { renderSheet(); renderEvents(); }
function source(ref) {
  const resource = state.run?.draft.source_resources[ref];
  $('source-json').textContent = resource ? JSON.stringify(resource, null, 2) : 'Source is a clinician review.';
}

async function initialize() {
  try {
    const [health, patients] = await Promise.all([api('/api/health'), api('/api/patients')]);
    state.patients = patients;
    $('patient-select').innerHTML = patients.map(p => `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name)} · ${escapeHtml(descriptions[p.scenario] || p.scenario)}</option>`).join('');
    $('source-mode').textContent = health.fhir.mode === 'live' ? 'Live FHIR server' : 'FHIR fixture';
    $('system-status').textContent = health.fhir.reachable ? 'Source ready' : 'FHIR source unavailable';
    $('trace-note').textContent = health.phoenix.configured ? `Phoenix project: ${health.phoenix.project}. Open its Sessions tab and match the session ID above.`
      : `Phoenix tracing unavailable: ${health.phoenix.error || 'not configured'}. Local run events remain visible.`;
    $('phoenix-link').href = `${location.protocol}//${location.hostname}:6006/`;
    if (!health.cua?.configured) notice('OpenAI key unavailable: the AI Operator cannot start.', true);
    renderPatient();
  } catch (error) { notice(error.message, true); $('system-status').textContent = 'Service check failed'; }
}

$('patient-select').addEventListener('change', renderPatient);
$('copy-session').addEventListener('click', async () => {
  if (!state.run) return;
  try { await navigator.clipboard.writeText(state.run.id); notice('Phoenix session ID copied.'); }
  catch (_) { notice('Could not copy the session ID. Select it in the panel instead.', true); }
});
$('prepare-btn').addEventListener('click', async () => {
  try {
    $('prepare-btn').disabled = true;
    if (state.poller) { clearInterval(state.poller); state.poller = null; }
    state.run = await api('/api/handoff', { method:'POST', body:JSON.stringify({patient_id:$('patient-select').value, layout:$('layout-select').value}) });
    state.dirty = false; $('verification').hidden = true; $('source-json').textContent = 'Select a source chip on the discharge sheet.';
    render(); notice('Discharge sheet prepared. Review all fields and their sources.');
  } catch (error) { notice(error.message, true); } finally { $('prepare-btn').disabled = false; }
});
$('sheet-fields').addEventListener('click', event => { const ref = event.target.dataset.source; if (ref) source(ref); });
$('resource-list').addEventListener('click', event => { const ref = event.target.dataset.source; if (ref) source(ref); });
$('sheet-fields').addEventListener('input', event => {
  if (!event.target.dataset.field) return;
  state.dirty = true; $('approve-btn').disabled = true; $('draft-state').textContent = 'Unsaved edits';
});
$('save-btn').addEventListener('click', async () => {
  if (!state.run) return;
  const changes = Object.fromEntries([...document.querySelectorAll('[data-field]')].map(el => [el.dataset.field, el.value]));
  try {
    state.run = await api(`/api/handoff/${state.run.id}/revise`, {method:'POST', body:JSON.stringify({changes})});
    state.dirty = false; render(); notice('Edits saved. Review the source and approve when ready.');
  } catch (error) { notice(error.message, true); }
});
$('approve-btn').addEventListener('click', async () => {
  try {
    state.run = await api(`/api/handoff/${state.run.id}/approve`, {method:'POST'});
    render(); notice('Clinician approval recorded. The mock HIS is ready for handoff.');
  } catch (error) { notice(error.message, true); }
});
async function pollOperator() {
  if (!state.run) return;
  const runId = state.run.id;
  try {
    const updated = await api(`/api/handoff/${runId}`);
    if (state.run?.id !== runId) return;
    const oldStatus = state.run.cua_status;
    state.run = updated; render();
    if (updated.cua_status === 'paused' && oldStatus !== 'paused') notice('The operator paused for your guidance.');
    if (['verified','failed'].includes(updated.cua_status)) {
      if (state.poller) { clearInterval(state.poller); state.poller = null; }
      $('target-frame').src = `/his/${runId}?updated=${Date.now()}`;
      notice(updated.cua_status === 'verified' ? 'The AI Operator saved and verified every field.' : `AI Operator stopped: ${updated.result?.error || 'verification failed'}`, updated.cua_status !== 'verified');
    }
  } catch (error) { notice(error.message, true); }
}
$('operator-frame').addEventListener('load', () => { $('operator-frame').hidden = false; });
$('operator-frame').addEventListener('error', () => { $('operator-frame').hidden = true; });
$('execute-btn').addEventListener('click', async () => {
  try {
    $('execute-btn').disabled = true;
    state.run = await api(`/api/handoff/${state.run.id}/execute-model`, {method:'POST'});
    render(); notice('GPT-6 Luna is observing the mock HIS and choosing actions.');
    if (state.poller) clearInterval(state.poller);
    state.poller = setInterval(pollOperator, 900);
  } catch (error) { notice(error.message, true); $('execute-btn').disabled = false; }
});
$('execute-scripted-btn').addEventListener('click', async () => {
  try {
    $('execute-scripted-btn').disabled = true;
    state.run = await api(`/api/handoff/${state.run.id}/execute`, {method:'POST'});
    render(); $('target-frame').src = `/his/${state.run.id}?baseline=${Date.now()}`;
    notice(state.run.result.verified ? 'Scripted baseline verified all 11 fields.' : 'Scripted baseline found a mismatch.', !state.run.result.verified);
  } catch (error) { notice(error.message, true); }
  finally { $('execute-scripted-btn').disabled = !state.run?.draft.approved; }
});
$('resume-btn').addEventListener('click', async () => {
  const guidance = $('human-guidance').value.trim();
  if (!guidance) { notice('Enter guidance before resuming.', true); return; }
  try {
    state.run = await api(`/api/handoff/${state.run.id}/resume`, {method:'POST', body:JSON.stringify({guidance})});
    $('human-guidance').value = ''; render(); notice('Human guidance sent to the operator.');
  } catch (error) { notice(error.message, true); }
});
$('cancel-btn').addEventListener('click', async () => {
  try { await api(`/api/handoff/${state.run.id}/cancel`, {method:'POST'}); notice('Cancelling the operator…'); }
  catch (error) { notice(error.message, true); }
});
$('download-btn').addEventListener('click', () => {
  if (!state.run) return;
  const fields = Object.entries(labels).map(([key,label]) => `<tr><th>${escapeHtml(label)}</th><td>${escapeHtml(state.run.draft.fields[key].value)}</td><td>${escapeHtml(state.run.draft.fields[key].source.join(', ') || 'Clinician input')}</td></tr>`).join('');
  const html = `<!doctype html><html><head><meta charset="utf-8"><title>Discharge sheet</title><style>body{font:15px system-ui;margin:45px;color:#173143}h1{font:28px Georgia}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ccc;padding:12px;text-align:left;vertical-align:top}th{width:20%}td:last-child{color:#668;font-size:12px}</style></head><body><h1>Discharge sheet · synthetic patient</h1><p>Run ${escapeHtml(state.run.id)} · ${state.run.draft.approved ? 'Clinician approved' : 'Draft'}</p><table>${fields}</table><p>Final sign-off remains manual.</p></body></html>`;
  const link = document.createElement('a'); link.href = URL.createObjectURL(new Blob([html],{type:'text/html'})); link.download = `discharge-sheet-${state.run.draft.patient_id}.html`; link.click(); setTimeout(() => URL.revokeObjectURL(link.href), 1000);
});
initialize();
