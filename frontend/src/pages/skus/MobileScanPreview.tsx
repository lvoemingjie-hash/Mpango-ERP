/**
 * U4-H-A: Mobile Scan Preview component.
 *
 * Thin mobile-friendly scan entry for Data Intake. Uses native BarcodeDetector
 * Web API when available; falls back to manual barcode/SKU text input.
 *
 * Contract: PREVIEW ONLY. No SKU writes. No apply. Internal-login-only.
 * No image persistence. No new dependencies.
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import { CameraIcon, ClipboardDocumentIcon } from '@heroicons/react/24/outline';

export interface ScanResult {
  code: string;
  source: 'camera' | 'manual';
  timestamp: string;
}

interface MobileScanPreviewProps {
  onScan?: (result: ScanResult) => void;
}

function isBarcodeDetectorSupported(): boolean {
  return typeof window !== 'undefined' && 'BarcodeDetector' in window;
}

export function MobileScanPreview({ onScan }: MobileScanPreviewProps) {
  const [supported, setSupported] = useState<boolean | null>(null);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [manualCode, setManualCode] = useState('');
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef<number | null>(null);
  const detectorRef = useRef<unknown>(null);

  useEffect(() => {
    setSupported(isBarcodeDetectorSupported());
  }, []);

  const stopCamera = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setScanning(false);
  }, []);

  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, [stopCamera]);

  const detectLoop = useCallback(async () => {
    const video = videoRef.current;
    if (!video || !detectorRef.current) return;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const detector = detectorRef.current as any;
    try {
      const barcodes = await detector.detect(video);
      if (barcodes && barcodes.length > 0) {
        const code = barcodes[0].rawValue as string;
        if (code) {
          const scanResult: ScanResult = {
            code,
            source: 'camera',
            timestamp: new Date().toISOString(),
          };
          setResult(scanResult);
          onScan?.(scanResult);
          stopCamera();
          return;
        }
      }
    } catch {
      // detect() can throw transiently; retry on next frame
    }

    if (scanning) {
      rafRef.current = requestAnimationFrame(detectLoop);
    }
  }, [onScan, scanning, stopCamera]);

  const startCamera = useCallback(async () => {
    setError(null);
    setResult(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
      });
      streamRef.current = stream;

      const video = videoRef.current;
      if (video) {
        video.srcObject = stream;
        await video.play();
      }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const BarcodeDetectorCtor = (window as any).BarcodeDetector;
      detectorRef.current = new BarcodeDetectorCtor({
        formats: ['ean_13', 'ean_8', 'code_128', 'code_39', 'upc_a', 'upc_e', 'qr_code'],
      });

      setScanning(true);
      rafRef.current = requestAnimationFrame(detectLoop);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Camera access failed';
      setError('Camera error: ' + message + '. Use manual entry below.');
      setScanning(false);
    }
  }, [detectLoop]);

  const handleManualSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      const code = manualCode.trim();
      if (!code) return;
      const scanResult: ScanResult = {
        code,
        source: 'manual',
        timestamp: new Date().toISOString(),
      };
      setResult(scanResult);
      onScan?.(scanResult);
    },
    [manualCode, onScan],
  );

  const handleCopy = useCallback(() => {
    if (result?.code) {
      navigator.clipboard?.writeText(result.code).catch(() => {});
    }
  }, [result]);

  const supportedNotice = supported === false ? (
    <div className="mt-3 rounded-md bg-blue-50 p-2 text-xs text-blue-700">
      Camera scanning is not supported in this browser. Use manual entry below.
    </div>
  ) : null;

  const errorDisplay = error ? (
    <div className="mt-2 rounded-md bg-red-50 p-2 text-xs text-red-700">{error}</div>
  ) : null;

  const resultDisplay = result ? (
    <div className="mt-3 rounded-md border border-green-200 bg-green-50 p-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-green-800">
          {'Captured (' + (result.source === 'camera' ? 'camera scan' : 'manual entry') + ')'}
        </span>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1 text-xs text-green-700 underline hover:text-green-900"
        >
          <ClipboardDocumentIcon className="h-3 w-3" />
          Copy
        </button>
      </div>
      <p className="mt-1 break-all font-mono text-sm text-green-900">{result.code}</p>
      <p className="mt-1 text-xs text-green-600">
        {new Date(result.timestamp).toLocaleString()}
      </p>
      <p className="mt-2 text-xs text-green-600">
        Preview only. Not applied to the product catalog.
      </p>
    </div>
  ) : null;

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="flex items-center gap-2">
        <CameraIcon className="h-5 w-5 text-gray-500" />
        <h3 className="text-sm font-semibold text-gray-900">Mobile scan preview</h3>
      </div>
      <p className="mt-1 text-xs text-gray-500">
        {'Scan or enter a product barcode/SKU code. The result is staged preview only and is NOT written to the product catalog.'}
      </p>

      {supported === true && !scanning && (
        <div className="mt-3">
          <button
            type="button"
            onClick={startCamera}
            className="btn-secondary flex items-center gap-2 text-sm"
          >
            <CameraIcon className="h-4 w-4" />
            Start camera scan
          </button>
        </div>
      )}

      {supported === true && scanning && (
        <div>
          <video
            ref={videoRef}
            className="w-full max-w-sm rounded-md border border-gray-300"
            playsInline
            muted
          />
          <button
            type="button"
            onClick={stopCamera}
            className="mt-2 text-xs text-gray-500 underline hover:text-gray-700"
          >
            Stop camera
          </button>
        </div>
      )}

      {supportedNotice}

      <form onSubmit={handleManualSubmit} className="mt-3 flex gap-2">
        <input
          type="text"
          value={manualCode}
          onChange={(e) => setManualCode(e.target.value)}
          placeholder="Enter barcode or SKU code"
          maxLength={128}
          className="block flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
          aria-label="Manual barcode or SKU code"
        />
        <button type="submit" className="btn-primary text-sm" disabled={!manualCode.trim()}>
          Capture
        </button>
      </form>

      {errorDisplay}
      {resultDisplay}
    </div>
  );
}
