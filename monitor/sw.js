/* Open-app notifications only: no push subscription, background polling, or API/tile cache. */
const ALERT_PATH = '/?view=alerts';
const RECEIPT_DB = 'lowsky-notification-receipts';
let database;
let deliveryQueue = Promise.resolve();

self.addEventListener('install', event => event.waitUntil(self.skipWaiting()));
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));

function receipts() {
  if (!database) database = new Promise((resolve, reject) => {
    const request = indexedDB.open(RECEIPT_DB, 1);
    request.onupgradeneeded = () => request.result.createObjectStore('receipts', {keyPath: 'id'});
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => { database = null; reject(request.error || new Error('Notification receipt storage failed')); };
  });
  return database;
}

async function claim(runId, alertIds) {
  const db = await receipts();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction('receipts', 'readwrite');
    const store = transaction.objectStore('receipts'), claimed = [];
    for (const alertId of alertIds) {
      const id = JSON.stringify([runId, alertId]);
      const request = store.get(id);
      request.onsuccess = () => {
        if (!request.result) { store.put({id, createdAt: Date.now()}); claimed.push({id, alertId}); }
      };
    }
    // Retain recent runs across worker restarts without accumulating receipts forever.
    const cursor = store.openCursor();
    cursor.onsuccess = () => {
      const entry = cursor.result;
      if (!entry) return;
      if (entry.value.createdAt < Date.now() - 7 * 86400000) entry.delete();
      entry.continue();
    };
    transaction.oncomplete = () => resolve(claimed);
    transaction.onerror = transaction.onabort = () => reject(transaction.error || new Error('Notification receipt storage failed'));
  });
}

async function release(claimed) {
  const db = await receipts();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction('receipts', 'readwrite');
    for (const item of claimed) transaction.objectStore('receipts').delete(item.id);
    transaction.oncomplete = resolve;
    transaction.onerror = transaction.onabort = () => reject(transaction.error || new Error('Notification receipt rollback failed'));
  });
}

async function notify(event) {
  const {data, source} = event;
  if (!source?.id) throw new Error('Notification sender is not a window client');
  const client = await self.clients.get(source.id);
  if (!client || client.type !== 'window' || new URL(client.url).origin !== self.location.origin)
    throw new Error('Notification sender must be a local window');
  if (typeof data.runId !== 'string' || !data.runId || data.runId.length > 128 ||
      !Array.isArray(data.alertIds) || data.alertIds.length < 1 || data.alertIds.length > 500 ||
      data.alertIds.some(id => typeof id !== 'string' || !id || id.length > 512) ||
      typeof data.title !== 'string' || !data.title || data.title.length > 160 ||
      typeof data.body !== 'string' || data.body.length > 1000)
    throw new Error('Invalid notification payload');
  const claimed = await claim(data.runId, [...new Set(data.alertIds)]);
  if (!claimed.length) return {ok: true, status: 'duplicate', count: 0};
  try {
    await self.registration.showNotification(data.title, {body: data.body,
      tag: `lowsky:${data.runId}`, icon: '/logo-metal.png', badge: '/logo-metal.png',
      data: {view: 'alerts'}, renotify: false});
  } catch (error) { await release(claimed); throw error; }
  return {ok: true, status: 'sent', count: claimed.length};
}

self.addEventListener('message', event => {
  if (event.data?.type !== 'notify-alerts') return;
  const reply = value => event.ports?.[0]?.postMessage(value);
  const operation = deliveryQueue.then(() => notify(event))
    .then(reply, error => reply({ok: false, error: error?.message || 'Notification delivery failed'}));
  deliveryQueue = operation.catch(() => {});
  event.waitUntil(operation);
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil((async () => {
    const clients = await self.clients.matchAll({type: 'window', includeUncontrolled: true});
    const client = clients.find(item => new URL(item.url).origin === self.location.origin && new URL(item.url).pathname === '/');
    if (client) { await client.focus(); client.postMessage({type: 'open-alerts'}); }
    else await self.clients.openWindow(ALERT_PATH);
  })());
});
