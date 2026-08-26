export type ForgeClientOptions = {
  baseUrl: string;
  apiKey?: string;
  bearerToken?: string;
  timeoutMs?: number;
  maxResponseBytes?: number;
  allowHttpForLoopback?: boolean;
  fetchImpl?: typeof fetch;
};

export type ForgeRequestOptions = {
  body?: unknown;
  query?: Record<string, string | number | boolean | null | undefined>;
  headers?: Record<string, string>;
  signal?: AbortSignal;
};

export class ForgeAPIError extends Error {
  readonly status: number;
  readonly payload: unknown;
  readonly requestId?: string;

  constructor(status: number, payload: unknown, requestId?: string) {
    super(`Forge API error ${status}`);
    this.name = "ForgeAPIError";
    this.status = status;
    this.payload = payload;
    this.requestId = requestId;
  }
}

function isLoopback(hostname: string): boolean {
  const host = hostname.toLowerCase();
  return host === "localhost" || host === "[::1]" || /^127(?:\.\d{1,3}){3}$/.test(host);
}

function decodedSegments(pathname: string): string[] {
  try {
    return decodeURIComponent(pathname).split("/");
  } catch {
    throw new TypeError("URL path contains invalid percent encoding");
  }
}

function segment(value: string | number, label: string): string {
  const text = String(value);
  if (!text || text === "." || text === ".." || /[\/\\\0\r\n]/.test(text)) {
    throw new TypeError(`${label} must be one non-empty URL path segment`);
  }
  return encodeURIComponent(text);
}

async function boundedBody(response: Response, limit: number): Promise<string> {
  const declaredLength = Number(response.headers.get("content-length"));
  if (Number.isFinite(declaredLength) && declaredLength > limit) {
    await response.body?.cancel();
    throw new ForgeAPIError(response.status, "response exceeded the configured size limit");
  }
  if (!response.body) {
    return "";
  }

  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    total += value.byteLength;
    if (total > limit) {
      await reader.cancel();
      throw new ForgeAPIError(response.status, "response exceeded the configured size limit");
    }
    chunks.push(value);
  }

  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder().decode(bytes);
}

export class ForgeClient {
  readonly baseUrl: string;
  readonly timeoutMs: number;
  readonly maxResponseBytes: number;
  private readonly base: URL;
  private readonly basePath: string;
  private readonly apiKey?: string;
  private readonly bearerToken?: string;
  private readonly fetchImpl: typeof fetch;

  constructor(options: ForgeClientOptions) {
    if (options.baseUrl.includes("\\") || /(?:\/|^)(?:(?:\.|%2e){1,2})(?:\/|$)/i.test(options.baseUrl)) {
      throw new TypeError("baseUrl contains an unsafe path segment");
    }
    const base = new URL(options.baseUrl);
    const allowLoopbackHttp = options.allowHttpForLoopback === true && base.protocol === "http:" && isLoopback(base.hostname);
    if (
      (base.protocol !== "https:" && !allowLoopbackHttp) ||
      base.username ||
      base.password ||
      base.search ||
      base.hash ||
      decodedSegments(base.pathname).some((part) => part === "." || part === "..")
    ) {
      throw new TypeError(
        "baseUrl must be HTTPS without credentials/query/fragment/traversal; HTTP is explicit and loopback-only",
      );
    }
    if (options.apiKey && options.bearerToken) {
      throw new TypeError("configure either apiKey or bearerToken, not both");
    }
    if (/[\r\n]/.test(options.apiKey ?? "") || /[\r\n]/.test(options.bearerToken ?? "")) {
      throw new TypeError("credentials may not contain line breaks");
    }

    this.timeoutMs = options.timeoutMs ?? 10_000;
    this.maxResponseBytes = options.maxResponseBytes ?? 4 * 1024 * 1024;
    if (this.timeoutMs <= 0 || this.maxResponseBytes < 1024) {
      throw new RangeError("timeoutMs and maxResponseBytes must be positive");
    }
    const basePath = base.pathname.replace(/\/+$/, "");
    base.pathname = basePath;
    this.base = base;
    this.basePath = basePath;
    this.baseUrl = `${base.origin}${basePath}`;
    this.apiKey = options.apiKey;
    this.bearerToken = options.bearerToken;
    this.fetchImpl = options.fetchImpl ?? fetch;
  }

  async request<T = unknown>(method: string, path: string, options: ForgeRequestOptions = {}): Promise<T> {
    if (!path.startsWith("/") || path.includes("\\") || path.includes("?") || path.includes("#")) {
      throw new TypeError("path must be an origin-relative path without query, fragment, or backslash");
    }
    const relative = path.replace(/^\/+/, "");
    if (decodedSegments(relative).some((part) => part === "." || part === "..")) {
      throw new TypeError("path may not contain traversal segments");
    }
    const url = new URL(`${this.baseUrl}/${relative}`);
    if (url.origin !== this.base.origin || !url.pathname.startsWith(`${this.basePath}/`)) {
      throw new TypeError("request URL escaped the configured Forge base path");
    }
    for (const [key, value] of Object.entries(options.query ?? {})) {
      if (value !== null && value !== undefined) {
        url.searchParams.set(key, String(value));
      }
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);
    const onAbort = () => controller.abort(options.signal?.reason);
    if (options.signal?.aborted) {
      onAbort();
    } else {
      options.signal?.addEventListener("abort", onAbort, { once: true });
    }
    const headers = new Headers(options.headers);
    headers.set("Accept", "application/json");
    if (this.apiKey) {
      headers.set("X-API-Key", this.apiKey);
    }
    if (this.bearerToken) {
      headers.set("Authorization", `Bearer ${this.bearerToken}`);
    }
    let body: BodyInit | undefined;
    if (options.body !== undefined) {
      headers.set("Content-Type", "application/json");
      body = JSON.stringify(options.body);
    }

    try {
      const response = await this.fetchImpl(url, {
        method,
        headers,
        body,
        redirect: "manual",
        signal: controller.signal,
      });
      const text = await boundedBody(response, this.maxResponseBytes);
      let payload: unknown = text;
      if (text && response.headers.get("content-type")?.toLowerCase().includes("application/json")) {
        try {
          payload = JSON.parse(text);
        } catch {
          throw new ForgeAPIError(response.status, "server returned invalid JSON");
        }
      }
      if (!response.ok || response.type === "opaqueredirect" || (response.status >= 300 && response.status < 400)) {
        throw new ForgeAPIError(response.status, payload, response.headers.get("x-request-id") ?? undefined);
      }
      return payload as T;
    } finally {
      clearTimeout(timeout);
      options.signal?.removeEventListener("abort", onAbort);
    }
  }

  rpc<T = unknown>(name: string, payload: unknown = {}, idempotencyKey?: string): Promise<T> {
    return this.request<T>("POST", `/rpc/${segment(name, "operation name")}`, {
      body: payload,
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
    });
  }

  list<T = unknown>(
    resource: string,
    query?: Record<string, string | number | boolean | null | undefined>,
  ): Promise<T> {
    return this.request<T>("GET", `/${segment(resource, "resource")}`, { query });
  }

  get<T = unknown>(resource: string, id: string | number): Promise<T> {
    return this.request<T>("GET", `/${segment(resource, "resource")}/${segment(id, "item id")}`);
  }

  create<T = unknown>(resource: string, payload: unknown): Promise<T> {
    return this.request<T>("POST", `/${segment(resource, "resource")}`, { body: payload });
  }

  update<T = unknown>(resource: string, id: string | number, payload: unknown): Promise<T> {
    return this.request<T>("PATCH", `/${segment(resource, "resource")}/${segment(id, "item id")}`, { body: payload });
  }

  delete<T = unknown>(resource: string, id: string | number): Promise<T> {
    return this.request<T>("DELETE", `/${segment(resource, "resource")}/${segment(id, "item id")}`);
  }
}
