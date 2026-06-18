/**
 * WHOOP v2 API client (TypeScript).
 *
 * Handles bearer auth with automatic refresh-token rotation, plus the v2 data
 * endpoints. Designed for use from a backend / dashboard server where the
 * client ID + secret are available as env vars (resolve via tools/load-env.sh).
 *
 * For the initial browser OAuth handshake, the Python CLI is the easiest path
 * (`python -m whoop.cli auth`); this TS client then consumes the cached token
 * or a token you obtain server-side. See lib/ts/whoop/README isn't written yet,
 * see lib/py/whoop/README.md for the full flow.
 */

const BASE_URL = "https://api.prod.whoop.com/developer/v2";
const TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token";

export interface Token {
  access_token: string;
  refresh_token: string;
  /** unix epoch seconds */
  expires_at: number;
  scope?: string;
  token_type?: string;
}

export interface Paginated<T> {
  records: T[];
  next_token?: string | null;
}

export interface WhoopClientOptions {
  clientId: string;
  clientSecret: string;
  token: Token;
  /** Called whenever the token is refreshed so callers can persist it. */
  onTokenRefresh?: (token: Token) => void | Promise<void>;
}

export class WhoopClient {
  private clientId: string;
  private clientSecret: string;
  private token: Token;
  private onTokenRefresh?: (token: Token) => void | Promise<void>;

  constructor(opts: WhoopClientOptions) {
    this.clientId = opts.clientId;
    this.clientSecret = opts.clientSecret;
    this.token = opts.token;
    this.onTokenRefresh = opts.onTokenRefresh;
  }

  static fromEnv(token: Token, onTokenRefresh?: (t: Token) => void | Promise<void>): WhoopClient {
    const clientId = process.env.WHOOP_CLIENT_ID;
    const clientSecret = process.env.WHOOP_CLIENT_SECRET;
    if (!clientId || !clientSecret) {
      throw new Error(
        "WHOOP_CLIENT_ID / WHOOP_CLIENT_SECRET not set. Run via tools/load-env.sh.",
      );
    }
    return new WhoopClient({ clientId, clientSecret, token, onTokenRefresh });
  }

  private expired(): boolean {
    return Date.now() / 1000 >= this.token.expires_at - 60;
  }

  private async refresh(): Promise<void> {
    const resp = await fetch(TOKEN_URL, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "refresh_token",
        refresh_token: this.token.refresh_token,
        client_id: this.clientId,
        client_secret: this.clientSecret,
        scope: "offline",
      }),
    });
    if (!resp.ok) {
      throw new Error(`token refresh failed: ${resp.status} ${await resp.text()}`);
    }
    const data = (await resp.json()) as {
      access_token: string;
      refresh_token: string;
      expires_in: number;
      scope?: string;
      token_type?: string;
    };
    this.token = {
      access_token: data.access_token,
      refresh_token: data.refresh_token,
      expires_at: Date.now() / 1000 + data.expires_in,
      scope: data.scope,
      token_type: data.token_type,
    };
    await this.onTokenRefresh?.(this.token);
  }

  private async get<T>(path: string, params?: Record<string, string | number>): Promise<T> {
    if (this.expired()) await this.refresh();
    const url = new URL(BASE_URL + path);
    for (const [k, v] of Object.entries(params ?? {})) url.searchParams.set(k, String(v));
    const resp = await fetch(url, {
      headers: { Authorization: `Bearer ${this.token.access_token}` },
    });
    if (resp.status === 401) {
      await this.refresh();
      return this.get<T>(path, params);
    }
    if (!resp.ok) throw new Error(`GET ${path} failed: ${resp.status} ${await resp.text()}`);
    return (await resp.json()) as T;
  }

  private async *paginate<T>(
    path: string,
    opts: { limit?: number; start?: string; end?: string } = {},
  ): AsyncGenerator<T> {
    const params: Record<string, string | number> = { limit: opts.limit ?? 25 };
    if (opts.start) params.start = opts.start;
    if (opts.end) params.end = opts.end;
    for (;;) {
      const page = await this.get<Paginated<T>>(path, params);
      for (const rec of page.records) yield rec;
      if (!page.next_token) break;
      params.nextToken = page.next_token;
    }
  }

  // profile / body
  profile = () => this.get<Record<string, unknown>>("/user/profile/basic");
  bodyMeasurement = () => this.get<Record<string, unknown>>("/user/measurement/body");

  // recovery
  recoveryAll = (opts?: { limit?: number; start?: string; end?: string }) =>
    this.paginate<Record<string, unknown>>("/recovery", opts);
  recoveryForCycle = (cycleId: number) =>
    this.get<Record<string, unknown>>(`/cycle/${cycleId}/recovery`);

  // cycles
  cyclesAll = (opts?: { limit?: number; start?: string; end?: string }) =>
    this.paginate<Record<string, unknown>>("/cycle", opts);
  cycle = (cycleId: number) => this.get<Record<string, unknown>>(`/cycle/${cycleId}`);
  sleepForCycle = (cycleId: number) =>
    this.get<Record<string, unknown>>(`/cycle/${cycleId}/sleep`);

  // sleep
  sleepAll = (opts?: { limit?: number; start?: string; end?: string }) =>
    this.paginate<Record<string, unknown>>("/activity/sleep", opts);
  sleep = (sleepId: string) => this.get<Record<string, unknown>>(`/activity/sleep/${sleepId}`);

  // workouts
  workoutsAll = (opts?: { limit?: number; start?: string; end?: string }) =>
    this.paginate<Record<string, unknown>>("/activity/workout", opts);
  workout = (workoutId: string) =>
    this.get<Record<string, unknown>>(`/activity/workout/${workoutId}`);
}
