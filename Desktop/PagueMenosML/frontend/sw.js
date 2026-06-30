const CACHE = 'paguemenos-v2';
const ASSETS = ['/', '/style.css', '/app.js', '/logo_transparent.png', '/ml_logo.png', '/icon-192.png', '/icon-512.png', '/icon-1024.png'];

self.addEventListener('install', e => {
    e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)));
    self.skipWaiting();
});

self.addEventListener('activate', e => {
    e.waitUntil(caches.keys().then(keys =>
        Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ));
    self.clients.claim();
});

self.addEventListener('fetch', e => {
    const url = new URL(e.request.url);

    // Requisições de API sempre vão para a rede
    if (url.pathname.startsWith('/api/')) {
        e.respondWith(fetch(e.request).catch(() => new Response('{"erro":"offline"}', {
            headers: { 'Content-Type': 'application/json' }
        })));
        return;
    }

    // Assets estáticos: cache primeiro, rede como fallback
    e.respondWith(
        caches.match(e.request).then(cached => cached || fetch(e.request))
    );
});
