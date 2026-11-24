export const DETAIL_TABS = [
  { id: 'summary', label: 'Özet' },
  { id: 'task', label: 'Aktif Görev' },
  { id: 'attempts', label: 'Denemeler' },
  { id: 'tools', label: 'Araç / Broker' },
  { id: 'evidence', label: 'Kanıtlar' },
  { id: 'acceptance', label: 'Kabul' },
  { id: 'events', label: 'Olaylar' },
];

export function createAgentDetailDrawer(dialogEl) {
  if (!dialogEl) {
    return { open() {}, close() {} };
  }
  const titleEl = dialogEl.querySelector('#detail-dialog-title');
  const bodyEl = dialogEl.querySelector('#detail-dialog-body');
  const tabsEl = dialogEl.querySelector('#detail-dialog-tabs');
  const closeBtn = dialogEl.querySelector('#detail-dialog-close');

  let currentTab = 'summary';
  let currentAgent = null;
  let currentRuns = [];

  function renderTabContent() {
    if (!bodyEl || !currentAgent) return;
    bodyEl.replaceChildren();
    const pre = document.createElement('pre');
    pre.className = 'run-output';

    const relatedRuns = (currentRuns || []).filter((r) => r.role_id === currentAgent.role_id);
    if (currentTab === 'summary') {
      pre.textContent = JSON.stringify(
        {
          agent_instance_id: currentAgent.agent_instance_id,
          role_id: currentAgent.role_id,
          display_name: currentAgent.display_name,
          worker_principal: currentAgent.worker_principal,
          state: currentAgent.state,
          revision: currentAgent.revision,
          last_seen_at: currentAgent.last_seen_at,
        },
        null,
        2,
      );
    } else if (currentTab === 'task') {
      pre.textContent = currentAgent.active_task_id
        ? `active_task_id: ${currentAgent.active_task_id}\nactive_attempt_id: ${currentAgent.active_attempt_id || '-'}\nactive_task_title: ${currentAgent.active_task_title || '-'}`
        : 'Aktif görev yok.';
    } else if (currentTab === 'attempts') {
      pre.textContent = relatedRuns.length
        ? relatedRuns.map((r) => `[${r.state}] ${r.title} (${r.task_id || '-'})`).join('\n')
        : 'Bu ajan için kayıtlı deneme yok.';
    } else if (currentTab === 'tools') {
      const receipts = relatedRuns.filter((r) => r.broker_receipt).map((r) => r.broker_receipt);
      pre.textContent = receipts.length
        ? JSON.stringify(receipts, null, 2)
        : 'Broker araç makbuzu henüz bağlı değil.';
    } else if (currentTab === 'evidence') {
      const verifications = relatedRuns.filter((r) => r.verification).map((r) => r.verification);
      pre.textContent = verifications.length
        ? JSON.stringify(verifications, null, 2)
        : 'Doğrulama kanıtı henüz yok.';
    } else if (currentTab === 'acceptance') {
      pre.textContent =
        'Kabul kararları yalnızca yetkili Kernel r54_acceptance_decisions_read oturumu ile okunur.';
    } else {
      pre.textContent = `Olay akışı: ${currentAgent.last_seen_at || 'veri yok'}`;
    }
    bodyEl.append(pre);
  }

  function renderTabs() {
    if (!tabsEl) return;
    tabsEl.replaceChildren();
    DETAIL_TABS.forEach((t) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'mini-btn';
      btn.textContent = t.label;
      btn.setAttribute('aria-pressed', String(t.id === currentTab));
      btn.addEventListener('click', () => {
        currentTab = t.id;
        renderTabs();
        renderTabContent();
      });
      tabsEl.append(btn);
    });
  }

  function open(agent, runs = []) {
    currentAgent = agent;
    currentRuns = runs;
    currentTab = 'summary';
    if (titleEl) {
      titleEl.textContent = `${agent.display_name} (${agent.role_id})`;
    }
    renderTabs();
    renderTabContent();
    if (typeof dialogEl.showModal === 'function') {
      dialogEl.showModal();
    } else {
      dialogEl.hidden = false;
    }
  }

  function close() {
    if (typeof dialogEl.close === 'function' && dialogEl.open) {
      dialogEl.close();
    } else {
      dialogEl.hidden = true;
    }
  }

  if (closeBtn) {
    closeBtn.addEventListener('click', close);
  }

  return { open, close };
}
