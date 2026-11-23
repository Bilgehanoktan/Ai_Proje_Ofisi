'use strict';
const $ = id => document.getElementById(id);
const pendingKey = 'aipof.pending-objective';
const receiptKey = 'aipof.last-command';
const pendingOperationKey = 'aipof.pending-operation';
const routes = {'objectives.create':'/api/objectives', 'plans.create':'/api/plans', 'tasks.create':'/api/tasks'};
const labels = {'objectives.create':'İş isteği', 'plans.create':'Plan', 'tasks.create':'Görev'};
let configured = false;
let operations = [];
let uncertain = sessionStorage.getItem(pendingKey);
let pendingOperation = sessionStorage.getItem(pendingOperationKey) || 'objectives.create';
let busy = false;
const lines = id => $(id).value.split('\n').map(value => value.trim()).filter(Boolean);
function selectOperation() {
  const operation = $('operation').value;
  for (const [name, op] of [['objective','objectives.create'], ['plan','plans.create'], ['task','tasks.create']]) {
    $(name+'-fields').hidden = operation !== op;
    $(name+'-fields').disabled = operation !== op;
  }
}
function showPending(id) {
  $('feedback').textContent = 'Bu isteğin kaydedilip kaydedilmediği henüz bilinmiyor. Aynı işi yeniden göndermeden önce kayıt durumu kontrol edilmeli.';
  $('request-ref').hidden = false;
  $('request-ref').textContent = 'İstek numarası: ' + id;
  $('request-fields').disabled = true;
  $('receipt-request').value = id;
  $('receipt-operation').value = pendingOperation;
}
function clearPending() {
  uncertain = null;
  sessionStorage.removeItem(pendingKey);
  sessionStorage.removeItem(pendingOperationKey);
  $('request-ref').hidden = true;
  $('request-fields').disabled = operations.length === 0;
}
function showReceipt(value, operation, requestId) {
  const receipt = value.command_receipt;
  if (value.semantics !== 'AUTHORIZED_FACT_NOT_CURRENT_STATE' || !receipt ||
      receipt.state !== 'SUCCEEDED' || !receipt.command_id || !receipt.result_ref ||
      receipt.correlation_id !== requestId) throw new Error('Invalid receipt');
  $('receipt').hidden = false;
  $('receipt-id').textContent = receipt.command_id;
  $('result-ref').textContent = receipt.result_ref;
  $('receipt-command').value = receipt.command_id;
  $('receipt-request').value = requestId;
  $('receipt-operation').value = operation;
  sessionStorage.setItem(receiptKey, JSON.stringify({operation, request_id:requestId, command_id:receipt.command_id}));
  $('request-state').textContent = labels[operation] + ' kaydedildi. Ajanın çalışmasına ilişkin kayıt henüz gösterilmedi.';
  $('stage-request').classList.add('recorded');
}
async function post(path, body) {
  const response = await fetch(path, {method:'POST', credentials:'omit', cache:'no-store',
    headers:{'Content-Type':'application/json','Authorization':'Bearer '+$('session').value},
    body:JSON.stringify(body)});
  return {ok:response.ok, code:response.status, value:await response.json()};
}
async function initialize() {
  try {
    const response = await fetch('/api/connection', {cache:'no-store'});
    if (!response.ok) throw new Error();
    const state = await response.json();
    configured = state.configured === true;
    operations = configured && Array.isArray(state.create_operations)
      ? state.create_operations.filter(operation => Object.hasOwn(routes,operation)) : [];
    for (const select of [$('operation'), $('receipt-operation')]) {
      for (const option of select.options) option.disabled = !operations.includes(option.value);
    }
    if (operations.length) $('operation').value = operations[0];
    selectOperation();
    const resources = Array.isArray(state.detail_resources) ? state.detail_resources : [];
    for (const option of $('resource').options) option.disabled = !resources.includes(option.value);
    const readable = [...$('resource').options].find(option => !option.disabled);
    if (readable) $('resource').value = readable.value;
    $('connection').textContent = configured ? 'Görev bağlantısı tanımlı' : 'Görev altyapısı bağlı değil';
    $('availability').textContent = operations.length
      ? 'Yetkili oturumunla kayıt gönderebilirsin. Kaydın alınması, işin başladığı anlamına gelmez.'
      : 'Bu bağlantıda yeni kayıt gönderimi açık değil.';
    $('request-fields').disabled = !operations.length || !!uncertain;
    $('read-fields').disabled = !configured || !readable;
    $('receipt-fields').disabled = !operations.length;
    const last = JSON.parse(sessionStorage.getItem(receiptKey) || 'null');
    if (last && Object.hasOwn(routes,last.operation)) {
      $('receipt-operation').value = last.operation;
      $('receipt-request').value = last.request_id;
      $('receipt-command').value = last.command_id;
      $('receipt-feedback').textContent = 'Önceki komut numarası bulundu. Kayıt içeriği ve yetkisi yeniden sorgulanmalı.';
    }
  } catch (_) {
    configured = false;
    operations = [];
    $('request-fields').disabled = true;
    $('read-fields').disabled = true;
    $('receipt-fields').disabled = true;
    $('connection').textContent = 'Bağlantı kurulamadı';
    $('availability').textContent = 'Sunucuya ulaşılamıyor. Bağlantı gelene kadar yeni istek gönderilemez.';
  }
  if (uncertain) showPending(uncertain);
}
$('operation').addEventListener('change', selectOperation);
$('request-form').addEventListener('submit', async event => {
  event.preventDefault();
  const operation = $('operation').value;
  if (!operations.includes(operation) || uncertain || busy) return;
  const id = crypto.randomUUID();
  let body;
  if (operation === 'objectives.create') {
    body = {goal:$('goal').value.trim(), constraints:[$('constraints').value.trim()], expected_outputs:[$('outputs').value.trim()]};
  } else if (operation === 'plans.create') {
    const revision = Number($('project-revision').value);
    if (!Number.isSafeInteger(revision) || revision < 0) return;
    body = {objective_id:$('objective-id').value.trim(), expected_revision:revision,
      assumptions:lines('assumptions'), acceptance_criteria:lines('plan-criteria')};
  } else {
    body = {plan_id:$('plan-id').value.trim(), title:$('task-title').value.trim(),
      role_id:$('role-id').value.trim(), acceptance_criteria:lines('task-criteria'), depends_on:lines('dependencies')};
  }
  // Only operation and identifiers persist. Never store token or request content.
  uncertain = id;
  pendingOperation = operation;
  sessionStorage.setItem(pendingKey,id);
  sessionStorage.setItem(pendingOperationKey,operation);
  body.request_id = id;
  busy = true;
  $('request-fields').disabled = true;
  $('feedback').textContent = 'İstek gönderiliyor…';
  try {
    const response = await post(routes[operation],body);
    if (!response.ok) {
      if (response.code === 409 || response.code >= 500) {showPending(id); return;}
      clearPending();
      $('feedback').textContent = response.code === 401 ? 'Geçerli bir oturum anahtarı gerekli.'
        : response.code === 403 ? 'Bu işlem için yetki doğrulanamadı. Kayıt başarılı gösterilmedi.'
        : 'İstek gönderilemedi. Alanları kontrol et.';
      return;
    }
    showReceipt(response.value, operation, id);
    clearPending();
    $('feedback').textContent = labels[operation] + ' kaydedildi. Henüz tamamlanmış bir iş veya teslim yok.';
  } catch (_) {showPending(id);}
  finally {busy = false; $('session').value='';}
});
$('receipt-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (!configured || busy) return;
  const operation = $('receipt-operation').value;
  const requestId = $('receipt-request').value.trim();
  const commandId = $('receipt-command').value.trim();
  busy = true;
  $('receipt-fields').disabled = true;
  try {
    const response = await post('/api/receipts', {operation, request_id:requestId, command_id:commandId});
    if (!response.ok || response.value.command_receipt?.command_id !== commandId) throw new Error();
    showReceipt(response.value, operation, requestId);
    if (uncertain === requestId && pendingOperation === operation) clearPending();
    $('receipt-feedback').textContent = 'Kalıcı makbuz yeniden okundu. Yeni komut gönderilmedi.';
  } catch (_) {
    $('receipt-feedback').textContent = 'Makbuz doğrulanamadı. Oturumu ve numaraları kontrol et. Belirsiz istek yeniden gönderilmedi.';
  } finally {
    busy = false;
    $('session').value = '';
    $('receipt-fields').disabled = !operations.length;
  }
});
$('read-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (!configured || busy) return;
  busy = true;
  $('record').hidden = true;
  $('read-feedback').textContent = 'Kayıt sorgulanıyor…';
  try {
    const response = await post('/api/details',{resource:$('resource').value,
      task_id:$('task-id').value.trim(), record_id:$('record-id').value.trim(),
      attempt_id:null, expected_digest:null, ui_generation:0});
    if (!response.ok) throw new Error();
    if (response.value.semantics !== 'AUTHORIZED_FACT_NOT_CURRENT_STATE' || !response.value.result?.record) throw new Error();
    const record=response.value.result.record;
    const states={DRAFT:'Taslak',READY:'Çalışmaya hazır',RUNNING:'Çalışıyor',WAITING_APPROVAL:'Onay bekliyor',
      VERIFYING:'Sonuç kontrol ediliyor',CHANGES_REQUIRED:'Düzeltme gerekiyor',BLOCKED:'Bir engel nedeniyle durdu',
      ACCEPTED:'Kabul edildi',FAILED:'Başarısız oldu',CANCELLED:'İptal edildi',PRODUCED:'Çıktı üretildi. Kabul sonucu ayrıca kontrol edilmeli.'};
    $('record-state').textContent=Object.hasOwn(states,record.state) ? states[record.state] : 'Bu kayıtta açıklanmış bir çalışma durumu bulunmuyor.';
    $('record-title').textContent=typeof record.title==='string' ? record.title : '';
    $('record-raw').textContent=JSON.stringify(record,null,2);
    $('record').hidden=false;
    $('read-feedback').textContent='Kayıt yeniden okundu. Bu sonuç sorgu anına aittir; canlı çalışma göstergesi değildir.';
  } catch (_) {$('read-feedback').textContent='Kayıt alınamadı. Başarılı bir sonuç gösterilmiyor.';}
  finally {busy = false; $('session').value='';}
});
initialize();
