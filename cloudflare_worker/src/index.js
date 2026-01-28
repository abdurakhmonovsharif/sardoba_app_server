const TARGET_ORIGIN = "https://api-ru.iiko.services";
const MAX_CONCURRENCY = 2;
const MAX_QUEUE_SIZE = 50;

const unauthorized = () => new Response("Unauthorized", { status: 401 });
const overflow = () => new Response("Queue limit exceeded", { status: 503 });

async function timingSafeEqual(a, b) {
  const encoder = new TextEncoder();
  const digestA = await crypto.subtle.digest("SHA-256", encoder.encode(a || ""));
  const digestB = await crypto.subtle.digest("SHA-256", encoder.encode(b || ""));
  const viewA = new Uint8Array(digestA);
  const viewB = new Uint8Array(digestB);
  if (viewA.length !== viewB.length) {
    return false;
  }
  let diff = 0;
  for (let i = 0; i < viewA.length; i += 1) {
    diff |= viewA[i] ^ viewB[i];
  }
  return diff === 0;
}

async function verifySecret(request, expected) {
  if (!expected) {
    return false;
  }
  const provided = request.headers.get("x-iiko-proxy-secret") || "";
  return timingSafeEqual(provided, expected);
}

function headerEntriesWithoutSecret(originalHeaders) {
  const filtered = new Headers();
  for (const [key, value] of originalHeaders.entries()) {
    const lower = key.toLowerCase();
    if (lower === "x-iiko-proxy-secret" || lower === "host") {
      continue;
    }
    filtered.set(key, value);
  }
  return Array.from(filtered.entries());
}

export default {
  async fetch(request, env) {
    if (!(await verifySecret(request, env.PROXY_SECRET))) {
      return unauthorized();
    }
    const queueId = env.IIKO_QUEUE.idFromName("global");
    const stub = env.IIKO_QUEUE.get(queueId);
    return stub.fetch(request);
  },
};

export class IikoQueue {
  constructor(state, env) {
    this.state = state;
    this.env = env;
    this.inflight = 0;
    this.queue = [];
  }

  async fetch(request) {
    if (!(await verifySecret(request, this.env.PROXY_SECRET))) {
      return unauthorized();
    }

    if (this.queue.length >= MAX_QUEUE_SIZE) {
      return overflow();
    }

    const url = new URL(request.url);
    const target = new URL(url.pathname + url.search, TARGET_ORIGIN).toString();
    const method = request.method || "GET";
    const headers = headerEntriesWithoutSecret(request.headers);
    const body =
      method === "GET" || method === "HEAD" || method === "OPTIONS"
        ? undefined
        : await request.arrayBuffer();

    return this.enqueue({ target, method, headers, body });
  }

  enqueue(job) {
    return new Promise((resolve) => {
      this.queue.push({ job, resolve });
      this.drain();
    });
  }

  drain() {
    while (this.inflight < MAX_CONCURRENCY && this.queue.length) {
      const next = this.queue.shift();
      this.inflight += 1;
      this.process(next.job)
        .then(next.resolve)
        .catch((err) => {
          console.error("iiko_proxy_upstream_error", err);
          next.resolve(new Response("Upstream error", { status: 502 }));
        })
        .finally(() => {
          this.inflight -= 1;
          this.drain();
        });
    }
  }

  async process(job) {
    const upstream = await fetch(job.target, {
      method: job.method,
      headers: new Headers(job.headers),
      body: job.body,
    });
    const payload = await upstream.arrayBuffer();
    const responseHeaders = new Headers(upstream.headers);
    return new Response(payload, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    });
  }
}
