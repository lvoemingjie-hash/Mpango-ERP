/**
 * Passive network observation helpers.
 *
 * ONLY passive request listening (page.on('request')) is permitted. No
 * page.route / context.route / fulfill / interception — the static validator
 * REDs any such pattern.
 */
import { Page, Request } from '@playwright/test';

export interface ObservedRequest {
  method: string;
  url: string;
  postData: string | null;
}

export function attachObserver(page: Page, sink: ObservedRequest[]): void {
  const handler = (request: Request) => {
    if (!request.url().includes('/api/')) return;
    let postData: string | null = null;
    try {
      postData = request.postData() ?? null;
    } catch {
      postData = null;
    }
    sink.push({ method: request.method(), url: request.url(), postData });
  };
  page.on('request', handler);
}

const ORDER_CREATE_URL: RegExp = new RegExp('/api/v1/client/orders/?$');

export function observedOrderCreations(sink: ObservedRequest[]): any[] {
  return sink
    .filter((r) => r.method === 'POST' && ORDER_CREATE_URL.test(r.url))
    .map((r): any => {
      if (!r.postData) return null;
      try {
        return JSON.parse(r.postData);
      } catch {
        return null;
      }
    })
    .filter((p) => p !== null);
}
