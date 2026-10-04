/* Reps & Greens service worker: makes the app installable and opens it offline.
   Pages are network-first (always the newest version when online); icons are cached;
   API calls are never cached. */
const V = 'rng-v12';
const SHELL = ['/app', '/static/manifest.json', '/static/icon-192.png', '/static/icon-512.png', '/static/favicon-32.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(V).then(c => c.addAll(SHELL)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  const r = e.request;
  if (r.method !== 'GET') return;
  const u = new URL(r.url);
  if (u.origin !== location.origin) return;            // photos, fonts: straight to the network
  if (r.mode === 'navigate') {                          // pages: newest first, cached copy when offline
    e.respondWith(fetch(r).then(res => {
      const copy = res.clone(); caches.open(V).then(c => c.put(r, copy)); return res;
    }).catch(() => caches.match(r).then(m => m || caches.match('/app'))));
    return;
  }
  if (u.pathname.startsWith('/static/')) {              // icons and manifest: cache first
    e.respondWith(caches.match(r).then(m => m || fetch(r).then(res => {
      const copy = res.clone(); caches.open(V).then(c => c.put(r, copy)); return res;
    })));
  }
});
