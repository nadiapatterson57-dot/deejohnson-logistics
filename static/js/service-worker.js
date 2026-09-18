// ============================================
// DEEJOHNSON RIDER — SERVICE WORKER
// ============================================
// This file runs in the background and:
// - Caches pages so they load instantly
// - Serves cached content when offline
// - Refreshes cache when network returns

const CACHE_NAME = 'dj-rider-v1';
const OFFLINE_URL = '/dispatch_riders/dashboard';

// Files to cache on install (the app shell)
const PRECACHE_URLS = [
    '/dispatch_riders/dashboard',
    '/dispatch_riders/history',
    '/dispatch_riders/profile',
    '/static/manifest.json',
    '/static/js/service-worker.js',
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css',
    'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap'
];

// ============================================
// INSTALL — Cache the app shell
// ============================================
self.addEventListener('install', event => {
    console.log('[SW] Installing service worker...');

    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => {
                console.log('[SW] Caching app shell');
                return cache.addAll(PRECACHE_URLS).catch(err => {
                    // Don't fail the whole install if some URLs can't be cached
                    console.warn('[SW] Some URLs failed to cache:', err);
                });
            })
            .then(() => self.skipWaiting())
    );
});

// ============================================
// ACTIVATE — Clean up old caches
// ============================================
self.addEventListener('activate', event => {
    console.log('[SW] Activating service worker...');

    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames
                    .filter(name => name !== CACHE_NAME)
                    .map(name => {
                        console.log('[SW] Deleting old cache:', name);
                        return caches.delete(name);
                    })
            );
        }).then(() => self.clients.claim())
    );
});

// ============================================
// FETCH — Serve from cache, fall back to network
// ============================================
self.addEventListener('fetch', event => {
    const { request } = event;

    // Only handle GET requests
    if (request.method !== 'GET') return;

    // Don't cache API calls — always fetch fresh
    if (request.url.includes('/api/')) {
        event.respondWith(
            fetch(request).catch(() => {
                return new Response(JSON.stringify({
                    error: 'You are offline',
                    offline: true
                }), {
                    headers: { 'Content-Type': 'application/json' }
                });
            })
        );
        return;
    }

    // For everything else: try cache first, then network
    event.respondWith(
        caches.match(request).then(cached => {
            if (cached) {
                // Serve from cache AND update in background
                const fetchPromise = fetch(request).then(response => {
                    if (response && response.status === 200) {
                        const copy = response.clone();
                        caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
                    }
                    return response;
                }).catch(() => cached);

                return cached;
            }

            // Not in cache — fetch from network
            return fetch(request).then(response => {
                // Cache successful responses
                if (response && response.status === 200 && response.type === 'basic') {
                    const copy = response.clone();
                    caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
                }
                return response;
            }).catch(() => {
                // Network failed and not in cache
                if (request.headers.get('accept')?.includes('text/html')) {
                    return caches.match(OFFLINE_URL);
                }
            });
        })
    );
});

// ============================================
// MESSAGE — Handle messages from the app
// ============================================
self.addEventListener('message', event => {
    if (event.data === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});