export type ForgeClientOptions = {
  /** Base URL should normally include the project API prefix, e.g. https://api.example.com/api/app1/v1 */
  baseUrl: string;
  apiKey?: string;
  bearerToken?: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
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

export class ForgeClient {
  readonly baseUrl: string;
  readonly timeoutMs: number;
  private readonly apiKey?: string;
  private readonly bearerToken?: string;
  private readonly fetchImpl: typeof fetch;

  constructor(options: ForgeClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.apiKey = options.apiKey;
    this.bearerToken = options.bearerToken;
    this.timeoutMs = options.timeoutMs ?? 10_000;
    this.fetchImpl = options.fetchImpl ?? fetch;
  }

  async request<T = unknown>(
    method: string,
    path: string,
    options: {
      body?: unknown;
      query?: Record<string, string | number | boolean | null | undefined>;
      headers?: Record<string, string>;
      signal?: AbortSignal;
    } = {},
  ): Promise<T> {
    const url = new URL(`${this.baseUrl}/${path.replace(/^\//, "")}`);
    for (const [key, value] of Object.entries(options.query ?? {})) {
      if (value !== null && value !== undefined) url.searchParams.set(key, String(value));
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);
    const onAbort = () => controller.abort();
    options.signal?.addEventListener("abort", onAbort, { once: true });

    const headers = new Headers(options.headers);
    headers.set("Accept", "application/json");
    if (this.apiKey) headers.set("X-API-Key", this.apiKey);
    if (this.bearerToken) headers.set("Authorization", `Bearer ${this.bearerToken}`);

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
        signal: controller.signal,
      });
      const contentType = response.headers.get("content-type") ?? "";
      const payload: unknown = contentType.includes("application/json")
        ? await response.json()
        : await response.text();
      if (!response.ok) {
        throw new ForgeAPIError(response.status, payload, response.headers.get("x-request-id") ?? undefined);
      }
      return payload as T;
    } finally {
      clearTimeout(timeout);
      options.signal?.removeEventListener("abort", onAbort);
    }
  }

  rpc<T = unknown>(name: string, payload: unknown = {}, idempotencyKey?: string): Promise<T> {
    return this.request<T>("POST", `/rpc/${name}`, {
      body: payload,
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
    });
  }

  list<T = unknown>(resource: string, query?: Record<string, string | number | boolean | null | undefined>): Promise<T> {
    return this.request<T>("GET", `/${resource.replace(/^\//, "")}`, { query });
  }

  get<T = unknown>(resource: string, id: string | number): Promise<T> {
    return this.request<T>("GET", `/${resource.replace(/^\//, "")}/${encodeURIComponent(String(id))}`);
  }

  create<T = unknown>(resource: string, payload: unknown): Promise<T> {
    return this.request<T>("POST", `/${resource.replace(/^\//, "")}`, { body: payload });
  }

  update<T = unknown>(resource: string, id: string | number, payload: unknown): Promise<T> {
    return this.request<T>("PATCH", `/${resource.replace(/^\//, "")}/${encodeURIComponent(String(id))}`, { body: payload });
  }

  delete<T = unknown>(resource: string, id: string | number): Promise<T> {
    return this.request<T>("DELETE", `/${resource.replace(/^\//, "")}/${encodeURIComponent(String(id))}`);
  }
}
