// service-worker.js

const CACHE_NAME = 'tot-time-cache-v1';
const urlsToCache = [
  '/',
  '/index.html',   // Replace with your homepage or root page
  '/static/pwa/logo.png',  // Include your logo or other essential files
  '/static/css/styles.css',  // Include your CSS or JS files
];

// Install the service worker and cache essential files
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('Opened cache');
        return cache.addAll(urlsToCache);
      })
  );
});

// Fetch files from cache when offline
self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request)
      .then((cachedResponse) => {
        // Return cached response if available, otherwise fetch from network
        return cachedResponse || fetch(event.request);
      })
  );
});

// Activate service worker and remove old caches
self.addEventListener('activate', (event) => {
  const cacheWhitelist = [CACHE_NAME];
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (!cacheWhitelist.includes(cacheName)) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
});
