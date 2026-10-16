"""One isolated decoder process, hard Linux limits, anonymous input/output."""
import asyncio
import base64
import json
import os
import signal
import subprocess
import sys
from pathlib import Path


def _child(input_fd, output_fd, expected):
    import resource
    import io
    import warnings

    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024**2, 1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = 8_000_000
    warnings.simplefilter('error', Image.DecompressionBombWarning)
    raw = bytearray()
    while len(raw) <= 5 * 1024**2:
        chunk = os.read(input_fd, min(65536, 5 * 1024**2 + 1 - len(raw)))
        if not chunk:
            break
        raw.extend(chunk)
    if not raw or len(raw) > 5 * 1024**2:
        raise ValueError
    with Image.open(io.BytesIO(raw), formats=('JPEG', 'PNG', 'WEBP')) as source:
        if source.format != expected or getattr(source, 'n_frames', 1) != 1 or getattr(source, 'is_animated', False):
            raise ValueError
        if max(source.size) > 4096 or source.width * source.height > 8_000_000:
            raise ValueError
        source.load()
        image = ImageOps.exif_transpose(source).convert('RGBA')
        clean = Image.new('RGBA', image.size)
        clean.paste(image)
        result = {}
        for name, edge, limit in [('thumb', 400, 80 * 1024), ('detail', 1280, 300 * 1024)]:
            for bound in (edge, edge * 3 // 4, edge // 2):
                resized = clean.copy()
                resized.thumbnail((bound, bound))
                for quality in (82, 70, 55, 40):
                    output = io.BytesIO()
                    resized.save(output, format='WEBP', quality=quality, method=2)
                    data = output.getvalue()
                    if len(data) <= limit:
                        result[name] = [base64.b64encode(data).decode('ascii'), resized.width, resized.height]
                        break
                if name in result:
                    break
            if name not in result:
                raise ValueError
    payload = json.dumps(result, separators=(',', ':')).encode('ascii')
    view = memoryview(payload)
    while view:
        n = os.write(output_fd, view)
        if n <= 0:
            raise OSError
        view = view[n:]


def _decode(raw, expected):
    from services.product_image_storage import refuse, VARIANT_LIMITS

    descriptors = []
    child = None
    try:
        for name in ('image-in', 'image-out'):
            descriptors.append(os.memfd_create(name, os.MFD_CLOEXEC))
        input_fd, output_fd = descriptors
        view = memoryview(raw)
        while view:
            n = os.write(input_fd, view)
            if n <= 0:
                raise OSError
            view = view[n:]
        os.lseek(input_fd, 0, os.SEEK_SET)
        child = subprocess.Popen(
            [sys.executable, '-B', '-I', str(Path(__file__).resolve()), str(input_fd), str(output_fd), expected],
            pass_fds=(input_fd, output_fd), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}, start_new_session=True,
        )
        try:
            rc = child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()
            refuse('IMAGE_PROCESS_TIMEOUT', 422)
        if rc != 0:
            refuse('IMAGE_INVALID', 422)
        size = os.fstat(output_fd).st_size
        if not 0 < size <= 600 * 1024:
            refuse('IMAGE_INVALID', 422)
        os.lseek(output_fd, 0, os.SEEK_SET)
        payload = json.loads(os.read(output_fd, size + 1))
        if set(payload) != set(VARIANT_LIMITS):
            refuse('IMAGE_INVALID', 422)
        result = {}
        for name, limit in VARIANT_LIMITS.items():
            encoded, width, height = payload[name]
            data = base64.b64decode(encoded, validate=True)
            if not data or len(data) > limit or type(width) is not int or type(height) is not int or min(width, height) <= 0 or max(width, height) > (400 if name == 'thumb' else 1280):
                refuse('IMAGE_INVALID', 422)
            result[name] = (data, width, height)
        return result
    except (OSError, ValueError, KeyError, TypeError):
        refuse('IMAGE_PROCESS_UNAVAILABLE')
    finally:
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
        for fd in descriptors:
            os.close(fd)


async def process_image(raw, expected):
    # Cancellation waits for the bounded owner, never releases the global
    # write lease while a decoder thread/process is still active.
    task = asyncio.create_task(asyncio.to_thread(_decode, raw, expected))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if task.done() and not task.cancelled():
            task.exception()
        raise


if __name__ == '__main__':
    try:
        _child(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3])
    except BaseException:
        sys.exit(2)
