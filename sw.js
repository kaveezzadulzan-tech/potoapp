const CACHE = 'fieldcam-v1';
// IMPORTANT: Add all essential assets here so they load offline
const SHELL  = ['/', '/index.html', '/manifest.json']; 

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // API calls (data) — network only, skip cache
  if (url.pathname.startsWith('/api/')) return;

  // App shell — Cache First
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))
  );
});