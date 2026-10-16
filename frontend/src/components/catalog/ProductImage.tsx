import { useEffect, useRef, useState } from 'react';
import { ShoppingBagIcon } from '@heroicons/react/24/outline';
import { useAuthStore } from '@/stores/authStore';
import { leaseProductImage, productImageService } from '@/services/productImageService';
import type { ProductImageMetadata, ProductImageState } from '@/services/productImageService';

function currentSession() {
  const state = useAuthStore.getState();
  return state.accessToken ? `${state.tenantCode}|${state.user?.id}|${state.accessToken}` : '';
}

export function ProductImage({ image, name, detail = false, className = '' }: {
  image?: ProductImageMetadata | null; name: string; detail?: boolean; className?: string;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [loaded, setLoaded] = useState<{ session: string; path: string; url: string } | null>(null);
  const token = useAuthStore(state => state.accessToken);
  const tenant = useAuthStore(state => state.tenantCode);
  const user = useAuthStore(state => state.user?.id);
  const session = token ? `${tenant}|${user}|${token}` : '';
  const path = image ? (detail ? image.detail_path : image.thumb_path) : '';

  useEffect(() => {
    if (!container.current) return;
    if (typeof IntersectionObserver === 'undefined') { setVisible(true); return; }
    const observer = new IntersectionObserver(entries => setVisible(entries.some(x => x.isIntersecting)), { rootMargin: '100px' });
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    setLoaded(null);
    if (!session || !path || !visible) return;
    let active = true;
    let lease: ReturnType<typeof leaseProductImage>;
    try { lease = leaseProductImage(path, session); } catch { return; }
    lease.ready.then(url => {
      if (active && currentSession() === session) setLoaded({ session, path, url });
    }).catch(() => { if (active) setLoaded(null); });
    return () => { active = false; lease.release(); };
  }, [session, path, visible]);

  const url = visible && loaded?.session === session && loaded.path === path ? loaded.url : null;
  return <div ref={container} className={`flex shrink-0 items-center justify-center overflow-hidden rounded-lg bg-gray-100 text-gray-400 ${className}`}>
    {url ? <img src={url} alt={name} decoding="async" className="h-full w-full object-contain" onError={() => setLoaded(null)} />
      : <><ShoppingBagIcon className="h-8 w-8" aria-hidden="true" /><span className="sr-only">No product image</span></>}
  </div>;
}

export function ProductImageMaintenance({ productId, initial, onChanged }: {
  productId: string; initial: Partial<ProductImageState>; onChanged: () => void;
}) {
  const [state, setState] = useState<ProductImageState>({ image_revision: initial.image_revision ?? 0, image: initial.image ?? null });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [unknown, setUnknown] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    setState({ image_revision: initial.image_revision ?? 0, image: initial.image ?? null });
    setUnknown(false); setMessage('');
  }, [productId, initial]);

  const act = async (file?: File) => {
    if (busy || unknown) return;
    if (file && (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 5 * 1024**2)) {
      setMessage('Choose a JPEG, PNG or WebP image no larger than 5 MiB.'); return;
    }
    setBusy(true); setMessage('');
    try {
      const value = file ? await productImageService.upload(productId, state.image_revision, file)
        : await productImageService.remove(productId, state.image_revision);
      setState(value); onChanged(); setMessage(file ? 'Image saved.' : 'Image removed.');
    } catch {
      setUnknown(true);
      setMessage('Image result is unknown or conflicted. Refresh image status before another change.');
    } finally {
      setBusy(false);
      if (input.current) input.current.value = '';
    }
  };
  const refresh = async () => {
    setBusy(true);
    try {
      setState(await productImageService.readState(productId)); setUnknown(false);
      setMessage('Status refreshed. Review it before choosing another change.'); onChanged();
    } catch { setMessage('Could not refresh image status. No change was retried.'); }
    finally { setBusy(false); }
  };
  return <section className="my-4 space-y-2 rounded-lg border border-gray-200 p-3" aria-label="Product image maintenance">
    <h3 className="text-sm font-semibold">Product image (optional)</h3>
    <ProductImage image={state.image} name="Current product" className="h-20 w-20" />
    <p className="text-xs text-gray-600">Shared by all packagings. The selected specification remains authoritative.</p>
    <input ref={input} type="file" aria-label="Upload product image" accept="image/jpeg,image/png,image/webp" disabled={busy || unknown}
      onChange={event => { const file = event.target.files?.[0]; if (file) void act(file); }} />
    <button type="button" disabled={busy || unknown || !state.image} onClick={() => void act()} className="text-sm text-red-700 disabled:opacity-50">Remove image</button>
    {unknown && <button type="button" disabled={busy} onClick={() => void refresh()} className="ml-3 text-sm text-primary-700">Refresh image status</button>}
    {message && <p role="status" className="text-sm text-gray-700">{message}</p>}
  </section>;
}
