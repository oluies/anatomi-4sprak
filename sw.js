// Cache-first service worker med bakgrundsuppdatering (stale-while-revalidate).
// Sidan visas alltid direkt från cachen, men hämtas samtidigt i bakgrunden så att
// nästa besök får den senaste versionen utan att någon behöver röra den här filen.
// CACHE-nyckeln är versionerad: höj den för att tvinga fram en total omladdning.
const CACHE = "anatomi-4sprak-v1";

// Endast skalet precachas. Deck-filen (~450 kB) laddas bara om användaren begär
// den, och cachas då av fetch-hanteraren nedan.
const SHELL = [
  "./",
  "./index.html",
  "./manifest.webmanifest"
];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE)
      // addAll är atomiskt: cacha en fil i taget så att ett enskilt fel inte
      // lämnar besökaren helt utan offlinestöd.
      .then(cache => Promise.all(SHELL.map(url => cache.add(url).catch(() => {}))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const req = event.request;
  if (req.method !== "GET") return;

  let url;
  try {
    url = new URL(req.url);
  } catch {
    return;
  }
  if (url.origin !== self.location.origin) return;

  event.respondWith(
    caches.open(CACHE).then(cache =>
      cache.match(req).then(hit => {
        const network = fetch(req).then(res => {
          if (res && res.ok && res.type === "basic") cache.put(req, res.clone());
          return res;
        }).catch(() => null);

        // Cache-first: svara direkt från cachen och uppdatera den i bakgrunden.
        if (hit) {
          event.waitUntil(network);
          return hit;
        }
        return network.then(res => res || cache.match("./index.html"));
      })
    )
  );
});
