import { fetchOfficeSnapshot, sendMemoryAction, submitOfficeTask } from './api-client.js';
import { ROLES, SCENE_KEY_TO_ROLE_ID, createOfficeCanvas } from './office-canvas.js';
import { createPanelsController } from './panels.js';
import { createOfficeEventStream } from './sse-client.js';

let liveAgentInstances = [];
let selectedAgentInstanceId = null;
let taskCommandEnabled = false;
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
  taskCommandEnabled = false;
  panels.renderConnectionLoss(lastOfficeSnapshotAt);
  officeCanvas.draw([], []);
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
    if (oBadge && ollama) {
      oBadge.textContent = ollama.available
        ? `Ollama: HAZIR (${ollama.default_model || 'yerel'})`
        : `Ollama: KAPALI (${ollama.error || 'erişilemiyor'})`;
      oBadge.classList.toggle('live', Boolean(ollama.available));
    }

    const fieldset = document.getElementById('office-task-fieldset');
    const panelSub = document.getElementById('task-panel-sub');
    taskCommandEnabled = Boolean(d.command_enabled);
    if (fieldset) fieldset.disabled = !taskCommandEnabled;
    if (panelSub && taskCommandEnabled) {
      const wr = d.worker_runner || {};
      panelSub.textContent = `AutonomousWorkerDaemon (${wr.daemon_state || 'RUNNING'}) + ücretsiz yerel Ollama bağlı. Kuyruk: ${wr.queued || 0}, Tamamlanan: ${wr.processed || 0}.`;
    }

    if (Array.isArray(d.office_runs)) panels.renderOfficeRuns(d.office_runs);
    if (Array.isArray(d.agent_instances) && d.agent_instances.length) {
      liveAgentInstances = d.agent_instances;
      panels.renderAgentInstancesList(liveAgentInstances, selectedAgentInstanceId);
      if (!selectedAgentInstanceId) {
        const initial = liveAgentInstances.find((a) => a.state === 'RUNNING') || liveAgentInstances[0];
        selectedAgentInstanceId = initial.agent_instance_id;
        panels.renderAgentContext(initial);
      }
    }
    if (Array.isArray(d.memory_promotions)) {
      panels.renderMemoryPromotions(d.memory_promotions, Boolean(d.lifecycle_enabled));
    }
    if (d.budget) panels.renderBudgetAndEffects(d.budget, d.external_effects || []);

    const sv = d.services || {};
    const ct = d.counts || {};
    const wr = d.worker_runner || {};
    officeCanvas.draw(
      liveAgentInstances,
      d.office_runs,
      `Canlı PG 18.6 bağlı · Worker: ${sv.worker_daemon || wr.daemon_state || 'bilinmiyor'}`,
    );

    const badge = document.getElementById('mode-badge');
    if (badge) {
      badge.textContent = 'CANLI · PG 18.6 (55490)';
      badge.classList.add('live');
    }
    const navNote = document.getElementById('nav-note');
    if (navNote) navNote.textContent = 'Canlı ofis verisi bağlı.';

    document.getElementById('stat-roles').textContent = `${ct.tasks || 0} görev (${ct.accepted_tasks || 0} kabul)`;
    document.getElementById('stat-live-agent').textContent = `Worker: ${sv.worker_daemon || wr.daemon_state || 'bilinmiyor'}`;
    document.getElementById('stat-freshness').textContent = d.updated_at || 'Canlı';
    document.getElementById('office-footer-left').textContent = `● Canlı PostgreSQL 18.6 bağlı · 087 tabloları aktif (${ct.tasks || 0} görev)`;
    document.getElementById('office-footer-right').textContent = `Yedekleme: ${sv.backup_timer || 'bilinmiyor'} (günlük) · First13 ${d.first13 || 'bilinmiyor'}`;

    if (!liveAgentInstances.length) {
      const cState = document.getElementById('context-state');
      cState.textContent = `CANLI · Worker ${sv.worker_daemon || wr.daemon_state || 'bilinmiyor'} · First13 ${d.first13 || 'bilinmiyor'}`;
      cState.classList.add('live');
      document.getElementById('context-eyebrow').textContent = 'Seçili ofis rolü';
      document.getElementById('agents-sub').textContent = 'Çekirdek roller. Canlı ajan örneği bilgisi bu bağlantıda bulunmuyor.';
      document.querySelectorAll('#role-list small').forEach((el) => {
        el.textContent = 'Tasarım rolü';
      });
      document.getElementById('context-evidence').textContent =
        `Küme: ${d.cluster || 'yerel'} | Hedef: ${ct.objectives || 0}, Plan: ${ct.plans || 0}, Kabul: ${ct.accepted_tasks || 0}/${ct.tasks || 0} | 087 kayıtları: katalog=${ct.catalog_entries || 0}, terfi=${ct.memory_promotions || 0}, şablon=${ct.work_template_validations || 0}, dış_etki=${ct.external_effect_ledger || 0}`;
      document.getElementById('context-boundary').textContent =
        'Tüm sayılar ve kayıtlar canlı PostgreSQL 18.6 (55490) veritabanından okunmaktadır.';
    }

    document.getElementById('office-notice').textContent =
      `Canlı bağlantı aktif: ${d.cluster || 'yerel'} · Worker: ${sv.worker_daemon || wr.daemon_state} · Yedekleme: ${sv.backup_timer || 'n/a'} · G0: ${d.g0 || 'n/a'} · First13: ${d.first13 || 'bilinmiyor'}.`;
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
    btn.disabled = true;
    fb.textContent = 'Görev kuyruğa alınıyor…';
    try {
      const { ok, status, data } = await submitOfficeTask(payload, token);
      if (!ok) {
        fb.textContent = `Gönderilemedi (${status}): ${data.error || 'bilinmeyen hata'}`;
        return;
      }
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

refreshLiveOffice();
setInterval(refreshLiveOffice, 2500);
