import axios, { AxiosError, type AxiosAdapter, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, refreshCurrentAuthority } from '@/services/api';
import { useAuthStore } from '@/stores/authStore';
import { useToastStore } from '@/stores/toastStore';
import type { CurrentUserData, TokenData } from '@/types/auth';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const user = (name: string, tenant = name): CurrentUserData => ({
  id: name, email: null, full_name: name, tenant_id: tenant, tenant_schema: `t_${tenant}`,
  roles: ['admin'], permissions: ['orders:read'],
});
const tokens = (name: string): TokenData => ({ access_token: `${name}-access`, refresh_token: `${name}-refresh`,
  token_type: 'bearer', user_id: name, tenant_id: name, tenant_schema: `t_${name}`, roles: ['admin'] });
const response = (config: InternalAxiosRequestConfig, data: unknown): AxiosResponse => ({
  config, data, status: 200, statusText: 'OK', headers: {},
});
const denied = (config: InternalAxiosRequestConfig, status = 401) => new AxiosError('controlled refusal',
  AxiosError.ERR_BAD_REQUEST, config, undefined, { ...response(config, { error: { code: 'CONTROLLED', message: 'denied' } }), status });
const settle = <T>(promise: Promise<T>) => promise.then(value => value, error => error);
const turn = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
const originalApiAdapter = api.defaults.adapter;
const originalGlobalAdapter = axios.defaults.adapter;
let calls: Array<{ url: string; auth: unknown }>;
let refreshes: Array<ReturnType<typeof deferred<AxiosResponse>>>;
let started: ReturnType<typeof deferred<void>>;
let business: AxiosAdapter;

function login(name: string, sameUser = name) {
  useAuthStore.getState().retailerLogin(tokens(name), user(sameUser, name), name);
}
function release(index: number, name: string) {
  refreshes[index].resolve(response({} as InternalAxiosRequestConfig, { success: true, data: tokens(name) }));
}
function request(path = '/protected') { return settle(api.get(path)); }
function install() {
  const adapter: AxiosAdapter = async config => {
    calls.push({ url: config.url || '', auth: config.headers.get('Authorization') });
    if (config.url?.endsWith('/auth/refresh')) {
      const pending = deferred<AxiosResponse>(); refreshes.push(pending); started.resolve();
      return pending.promise;
    }
    if (config.url === '/auth/me') return response(config, { success: true, data: useAuthStore.getState().user });
    return business(config);
  };
  api.defaults.adapter = adapter;
  axios.defaults.adapter = adapter;
}
beforeEach(() => {
  calls = []; refreshes = []; started = deferred<void>();
  useAuthStore.getState().logout();
  useToastStore.setState({ toasts: [] });
  business = async config => {
    if (String(config.headers.get('Authorization')).includes('fresh')) return response(config, { ok: true });
    throw denied(config);
  };
  install();
  vi.spyOn(console, 'debug').mockImplementation(() => {});
});
afterEach(() => {
  api.defaults.adapter = originalApiAdapter;
  axios.defaults.adapter = originalGlobalAdapter;
  vi.restoreAllMocks();
});

describe('request-owned session generation', () => {
  it('old refresh success cannot overwrite a new login', async () => {
    login('A'); const pending = request(); await started.promise;
    login('B'); release(0, 'A-fresh'); const result = await pending;
    expect(useAuthStore.getState().accessToken, 'SESSION_OLD_REFRESH_SUCCESS').toBe('B-access');
    expect(useAuthStore.getState().user?.id).toBe('B');
    expect(axios.isCancel(result)).toBe(true);
    expect(calls.filter(c => c.url === '/protected')).toHaveLength(1);
  });
  it('old refresh failure cannot logout redirect or clear a new login', async () => {
    login('A'); const pending = request(); await started.promise;
    login('B'); const location = window.location.href;
    refreshes[0].reject(new Error('controlled old failure')); await pending;
    expect(useAuthStore.getState().accessToken).toBe('B-access');
    expect(window.location.href).toBe(location);
  });
  it('late A 401 never starts a refresh owned by B', async () => {
    const late = deferred<AxiosResponse>(); let captured!: InternalAxiosRequestConfig;
    business = async config => { captured = config; return late.promise; };
    login('A'); const pending = request(); await turn(); login('B');
    late.reject(denied(captured)); const result = await pending;
    expect(axios.isCancel(result)).toBe(true); expect(refreshes).toHaveLength(0);
    expect(useAuthStore.getState().accessToken).toBe('B-access');
  });
  it('old queued A requests cannot replay using B credentials', async () => {
    login('A'); const first = request(); await started.promise;
    const second = request('/queued'); await turn();
    expect(calls.filter(c => c.url === '/queued')).toHaveLength(1);
    login('B');
    // Queued work is refused at the boundary, before A's network returns.
    expect(axios.isCancel(await second)).toBe(true);
    release(0, 'A-fresh'); expect(axios.isCancel(await first)).toBe(true);
    expect(calls.filter(c => c.url === '/queued')).toHaveLength(1);
  });
  it('old finally cannot clear a newer refresh and its queue', async () => {
    login('A'); const old = request(); await started.promise;
    login('B'); started = deferred<void>(); const fresh = request('/B'); await started.promise;
    expect(refreshes).toHaveLength(2);
    release(0, 'A-fresh'); await old;
    const queued = request('/B-queued'); await turn(); expect(refreshes).toHaveLength(2);
    release(1, 'B-fresh'); await fresh; await queued;
    expect(useAuthStore.getState().accessToken).toBe('B-fresh-access');
  });
  it('logout and same-user login are a new generation even with identical tokens', async () => {
    login('A'); const old = request(); await started.promise;
    useAuthStore.getState().logout(); login('A'); release(0, 'A-fresh'); await old;
    expect(useAuthStore.getState().accessToken).toBe('A-access');
  });
  it('pending identity and workspace selection invalidate old work', async () => {
    login('A'); const old = request(); await started.promise;
    useAuthStore.getState().beginWorkspaceSelection(tokens('identity'));
    release(0, 'A-fresh'); await old;
    expect(useAuthStore.getState().user).toBeNull();
    expect(useAuthStore.getState().accessToken).toBe('identity-access');
  });
  it('workspace login invalidates an old identity request before its late 401', async () => {
    const late = deferred<AxiosResponse>(); let captured!: InternalAxiosRequestConfig;
    business = async config => { captured = config; return late.promise; };
    useAuthStore.getState().beginWorkspaceSelection(tokens('identity'));
    const old = request(); await turn();
    useAuthStore.getState().login(tokens('B'), user('B'), 'B');
    late.reject(denied(captured)); await old;
    expect(useAuthStore.getState().accessToken).toBe('B-access'); expect(refreshes).toHaveLength(0);
  });
  it('same-generation requests share one refresh and retry once', async () => {
    login('A'); const first = request(); await started.promise;
    const second = request('/queued'); await turn(); release(0, 'A-fresh');
    expect((await first).status).toBe(200); expect((await second).status).toBe(200);
    expect(refreshes).toHaveLength(1);
    expect(calls.filter(c => c.url === '/queued')).toHaveLength(2);
  });
  it('retried queued requests cannot create an infinite 401 refresh cycle', async () => {
    business = async config => { throw denied(config); };
    login('A'); const first = request(); await started.promise;
    const second = request('/queued'); await turn(); release(0, 'A-fresh');
    expect((await first).response.status).toBe(401); expect((await second).response.status).toBe(401);
    expect(refreshes).toHaveLength(1);
  });
  it('explicit empty authorization remains empty across a same-generation refresh', async () => {
    login('A'); const pending = settle(api.get('/empty', { headers: { authorization: '' } }));
    await started.promise; release(0, 'A-fresh'); const result = await pending;
    expect(result.response.status).toBe(401); expect(refreshes).toHaveLength(1);
    expect(calls.filter(c => c.url === '/empty').map(c => c.auth)).toEqual(['', '']);
  });
  it('explicit foreign case-insensitive authorization is never replaced on 401', async () => {
    login('A'); const pending = settle(api.get('/foreign', { headers: { aUtHoRiZaTiOn: 'Bearer external' } }));
    await started.promise; release(0, 'A-fresh'); const result = await pending;
    expect(result.response.status).toBe(401); expect(refreshes).toHaveLength(1);
    expect(calls.filter(c => c.url === '/foreign').map(c => c.auth)).toEqual(['Bearer external', 'Bearer external']);
  });
  it('public opt-out rejection has no refresh logout or toast side effect', async () => {
    login('A'); const before = useAuthStore.getState();
    await settle(api.post('/public', {}, { skipAuthInterceptors: true, headers: { Authorization: '' } }));
    expect(useAuthStore.getState().accessToken).toBe(before.accessToken);
    expect(refreshes).toHaveLength(0); expect(useToastStore.getState().toasts).toHaveLength(0);
  });
  it('late old 403 and authority refresh cannot change a new session', async () => {
    const late = deferred<AxiosResponse>(); let captured!: InternalAxiosRequestConfig;
    business = async config => { captured = config; return late.promise; };
    login('A'); const old = request(); await turn(); login('B');
    late.reject(denied(captured, 403)); await old;
    expect(calls.filter(c => c.url === '/auth/me')).toHaveLength(0);
    expect(useToastStore.getState().toasts).toHaveLength(0);
    await refreshCurrentAuthority(); expect(useAuthStore.getState().user?.id).toBe('B');
  });
  it('late same-generation 401 reuses the token already refreshed by its peer', async () => {
    const late = deferred<AxiosResponse>(); let captured!: InternalAxiosRequestConfig;
    business = async config => {
      if (String(config.headers.get('Authorization')).includes('fresh')) return response(config, { ok: true });
      if (config.url === '/late') { captured = config; return late.promise; }
      throw denied(config);
    };
    login('A'); const old = request('/late'); await turn();
    const peer = request(); await started.promise; release(0, 'A-fresh'); await peer;
    late.reject(denied(captured)); expect((await old).status).toBe(200);
    expect(refreshes).toHaveLength(1);
  });
  it('same-user identical-token relogin also invalidates an old authority response', async () => {
    const late = deferred<AxiosResponse>(); const arrived = deferred<void>();
    let captured!: InternalAxiosRequestConfig;
    const ordinary = api.defaults.adapter as AxiosAdapter;
    api.defaults.adapter = async config => {
      if (config.url === '/auth/me') { captured = config; arrived.resolve(); return late.promise; }
      return ordinary(config);
    };
    login('A'); const old = refreshCurrentAuthority(); await arrived.promise;
    useAuthStore.getState().logout(); login('A');
    late.resolve(response(captured, { success: true, data: { ...user('A'), permissions: ['stale:authority'] } }));
    await old;
    expect(useAuthStore.getState().user?.permissions).toEqual(['orders:read']);
  });
});
