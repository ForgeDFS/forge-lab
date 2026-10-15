// FORGE DFS Lab service worker (2026-10-15): receives a DraftKings entries file shared from Android's Share menu (Web Share Target),
// keeps it in a cache, and opens the site on the To DraftKings tab. Pages are always fetched from the network (no offline copy, no stale data).
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (e.request.method === 'POST' && u.pathname.endsWith('/share')) {
    e.respondWith((async () => {
      try {
        const fd = await e.request.formData();
        const f = fd.get('dkfile') || [...fd.values()].find(v => typeof v === 'object' && v && 'text' in v);
        const txt = f ? await f.text() : (fd.get('text') || '');
        const c = await caches.open('forge-share');
        await c.put('shared-entries', new Response(String(txt), { headers: { 'content-type': 'text/csv', 'x-name': (f && f.name) || '' } }));
      } catch (err) { /* page shows the normal picker if nothing was stored */ }
      return Response.redirect(new URL('./?shared=1', self.registration.scope).href, 303);
    })());
  }
});
