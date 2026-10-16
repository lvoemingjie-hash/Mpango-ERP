import { api } from '@/services/api';
import type { ApiResponse } from '@/types/api';

export interface ProductImageMetadata {
  version: string;
  revision: number;
  thumb_path: string;
  detail_path: string;
  width: number;
  height: number;
}
export interface ProductImageState {
  image_revision: number;
  image: ProductImageMetadata | null;
}

const entries = new Map<string, {
  controller: AbortController; ready: Promise<string>; refs: number;
  url?: string; bytes: number;
}>();
let bytes = 0;
let running = 0;
const waiting: Array<() => void> = [];

function slot(signal: AbortSignal): Promise<() => void> {
  return new Promise((resolve, reject) => {
    const abort = () => {
      const index = waiting.indexOf(start);
      if (index >= 0) waiting.splice(index, 1);
      reject(new DOMException('Image request cancelled', 'AbortError'));
    };
    const start = () => {
      if (signal.aborted) { abort(); return; }
      if (running >= 4) { waiting.push(start); return; }
      signal.removeEventListener('abort', abort);
      running += 1;
      let released = false;
      resolve(() => {
        if (released) return;
        released = true;
        running -= 1;
        waiting.shift()?.();
      });
    };
    signal.addEventListener('abort', abort, { once: true });
    start();
  });
}

export function leaseProductImage(path: string, session: string) {
  if (!/^\/(?:catalog-products|client\/products)\/[0-9a-f-]{36}\/image\/[0-9a-f-]{36}\/(thumb|detail)$/.test(path)) {
    throw new Error('Invalid image path');
  }
  const key = `${session}|${path}`;
  let entry = entries.get(key);
  if (!entry) {
    if (entries.size >= 24) throw new Error('Image view capacity reached');
    const controller = new AbortController();
    const item = { controller, refs: 0, bytes: 0 } as {
      controller: AbortController; refs: number; bytes: number; ready: Promise<string>; url?: string;
    };
    item.ready = (async () => {
      const release = await slot(controller.signal);
      try {
        const response = await api.get<Blob>(path, { responseType: 'blob', signal: controller.signal });
        const limit = path.endsWith('/thumb') ? 80 * 1024 : 300 * 1024;
        const blob = response.data;
        if (controller.signal.aborted || item.refs === 0) throw new Error('Image view ended');
        if (blob.type !== 'image/webp' || blob.size <= 0 || blob.size > limit || bytes + blob.size > 8 * 1024**2) {
          throw new Error('Image response rejected');
        }
        item.url = URL.createObjectURL(blob);
        item.bytes = blob.size;
        bytes += blob.size;
        return item.url;
      } finally { release(); }
    })();
    entries.set(key, item);
    entry = item;
  }
  entry.refs += 1;
  const owned = entry;
  let released = false;
  return { ready: entry.ready, release: () => {
    if (released) return;
    released = true;
    owned.refs -= 1;
    if (owned.refs === 0) {
      owned.controller.abort();
      if (owned.url) URL.revokeObjectURL(owned.url);
      bytes -= owned.bytes;
      if (entries.get(key) === owned) entries.delete(key);
    }
  } };
}

export const productImageService = {
  readState: async (productId: string): Promise<ProductImageState> => {
    const response = await api.get<ApiResponse<ProductImageState>>(`/catalog-products/${productId}`);
    return response.data.data;
  },
  upload: async (productId: string, revision: number, file: File) => {
    const response = await api.put<ApiResponse<ProductImageState>>(`/catalog-products/${productId}/image`, file, {
      headers: { 'Content-Type': file.type, 'If-Match': String(revision) }, timeout: 25_000,
    });
    return response.data.data;
  },
  remove: async (productId: string, revision: number) => {
    const response = await api.delete<ApiResponse<ProductImageState>>(`/catalog-products/${productId}/image`, {
      headers: { 'If-Match': String(revision) },
    });
    return response.data.data;
  },
};
