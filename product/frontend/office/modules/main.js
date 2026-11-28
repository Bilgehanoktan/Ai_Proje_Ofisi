import {
  fetchOfficeSnapshot,
  fetchReadinessSnapshot,
  fetchVerifierCalibration,
  observeOfficeAgents,
  sendMemoryAction,
  submitOfficeTask,
} from './api-client.js';
import { ROLES, SCENE_KEY_TO_ROLE_ID, createOfficeCanvas } from './office-canvas.js';
import { createPanelsController } from './panels.js';
import { createOfficeEventStream } from './sse-client.js';

let liveAgentInstances = [];
let stopObservingAgents;
let selectedAgentInstanceId = null;
let taskCommandEnabled = false;
let lastSubmittedTaskId = null;
let officeSnapshotPending = false;
let lastOfficeSnapshotAt = '';
let zoom = 100;
let sseStream = null;
let sseTenantId = '';
let sseRefreshTimer = null;

const officeCanvas = createOfficeCanvas(
  document.getElementById('office-canvas'),
  document.getElementById('hotspots'),
  {
    onSelectAgent: (agentId) => selectAgentInstance(agentId),
    onSelectRole: (key) => {
      const rid = SCENE_KEY_TO_ROLE_ID[key];
      if (liveAgentInstances.length && rid) {
        const matches = liveAgentInstances.filter((a) => a.role_id === rid);
        const chosen = matches.find((a) => a.state === 'RUNNING') || matches[0];
        if (chosen) {
          selectAgentInstance(chosen.agent_instance_id, true);
          return;
        }
      }
      panels.renderSampleRoleContext(key);
    },
  },
);

const panels = createPanelsController(document, {
  onSelectAgent: (agentId, switchTab) => selectAgentInstance(agentId, switchTab),
  onMemoryAction: async (recordId, action) => {
    try {
      const ok = await sendMemoryAction(recordId, action);
      if (ok) await refreshLiveOffice();
    } catch {
      // Bağlantı hatası bir sonraki yenilemede gösterilir.
    }
  },
});

function selectAgentInstance(agentId, switchTab = true) {
  selectedAgentInstanceId = agentId;
  const found = liveAgentInstances.find((a) => a.agent_instance_id === agentId);
  if (found) {
    panels.renderAgentContext(found);
    document.querySelectorAll('#role-list button').forEach((btn) => {
      btn.setAttribute('aria-pressed', String(btn.dataset.agentId === agentId));
    });
    document.querySelectorAll('.scene-agent').forEach((btn) => {
      btn.setAttribute('aria-pressed', String(btn.dataset.sceneAgentId === agentId));
    });
    if (switchTab) panels.showTab('context');
  }
}

// İlk yüklemede örnek rol listesini oluştur
const initialRoleList = document.getElementById('role-list');
if (initialRoleList && !initialRoleList.childElementCount) {
  Object.entries(ROLES).forEach(([key, r]) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.append(document.createTextNode(r.name));
    const small = document.createElement('small');
    small.textContent = 'Örnek rol · UNVERIFIED';
    btn.append(small);
    btn.addEventListener('click', () => panels.renderSampleRoleContext(key));
    initialRoleList.append(btn);
  });
}

// Zoom & expand kontrolleri
const world = document.querySelector('.world');
function setZoom(v) {
  zoom = Math.max(75, Math.min(150, v));
  world.style.width = `${zoom}%`;
  document.getElementById('zoom-reset').textContent = `${zoom}%`;
}
document.getElementById('zoom-in').onclick = () => setZoom(zoom + 25);
document.getElementById('zoom-out').onclick = () => setZoom(zoom - 25);
document.getElementById('zoom-reset').onclick = () => setZoom(100);

const officeEl = document.getElementById('office');
const expandBtn = document.getElementById('expand');
function setExpanded(on) {
  officeEl.classList.toggle('expanded', on);
  expandBtn.setAttribute('aria-pressed', String(on));
  expandBtn.textContent = on ? 'Küçült' : 'Büyüt';
  document.body.style.overflow = on ? 'hidden' : '';
}
expandBtn.onclick = () => setExpanded(!officeEl.classList.contains('expanded'));
document.addEventListener('keydown', (ev) => {
  if (ev.key === 'Escape') setExpanded(false);
});
document.querySelectorAll('a[href^="#"]').forEach((a) => {
  a.addEventListener('click', () => {
    const target = document.getElementById(a.hash.slice(1));
    if (target?.tagName === 'DETAILS') target.open = true;
  });
});

function handleConnectionLoss() {
  stopObservingAgents?.();
  taskCommandEnabled = false;
  liveAgentInstances = [];
  panels.renderConnectionLoss(lastOfficeSnapshotAt);
  officeCanvas.draw(null, 'Canlı ajan verisi alınamadı');
}

function ensureSseStream(tenantId) {
  if (!tenantId || tenantId === sseTenantId) return;
  sseTenantId = tenantId;
  if (sseStream) sseStream.close();
  sseStream = createOfficeEventStream({
    tenantId,
    onEvent: () => {
      if (sseRefreshTimer) clearTimeout(sseRefreshTimer);
      sseRefreshTimer = setTimeout(() => {
        void refreshLiveOffice();
      }, 300);
    },
    onResyncRequired: () => {
      void refreshLiveOffice();
    },
    onError: (readyState) => {
      if (readyState === 2) {
        handleConnectionLoss();
      }
    },
  });
  sseStream.connect();
}

export async function refreshLiveOffice() {
  if (officeSnapshotPending) return;
  officeSnapshotPending = true;
  try {
    const d = await fetchOfficeSnapshot(5000);
    if (d?.connected !== true) {
      handleConnectionLoss();
      return;
    }
    lastOfficeSnapshotAt = d.updated_at || new Date().toLocaleTimeString('tr-TR');
    const resolvedTenant = d.tenant_id || d.agent_instances?.[0]?.tenant_id || '';
    if (resolvedTenant) ensureSseStream(resolvedTenant);

    const ollama = d.ollama || null;
    const oBadge = document.getElementById('ollama-badge');
    if (oBadge) {
      oBadge.textContent = ollama?.available === true
        ? `Ollama hazır (${ollama.default_model || 'yerel'})`
        : ollama?.available === false ? 'Ollama erişilemiyor' : 'Ollama durumu bilinmiyor';
      oBadge.classList.toggle('live', ollama?.available === true);
    }
    const modelSelect = document.getElementById('office-task-model');
    if (modelSelect && ollama) {
      const models = Array.isArray(ollama.models) ? ollama.models.filter(Boolean) : [];
      const prevValue = modelSelect.value;
      const defaultModel = ollama.default_model || '';
      const optionList = models.length > 0 ? models : (defaultModel ? [defaultModel] : []);
      if (optionList.length > 0) {
        modelSelect.innerHTML = '';
        for (const name of optionList) {
          const opt = document.createElement('option');
          opt.value = name;
          opt.textContent = name === defaultModel ? `${name} (varsayılan)` : name;
          modelSelect.appendChild(opt);
        }
        if (prevValue && optionList.includes(prevValue)) {
          modelSelect.value = prevValue;
        } else if (defaultModel && optionList.includes(defaultModel)) {
          modelSelect.value = defaultModel;
        }
      }
    }

    const fieldset = document.getElementById('office-task-fieldset');
    const panelSub = document.getElementById('task-panel-sub');
    taskCommandEnabled = Boolean(d.command_enabled);
    if (fieldset) fieldset.disabled = !taskCommandEnabled;
    if (panelSub) {
      panelSub.textContent = taskCommandEnabled ? 'Görev gönderimi açık.' : 'Görev gönderimi kapalı.';
    }

    if (Array.isArray(d.office_runs)) {
      panels.renderOfficeRuns(d.office_runs);
      if (lastSubmittedTaskId) {
        const match = d.office_runs.find((r) => r.task_id === lastSubmittedTaskId);
        const fb = document.getElementById('office-task-feedback');
        if (match && fb) {
          const shortId = match.task_id.slice(0, 8);
          if (match.state === 'ACCEPTED') {
            fb.textContent = `Tamamlandı (${shortId}): Kabul edildi.`;
            lastSubmittedTaskId = null;
          } else if (match.state === 'REJECTED') {
            fb.textContent = `Tamamlandı (${shortId}): Reddedildi.`;
            lastSubmittedTaskId = null;
          } else if (match.state === 'ERROR') {
            fb.textContent = `Hata (${shortId}): ${match.error || 'bilinmeyen hata'}`;
            lastSubmittedTaskId = null;
          }
        }
      }
    }
    if (Array.isArray(d.memory_promotions)) {
      panels.renderMemoryPromotions(d.memory_promotions, Boolean(d.lifecycle_enabled));
    }
    if (d.budget) panels.renderBudgetAndEffects(d.budget, d.external_effects || []);

    const sv = d.services || {};
    const ct = d.counts || {};
    const wr = d.worker_runner || {};
    const postgresConnected = d.mode === 'LIVE_POSTGRES_18_6';
    const sourceLabel = postgresConnected
      ? 'PostgreSQL bağlı'
      : d.mode === 'LOCAL_OFFICE_ONLY' ? 'Yerel ofis · UNVERIFIED' : 'Ofis sunucusu bağlı · UNVERIFIED';
    const workerState = sv.worker_daemon || wr.daemon_state || 'Bilinmiyor';
    stopObservingAgents?.();
    stopObservingAgents = observeOfficeAgents(d, (agents) => {
      liveAgentInstances = agents;
      if (!agents.some((agent) => agent.agent_instance_id === selectedAgentInstanceId)) {
        selectedAgentInstanceId = agents[0]?.agent_instance_id ?? null;
      }
      panels.renderAgentInstancesList(agents, selectedAgentInstanceId);
      officeCanvas.draw(agents, sourceLabel, selectedAgentInstanceId);
    });

    const badge = document.getElementById('mode-badge');
    if (badge) {
      badge.textContent = sourceLabel;
      badge.classList.toggle('live', postgresConnected);
    }
    const navNote = document.getElementById('nav-note');
    if (navNote) navNote.textContent = sourceLabel;

    document.getElementById('stat-roles').textContent = Number.isInteger(ct.tasks) ? String(ct.tasks) : 'Veri yok';
    document.getElementById('stat-live-agent').textContent =
      Array.isArray(d.agent_instances) ? String(liveAgentInstances.length) : 'Veri yok';
    document.getElementById('stat-freshness').textContent = lastOfficeSnapshotAt;
    document.getElementById('office-footer-left').textContent = sourceLabel;
    document.getElementById('office-footer-right').textContent = `Worker: ${workerState}`;

    document.getElementById('office-notice').textContent =
      `Yedekleme: ${sv.backup_timer || 'bilinmiyor'} · G0: ${d.g0 || 'bilinmiyor'} · İlk akış: ${d.first13 || 'bilinmiyor'}.`;
    document.getElementById('bottom-status').textContent =
      `${d.mode} · G0 ${d.g0 || 'bilinmiyor'} · First13 ${d.first13 || 'bilinmiyor'}`;

    const actItems = [
      ...(d.office_runs || []).map((r) => ({
        title: `Canlı Koşu: ${r.title} [${r.state}]`,
        sub: `${r.work_type} · ${r.role_id} · ${r.updated_at || ''}`,
      })),
      ...(d.tasks || []).map((t) => ({
        title: `Görev: ${t.title} [${t.state}]`,
        sub: `id=${t.id} · rev=${t.revision}`,
      })),
      ...(d.outbox || []).map((o) => ({
        title: `Olay: ${o.kind}`,
        sub: o.created_at || '',
      })),
    ];
    panels.renderLiveList(document.getElementById('activity-body'), actItems, 'Henüz canlı aktivite kaydı yok.');

    const appItems = [
      {
        title: `G0 & First13 İnsan Kabulü (${d.first13 || 'bilinmiyor'})`,
        sub: `Durum: ${d.g0 || 'bilinmiyor'}`,
      },
      ...(d.approvals || []).map((a) => ({
        title: `Kabul Kaydı #${a.id.slice(0, 8)}`,
        sub: `Onaylayan: ${a.accepted_by} · ${a.created_at || ''}`,
      })),
    ];
    panels.renderLiveList(document.getElementById('approvals-body'), appItems, 'Henüz onay kaydı yok.');
  } catch {
    handleConnectionLoss();
  } finally {
    officeSnapshotPending = false;
  }
}

const taskForm = document.getElementById('office-task-form');
if (taskForm) {
  taskForm.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    if (!taskCommandEnabled) return;
    const fb = document.getElementById('office-task-feedback');
    const btn = document.getElementById('office-task-submit');
    const tokenEl = document.getElementById('office-task-token');
    const token = (tokenEl?.value || '').trim();
    const readPathEl = document.getElementById('office-task-read-path');
    const readPath = (readPathEl?.value || '').trim();
    const modelEl = document.getElementById('office-task-model');
    const selectedModel = (modelEl?.value || '').trim();
    const payload = {
      title: document.getElementById('office-task-title').value.trim(),
      work_type: document.getElementById('office-task-work-type').value,
      role_id: document.getElementById('office-task-role').value,
      goal: document.getElementById('office-task-goal').value.trim(),
      acceptance_criteria: document
        .getElementById('office-task-criteria')
        .value.split('\n')
        .map((s) => s.trim())
        .filter(Boolean),
    };
    if (readPath) {
      payload.read_path = readPath;
    }
    if (selectedModel) {
      payload.model = selectedModel;
    }
    btn.disabled = true;
    fb.textContent = 'Görev kuyruğa alınıyor…';
    try {
      const { ok, status, data } = await submitOfficeTask(payload, token);
      if (!ok) {
        fb.textContent = `Gönderilemedi (${status}): ${data.error || 'bilinmeyen hata'}`;
        return;
      }
      lastSubmittedTaskId = data.task?.task_id || null;
      fb.textContent = `Kuyruğa alındı (${data.task?.task_id?.slice(0, 8) || 'ok'}). Yerel ajan çalıştırıyor…`;
      document.getElementById('office-task-title').value = '';
      document.getElementById('office-task-goal').value = '';
      document.getElementById('office-task-criteria').value = '';
      await refreshLiveOffice();
    } catch {
      fb.textContent = 'Sunucuya ulaşılamadı.';
    } finally {
      if (tokenEl) tokenEl.value = '';
      btn.disabled = false;
    }
  });
}

async function refreshReadinessAndCalibration() {
  const [readinessRes, calibrationRes] = await Promise.allSettled([
    fetchReadinessSnapshot(),
    fetchVerifierCalibration(),
  ]);
  panels.renderReadinessAndCalibration(
    readinessRes.status === 'fulfilled' ? readinessRes.value : null,
    calibrationRes.status === 'fulfilled' ? calibrationRes.value : null,
  );
}

async function refreshExpansionStatus() {
  const el = document.getElementById('expansion-status-body');
  if (!el) return;
  try {
    const resp = await fetch('/api/expansion-status', { cache: 'no-store' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    el.textContent = '';
    const ul = document.createElement('ul');

    const roles = Array.isArray(data.pilot_roles) ? data.pilot_roles : [];
    const liRoles = document.createElement('li');
    liRoles.textContent = `087 Pilot Roller (${roles.length}): ` + roles.map((r) => `${r.name} [${r.license_spdx}]`).join(', ');
    ul.appendChild(liRoles);

    const ci = data.code_intel || {};
    const liCi = document.createElement('li');
    liCi.textContent = `Kod Zekâsı (MOD-012): ${ci.adapter || '-'} [${ci.license || '-'}] — ${ci.installed ? 'KURULU' : 'KURULU DEĞİL'} (${ci.authority_mode || ''})`;
    ul.appendChild(liCi);

    const ints = Array.isArray(data.integrations) ? data.integrations : [];
    const liInts = document.createElement('li');
    liInts.textContent = `Ticari Adaptörler (D1–D5): ` + ints.map((i) => `${i.id} ${i.name} [${i.license}]`).join(' · ');
    ul.appendChild(liInts);

    const pa = data.phase_a_gates || {};
    const liPa = document.createElement('li');
    liPa.textContent = `Faz A Kapıları: A1=${pa.A1_exp01_ollama || '-'} | A2=${pa.A2_ci_security || '-'} | A3=${pa.A3_restore_rto_rpo || '-'}`;
    ul.appendChild(liPa);

    const opt = Array.isArray(data.optional_on_demand) ? data.optional_on_demand : [];
    if (opt.length > 0) {
      const liOpt = document.createElement('li');
      liOpt.textContent = `İhtiyaca Bağlı (B2/C2): ` + opt.join(' · ');
      ul.appendChild(liOpt);
    }

    el.appendChild(ul);
  } catch (err) {
    el.textContent = `Genişleme durumu okunamadı: ${err?.message || 'hata'}`;
  }
}

refreshLiveOffice();
refreshReadinessAndCalibration();
refreshExpansionStatus();
setInterval(refreshLiveOffice, 2500);
