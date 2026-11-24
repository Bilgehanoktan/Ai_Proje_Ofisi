import { ROLES, ROLE_ID_TO_SCENE_KEY } from './office-canvas.js';

export const AGENT_STATE_LABELS = {
  IDLE: 'Boşta (IDLE)',
  RUNNING: 'Çalışıyor (RUNNING)',
  BLOCKED: 'Engelli (BLOCKED)',
  STALE: 'Güncel değil (STALE)',
};

export function createPanelsController(doc, { onSelectAgent, onMemoryAction }) {
  const tabs = [...doc.querySelectorAll('[role="tab"]')];

  function showTab(id, focus = false) {
    tabs.forEach((tab) => {
      const active = tab.getAttribute('aria-controls') === id;
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
      const panel = doc.getElementById(tab.getAttribute('aria-controls'));
      if (panel) panel.hidden = !active;
      if (active && focus) tab.focus();
    });
  }

  tabs.forEach((tab, idx) => {
    tab.addEventListener('click', () => showTab(tab.getAttribute('aria-controls')));
    tab.addEventListener('keydown', (ev) => {
      let next;
      if (ev.key === 'ArrowRight') next = (idx + 1) % tabs.length;
      if (ev.key === 'ArrowLeft') next = (idx + tabs.length - 1) % tabs.length;
      if (ev.key === 'Home') next = 0;
      if (ev.key === 'End') next = tabs.length - 1;
      if (next !== undefined) {
        ev.preventDefault();
        showTab(tabs[next].getAttribute('aria-controls'), true);
      }
    });
  });

  function renderLiveList(container, items, emptyText) {
    if (!container) return;
    container.replaceChildren();
    if (!items.length) {
      const p = doc.createElement('p');
      p.textContent = emptyText;
      container.append(p);
      return;
    }
    const ul = doc.createElement('ul');
    ul.className = 'live-list';
    items.forEach(({ title, sub }) => {
      const li = doc.createElement('li');
      const strong = doc.createElement('strong');
      strong.textContent = title;
      const small = doc.createElement('small');
      small.textContent = sub;
      li.append(strong, small);
      ul.append(li);
    });
    container.append(ul);
  }

  function renderAgentContext(agent) {
    if (!agent) return;
    const sceneKey = ROLE_ID_TO_SCENE_KEY[agent.role_id] || 'engineer';
    const role = ROLES[sceneKey] || ROLES.engineer;
    doc.getElementById('context-eyebrow').textContent = 'Canlı AgentInstance kaydı';
    doc.getElementById('role-icon').textContent = role.icon;
    doc.getElementById('role-title').textContent = agent.display_name;
    doc.getElementById('role-sub').textContent = `${agent.role_id} · ${agent.worker_principal}`;
    const cState = doc.getElementById('context-state');
    cState.textContent = AGENT_STATE_LABELS[agent.state] || agent.state;
    cState.classList.toggle('live', agent.state === 'RUNNING' || agent.state === 'IDLE');
    doc.getElementById('role-description').textContent =
      agent.state === 'RUNNING' && agent.active_task_title
        ? `Aktif görev: ${agent.active_task_title}`
        : role.description;
    const taskInfo =
      agent.state === 'RUNNING'
        ? `active_task_id: ${agent.active_task_id || '-'} | active_attempt_id: ${agent.active_attempt_id || '-'}`
        : 'Aktif görev yok';
    doc.getElementById('context-evidence').textContent =
      `agent_instance_id: ${agent.agent_instance_id} | ${taskInfo} | rev: ${agent.revision} | son görülme: ${agent.last_seen_at || '-'}`;
    doc.getElementById('context-boundary').textContent =
      'Bu kayıt PostgreSQL 18.6 company.agent_instances (088 FORCE RLS) tablosundan okunmaktadır.';
    doc.querySelectorAll('.hotspot').forEach((btn) => {
      btn.setAttribute('aria-pressed', String(btn.dataset.role === sceneKey));
    });
  }

  function renderSampleRoleContext(key) {
    const role = ROLES[key];
    if (!role) return;
    doc.getElementById('role-title').textContent = role.name;
    doc.getElementById('role-sub').textContent = role.sub;
    doc.getElementById('role-description').textContent = role.description;
    doc.getElementById('role-icon').textContent = role.icon;
    doc.querySelectorAll('.hotspot').forEach((btn) => {
      btn.setAttribute('aria-pressed', String(btn.dataset.role === key));
    });
    showTab('context');
  }

  function renderAgentInstancesList(instances, selectedId) {
    const list = doc.getElementById('role-list');
    if (!list || !Array.isArray(instances) || !instances.length) return;
    list.replaceChildren();
    doc.getElementById('agents-sub').textContent =
      `Canlı PostgreSQL 18.6 üzerinde ${instances.length} kalıcı AgentInstance kaydı izleniyor.`;
    instances.forEach((a) => {
      const btn = doc.createElement('button');
      btn.type = 'button';
      btn.dataset.agentId = a.agent_instance_id;
      btn.setAttribute('aria-pressed', String(a.agent_instance_id === selectedId));
      btn.append(doc.createTextNode(`${a.display_name} (${a.role_id})`));
      const small = doc.createElement('small');
      const taskPart = a.state === 'RUNNING' && a.active_task_title ? ` · Görev: ${a.active_task_title}` : '';
      small.textContent = `${AGENT_STATE_LABELS[a.state] || a.state}${taskPart} · id=${a.agent_instance_id.slice(0, 8)}`;
      btn.append(small);
      btn.addEventListener('click', () => onSelectAgent(a.agent_instance_id, true));
      list.append(btn);
    });
    if (selectedId) {
      const cur = instances.find((a) => a.agent_instance_id === selectedId);
      if (cur) renderAgentContext(cur);
    }
  }

  function renderOfficeRuns(runs) {
    const box = doc.getElementById('office-runs-list');
    if (!box) return;
    box.replaceChildren();
    if (!Array.isArray(runs) || !runs.length) return;
    runs.forEach((run) => {
      const card = doc.createElement('div');
      card.className = `run-card ${run.state === 'ERROR' ? 'error' : (run.state === 'REJECTED' ? 'rejected' : '')}`;
      const head = doc.createElement('strong');
      head.textContent = `[${run.state}] ${run.title} (${run.work_type} · ${run.role_id})`;
      card.append(head);

      const meta = doc.createElement('div');
      meta.className = 'run-meta';
      const dbNote = run.db_persisted ? 'Kernel PG kaydedildi' : 'Yerel ajan koşusu (Kernel oturumu yok)';
      const verNote = run.verification
        ? `Doğrulama: ${run.verification.reason} (${run.verification.verified_by})`
        : (run.error ? `Hata: ${run.error}` : 'Ajan çalışıyor / kuyrukta...');
      const tokNote = run.exec_result
        ? ` · Model: ${run.exec_result.model} · ${run.exec_result.eval_count || 0} token · ${run.exec_result.total_duration_ms || 0} ms`
        : '';
      meta.textContent = `${dbNote} · ${verNote}${tokNote}`;
      card.append(meta);

      if (run.broker_receipt) {
        const receiptEl = doc.createElement('div');
        receiptEl.className = 'run-meta';
        const digest = String(run.broker_receipt.source_digest || '').slice(0, 12);
        receiptEl.textContent = `Broker Makbuzu: ${run.broker_receipt.receipt_id || '-'} · digest=${digest || '-'} · doğrulayan=${run.broker_receipt.verified_by || '-'}`;
        card.append(receiptEl);
      }

      if (run.exec_result && run.exec_result.response) {
        const pre = doc.createElement('pre');
        pre.className = 'run-output';
        pre.textContent = run.exec_result.response;
        card.append(pre);
      }
      box.append(card);
    });
  }

  function renderMemoryPromotions(items, enabled) {
    const box = doc.getElementById('memory-promotions-body');
    if (!box) return;
    box.replaceChildren();
    if (!Array.isArray(items) || !items.length) {
      const p = doc.createElement('p');
      p.textContent = 'Henüz hafıza adayı yok. Kabul edilen görevler otomatik aday üretir.';
      box.append(p);
      return;
    }
    const ul = doc.createElement('ul');
    ul.className = 'live-list';
    items.forEach((m) => {
      const li = doc.createElement('li');
      const strong = doc.createElement('strong');
      strong.textContent = `[${m.state}] ${m.record_id}`;
      const small = doc.createElement('small');
      small.textContent = `${m.summary} · doğrulayan=${m.verified_by || '-'} · terfi=${m.promoted_by || '-'}`;
      li.append(strong, small);
      if (enabled && m.state === 'VERIFIED') {
        const bar = doc.createElement('div');
        bar.className = 'mini-actions';
        const okBtn = doc.createElement('button');
        okBtn.type = 'button';
        okBtn.className = 'mini-btn ok';
        okBtn.textContent = 'Terfi Et (PROMOTED)';
        okBtn.addEventListener('click', () => onMemoryAction(m.record_id, 'promote'));
        const noBtn = doc.createElement('button');
        noBtn.type = 'button';
        noBtn.className = 'mini-btn warn';
        noBtn.textContent = 'Reddet';
        noBtn.addEventListener('click', () => onMemoryAction(m.record_id, 'reject'));
        bar.append(okBtn, noBtn);
        li.append(bar);
      }
      ul.append(li);
    });
    box.append(ul);
  }

  function renderBudgetAndEffects(budget, effects) {
    const box = doc.getElementById('budget-effects-body');
    if (!box) return;
    box.replaceChildren();
    if (!budget) {
      const p = doc.createElement('p');
      p.textContent = 'Canlı bütçe defteri bağlı değil.';
      box.append(p);
      return;
    }
    const sum = doc.createElement('p');
    sum.textContent = `Limit: ${budget.budget_limit_minor} · Harcanan: ${budget.spent_minor} · Blokeli: ${budget.held_minor} · Kalan: ${budget.available_minor}${budget.blocked_by_unknown ? ' · [UNKNOWN KİLİT AKTİF]' : ''}`;
    box.append(sum);
    if (Array.isArray(effects) && effects.length) {
      const listWrap = doc.createElement('div');
      box.append(listWrap);
      renderLiveList(
        listWrap,
        effects.map((e) => ({
          title: `[${e.status}] ${e.provider} (${e.effect_id})`,
          sub: `key=${e.idempotency_key}`,
        })),
        '',
      );
    }
  }

  function renderConnectionLoss(lastSnapshotAt) {
    const badge = doc.getElementById('mode-badge');
    badge.classList.remove('live');
    badge.textContent = lastSnapshotAt ? 'Bağlantı kesildi' : 'Canlı veri yok';
    doc.getElementById('stat-freshness').textContent = lastSnapshotAt
      ? `Son okuma ${lastSnapshotAt} · güncel değil`
      : 'Bağlı değil';
    doc.getElementById('office-footer-left').textContent = lastSnapshotAt
      ? 'Son alınan ofis verisi gösteriliyor.'
      : 'Canlı ofis verisi alınamadı.';
    const cState = doc.getElementById('context-state');
    cState.classList.remove('live');
    cState.textContent = 'Bağlantı kesildi · güncel durum doğrulanamıyor';
    doc.getElementById('role-description').textContent =
      'Canlı bağlantı kesildiği için ajanın aktif görev yürütüp yürütmediği doğrulanamıyor.';
    doc.querySelectorAll('#role-list small').forEach((el) => {
      el.textContent = 'Güncel değil · bağlantı bekleniyor';
    });
    doc.getElementById('ollama-badge')?.classList.remove('live');
    doc.getElementById('nav-note').textContent = 'Canlı bağlantı bekleniyor.';
    const fieldset = doc.getElementById('office-task-fieldset');
    if (fieldset) fieldset.disabled = true;
  }

  return {
    showTab,
    renderLiveList,
    renderAgentContext,
    renderSampleRoleContext,
    renderAgentInstancesList,
    renderOfficeRuns,
    renderMemoryPromotions,
    renderBudgetAndEffects,
    renderConnectionLoss,
  };
}
