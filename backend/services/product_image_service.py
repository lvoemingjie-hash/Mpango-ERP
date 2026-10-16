"""Media-only commands; transaction ownership remains with request finalization."""
import asyncio

from sqlalchemy import event, func, select, text
from sqlalchemy.orm import Session

from models.catalog_product import CatalogProduct
from models.catalog_product_image import CatalogProductImage
from schemas.product_image import image_state
from services.product_image_processor import process_image
from services.product_image_storage import (
    DATABASE_IDENTITY_SQL, MAX_INPUT, TENANT_IMAGES, MediaIOLease,
    canonical_uuid, refuse, storage_io,
)


@event.listens_for(Session, 'after_transaction_end')
def _release_media_leases(session, transaction):
    if transaction.parent is None:
        for lease in session.info.pop('product_image_leases', []):
            lease.transaction_ended()


async def product_for_images(db, product_id, *, client=False):
    from uuid import UUID
    from models.sku import SKU

    pid = UUID(canonical_uuid(product_id))
    query = select(CatalogProduct.id).where(
        CatalogProduct.id == pid, CatalogProduct.is_deleted.is_(False))
    if client:
        query = query.where(CatalogProduct.is_active.is_(True),
            select(SKU.id).where(SKU.catalog_product_id == pid,
                                 SKU.is_active.is_(True), SKU.is_deleted.is_(False)).exists())
    if (await db.execute(query)).scalar_one_or_none() is None:
        refuse('PRODUCT_NOT_FOUND', 404)
    return pid


async def rate_limit_images(tenant, actor):
    from redis.asyncio import Redis
    from redis.exceptions import RedisError
    from core.config import get_settings

    client = Redis.from_url(get_settings().REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
    script = """
    local a = redis.call('INCR', KEYS[1])
    if a == 1 then redis.call('EXPIRE', KEYS[1], 60) end
    local b = redis.call('INCR', KEYS[2])
    if b == 1 then redis.call('EXPIRE', KEYS[2], 60) end
    return {a,b}
    """
    try:
        a, b = await client.eval(script, 2, f'images:user:{tenant}:{actor}', f'images:tenant:{tenant}')
        if a > 10 or b > 30:
            refuse('IMAGE_RATE_LIMIT', 429)
    except (RedisError, OSError):
        refuse('IMAGE_LIMITER_UNAVAILABLE')
    finally:
        await client.aclose()


async def bounded_body(request):
    data = bytearray()
    try:
        async with asyncio.timeout(15):
            async for chunk in request.stream():
                if len(data) + len(chunk) > MAX_INPUT:
                    refuse('IMAGE_INPUT_LIMIT', 413)
                data.extend(chunk)
    except TimeoutError:
        refuse('IMAGE_UPLOAD_TIMEOUT', 408)
    if not data:
        refuse('IMAGE_INVALID', 422)
    return bytes(data)


def expected_revision(value):
    # Do not silently upgrade a stale revision on behalf of the caller.
    if value is None:
        refuse('IMAGE_REVISION_REQUIRED', 428)
    if not value.isascii() or not value.isdigit() or len(value) > 18:
        refuse('IMAGE_REVISION_INVALID', 422)
    return int(value)


async def write_image(db, request, *, product_id, tenant_id, actor_id, delete=False):
    from uuid import UUID
    from core.config import get_settings

    pid = await product_for_images(db, product_id)
    expected = expected_revision(request.headers.get('If-Match'))
    await rate_limit_images(tenant_id, actor_id)
    lease = MediaIOLease()
    db.info.setdefault('product_image_leases', []).append(lease)
    try:
        identity = dict((await db.execute(text(DATABASE_IDENTITY_SQL))).mappings().one())
        def open_store(owner):
            owner.open(get_settings().PRODUCT_IMAGE_ROOT, write=True)
            owner.store.verify_database(identity)
        await storage_io(lease, open_store)
        # Row creation and revision checks are serialized across workers by
        # the same filesystem lease that the GC/backup operator must hold.
        row = (await db.execute(select(CatalogProductImage).where(
            CatalogProductImage.product_id == pid).with_for_update()
            .execution_options(populate_existing=True))).scalar_one_or_none()
        current = row.image_revision if row else 0
        if current != expected:
            refuse('IMAGE_REVISION_CONFLICT', 409)
        if delete and (row is None or row.current_version is None):
            return image_state(row, pid)
        if delete:
            row.current_version = None
            row.variants = None
        else:
            mime = request.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
            formats = {'image/jpeg': 'JPEG', 'image/png': 'PNG', 'image/webp': 'WEBP'}
            if mime not in formats:
                refuse('IMAGE_TYPE_UNSUPPORTED', 415)
            await storage_io(lease, lambda owner: owner.store.check_capacity(tenant_id))
            count = (await db.execute(select(func.count()).select_from(CatalogProductImage).where(
                CatalogProductImage.current_version.is_not(None)))).scalar_one()
            if (row is None or row.current_version is None) and count >= TENANT_IMAGES:
                refuse('IMAGE_TENANT_QUOTA', 429)
            variants = await process_image(await bounded_body(request), formats[mime])
            # A request may have spent up to 20s receiving/decoding. Check
            # the authoritative product again before publishing any pointer.
            await product_for_images(db, product_id)
            version, metadata = await storage_io(lease, lambda owner: owner.store.publish(tenant_id, pid, variants))
            if row is None:
                row = CatalogProductImage(product_id=pid, image_revision=0, created_by=UUID(actor_id))
                db.add(row)
            row.current_version, row.variants = version, metadata
        row.image_revision = current + 1
        row.updated_by = UUID(actor_id)
        await db.flush()
        return image_state(row, pid)
    except BaseException:
        # Includes cancelled body reads: the existing auth middleware only
        # catches Exception. Release this command's transaction on that path.
        await db.rollback()
        raise


async def read_image(db, *, root, tenant_id, product_id, version, variant, client=False):
    if variant not in {'thumb', 'detail'}:
        refuse('IMAGE_NOT_FOUND', 404)
    pid = await product_for_images(db, product_id, client=client)
    version = canonical_uuid(version)
    row = await db.get(CatalogProductImage, pid, populate_existing=True)
    if row is None or str(row.current_version) != version:
        refuse('IMAGE_NOT_FOUND', 404)
    lease = MediaIOLease()
    try:
        identity = dict((await db.execute(text(DATABASE_IDENTITY_SQL))).mappings().one())
        def read(owner):
            owner.open(root)
            owner.store.verify_database(identity)
            return owner.store.read(tenant_id, pid, version, variant, row.variants[variant])
        return await storage_io(lease, read)
    except FileNotFoundError:
        refuse('IMAGE_NOT_FOUND', 404)
    except (OSError, KeyError):
        refuse('IMAGE_UNAVAILABLE')
    finally:
        lease.transaction_ended()
