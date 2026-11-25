export const SUPPORTED_SSE_EVENTS = [
  'ObjectiveCreated',
  'TaskCreated',
  'Migration087Verified',
  'MemoryPromoted',
  'BudgetSettled',
  'WorkerTaskClaimed',
  'WorkerTaskAccepted',
  'WorkerTaskRejected',
  'WorkerTaskError',
];

export function createOfficeEventStream({
  tenantId,
  onEvent,
  onResyncRequired,
  onOpen,
  onError,
}) {
  let es = null;
  const storageKey = tenantId ? `office_sse_last_event_id_${tenantId}` : null;
  let lastEventId = 0;
  if (storageKey && typeof sessionStorage !== 'undefined') {
    const saved = Number.parseInt(sessionStorage.getItem(storageKey) || '0', 10);
    if (Number.isFinite(saved) && saved > 0) {
      lastEventId = saved;
    }
  }

  function connect() {
    if (!tenantId || typeof EventSource === 'undefined') return;
    if (es) es.close();
    const qs = new URLSearchParams({ tenant_id: tenantId, last_event_id: String(lastEventId) });
    es = new EventSource(`/api/events?${qs.toString()}`);

    es.onopen = () => {
      if (onOpen) onOpen();
    };

    const handleEvent = (ev) => {
      if (ev.lastEventId) {
        const parsed = Number.parseInt(ev.lastEventId, 10);
        if (Number.isFinite(parsed)) {
          if (parsed <= lastEventId) {
            return;
          }
          lastEventId = parsed;
          if (storageKey && typeof sessionStorage !== 'undefined') {
            sessionStorage.setItem(storageKey, String(lastEventId));
          }
        }
      }
      if (onEvent) onEvent(ev);
    };

    es.onmessage = handleEvent;
    SUPPORTED_SSE_EVENTS.forEach((eventType) => {
      es.addEventListener(eventType, handleEvent);
    });

    es.addEventListener('resync_required', () => {
      if (onResyncRequired) onResyncRequired();
    });

    es.onerror = () => {
      if (onError) onError(es?.readyState ?? 2);
    };
  }

  function close() {
    if (es) {
      es.close();
      es = null;
    }
  }

  function getState() {
    return es ? es.readyState : 2;
  }

  return { connect, close, getState };
}
