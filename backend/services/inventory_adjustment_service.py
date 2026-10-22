"""Single-session inventory commands. Authority precedes request and stock locks."""
from __future__ import annotations

import hashlib
import json
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import text

from services.inventory_service import InventoryService, _manual_decimal_from_cents, _manual_quantity_cents
from services.staff_management_service import StaffManagementService, current_staff_access, staff_error


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def adjustment_quantity(value, reason_kind):
    try:
        cents = _manual_quantity_cents(value)
    except ValueError:
        raise staff_error('INVALID_ADJUSTMENT_QUANTITY', 422) from None
    if (reason_kind not in {'loss', 'shrink', 'gain', 'correction'}
            or (reason_kind in {'loss', 'shrink'} and cents > 0)
            or (reason_kind == 'gain' and cents < 0)):
        raise staff_error('INVALID_ADJUSTMENT_QUANTITY', 422)
    return _manual_decimal_from_cents(cents)


class InventoryAdjustmentService:
    def __init__(self, db, tenant_id, schema):
        self.db = db
        self.staff = StaffManagementService(db, tenant_id, schema)
        self.q = self.staff.q

    async def _actor(self, actor, capability=None, *, owner=False, exclusive=False):
        actor = UUID(str(actor))
        if (self.db.info.get('tenant_schema') != self.staff.schema
                or self.db.info.get('_staff_stock_actor') != str(actor)
                or await self.db.scalar(text('SELECT current_schema()')) != self.staff.schema):
            raise staff_error('INVENTORY_AUTHORITY_SCOPE_MISMATCH', 403)
        authority = await self.staff.lock_authority(exclusive=exclusive)
        if authority.state != 'verified':
            raise staff_error('OWNER_MAPPING_REQUIRED')
        await self.staff.assert_non_customer_active_user(authority.owner_user_id, lock_user=False)
        access = await current_staff_access(self.db, self.staff.tenant_id, self.staff.schema, actor)
        await self.staff.assert_non_customer_active_user(actor, lock_user=False)
        if owner and not access['is_owner']:
            raise staff_error('OWNER_REQUIRED', 403)
        if not access['is_owner'] and (access['staff_state'] != 'active'
                or (capability is not None and capability not in access['permissions'])):
            raise staff_error('STAFF_PERMISSION_DENIED', 403)
        return actor, access, authority

    async def _eligible(self, user_id):
        configured = await self.db.scalar(text(
            f'SELECT EXISTS(SELECT 1 FROM {self.q}.inventory_adjustment_approvers WHERE user_id=:u)'), {'u': user_id})
        if not configured:
            return False
        try:
            access = await current_staff_access(self.db, self.staff.tenant_id, self.staff.schema, user_id)
            await self.staff.assert_non_customer_active_user(user_id, lock_user=False)
        except HTTPException:
            return False
        return access['is_owner'] or (access['staff_state'] == 'active'
            and 'inventory:adjustments:approve' in access['permissions'])

    async def _require_approver(self, actor):
        if not await self._eligible(actor):
            raise staff_error('ADJUSTMENT_APPROVER_REQUIRED', 403)

    async def policy(self, actor):
        await self._actor(actor, owner=True)
        row = (await self.db.execute(text(
            f'SELECT policy_version,owner_direct_enabled FROM {self.q}.staff_authority WHERE singleton=1'))).mappings().one()
        ids = (await self.db.execute(text(f'SELECT user_id FROM {self.q}.inventory_adjustment_approvers ORDER BY user_id'))).scalars().all()
        return {**dict(row), 'approver_ids': [str(uid) for uid in ids]}

    async def set_policy(self, actor, *, approver_ids, owner_direct_enabled, expected_policy_version):
        actor, _, authority = await self._actor(actor, owner=True, exclusive=True)
        if authority.policy_version != expected_policy_version:
            raise staff_error('POLICY_CHANGED')
        ids = [UUID(str(uid)) for uid in approver_ids]
        if not ids or len(ids) != len(set(ids)):
            raise staff_error('INVALID_APPROVER_LIST', 422)
        for uid in sorted(ids):
            try:
                access = await current_staff_access(self.db, self.staff.tenant_id, self.staff.schema, uid)
                await self.staff.assert_non_customer_active_user(uid, lock_user=False)
            except HTTPException:
                raise staff_error('INVALID_APPROVER_LIST', 422) from None
            if not access['is_owner'] and (access['staff_state'] != 'active'
                    or 'inventory:adjustments:approve' not in access['permissions']):
                raise staff_error('INVALID_APPROVER_LIST', 422)
        await self.db.execute(text(f'DELETE FROM {self.q}.inventory_adjustment_approvers'))
        for uid in sorted(ids):
            await self.db.execute(text(f'INSERT INTO {self.q}.inventory_adjustment_approvers(user_id) VALUES (:u)'), {'u': uid})
        await self.db.execute(text(f'UPDATE {self.q}.staff_authority SET policy_version=policy_version+1, '
            'authz_revision=authz_revision+1,owner_direct_enabled=:enabled,updated_at=now() WHERE singleton=1'),
            {'enabled': owner_direct_enabled})
        await self.staff.audit(actor, 'adjustment_policy_updated', actor,
            {'policy_version': expected_policy_version+1, 'approver_ids': [str(u) for u in sorted(ids)],
             'owner_direct_enabled': owner_direct_enabled})
        return await self.policy(actor)

    async def _stock(self, sku_id):
        # Locate without locks, then use exactly the normal order stock kernel.
        identity = text(
            f'SELECT s.id,s.sku_code,s.name,s.unit,s.package_quantity,s.is_active,s.is_deleted,'
            f'c.is_active AS product_active,c.is_deleted AS product_deleted FROM {self.q}.skus s '
            f'JOIN {self.q}.catalog_products c ON c.id=s.catalog_product_id WHERE s.id=:s')
        sku = (await self.db.execute(identity,
            {'s': sku_id})).mappings().one_or_none()
        if not sku or not sku['is_active'] or sku['is_deleted'] or not sku['product_active'] or sku['product_deleted']:
            raise staff_error('SELLABLE_UNIT_NOT_FOUND', 404)
        code = sku['sku_code']
        try:
            await InventoryService()._locked_stock_by_sku_id(
                self.db, sku_id=sku_id, sku_code=code, require_active=True)
        except HTTPException as error:
            if not isinstance(error.detail, dict) or error.detail.get('code') != 'SELLABLE_UNIT_UNAVAILABLE':
                raise
            latest = (await self.db.execute(identity, {'s': sku_id})).mappings().one_or_none()
            if (not latest or latest['sku_code'] != code or not latest['is_active'] or latest['is_deleted']
                    or not latest['product_active'] or latest['product_deleted']):
                raise staff_error('SELLABLE_UNIT_NOT_FOUND', 404) from None
            raise staff_error('STOCK_NOT_INITIALIZED') from None
        # The kernel holds all three rows; no identity-first second lock order.
        sku = (await self.db.execute(identity, {'s': sku_id})).mappings().one()
        stock = (await self.db.execute(text(f'SELECT * FROM {self.q}.inventory_stocks WHERE sku_id=:s'),
            {'s': sku_id})).mappings().one_or_none()
        if not stock or stock['is_deleted']:
            raise staff_error('STOCK_NOT_INITIALIZED')
        try:
            before = _manual_quantity_cents(stock['quantity_on_hand'], allow_zero=True)
            reserved = _manual_quantity_cents(stock['quantity_reserved'], allow_zero=True)
            if before < reserved or reserved < 0:
                raise ValueError()
        except ValueError:
            raise staff_error('STOCK_STATE_INVALID') from None
        snapshot = {'sku_id': str(sku['id']), 'sku_code': sku['sku_code'], 'unit': sku['unit'],
                    'package_quantity': str(sku['package_quantity']), 'is_active': sku['is_active'],
                    'product_active': sku['product_active'], 'stock_id': str(stock['id']),
                    'stock_revision': stock['stock_revision'], 'quantity_on_hand': str(stock['quantity_on_hand']),
                    'quantity_reserved': str(stock['quantity_reserved'])}
        return snapshot, before, reserved

    async def snapshot(self, actor, sku_id):
        _, _, authority = await self._actor(actor, 'inventory:adjustments:request')
        snap, _, _ = await self._stock(sku_id)
        return {**snap, 'policy_version': authority.policy_version}

    @staticmethod
    def _key(key):
        if not isinstance(key, str) or not key.strip() or len(key) > 128:
            raise staff_error('ADJUSTMENT_KEY_REQUIRED', 422)
        return digest(key)

    @staticmethod
    def _view(row, *, replayed=False):
        return {'id': str(row['id']), 'requester_id': str(row['requester_id']),
                'sellable_unit_id': str(row['sellable_unit_id']), 'payload': row['payload'],
                'delta': str(row['delta']), 'policy_version': row['policy_version'], 'version': row['version'],
                'status': row['status'], 'result': row['result'], 'replayed': replayed,
                'decision_actor_id': str(row['decision_actor_id']) if row['decision_actor_id'] else None}

    async def submit(self, actor, *, key, sellable_unit_id, quantity_delta, reason_kind, reason,
                     expected_policy_version, expected_stock_revision, direct=False):
        quantity = adjustment_quantity(quantity_delta, reason_kind)
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
            raise staff_error('ADJUSTMENT_REASON_REQUIRED', 422)
        actor, _, authority = await self._actor(actor, 'inventory:adjustments:request', owner=direct)
        kd = self._key(key)
        fingerprint = digest([str(sellable_unit_id), str(quantity), reason_kind, reason,
                              expected_policy_version, expected_stock_revision, direct])
        # Serializes only this actor/key. Authority always precedes it.
        lock = int.from_bytes(bytes.fromhex(digest([str(self.staff.tenant_id), str(actor), kd]))[:8], 'big', signed=True)
        await self.db.execute(text('SELECT pg_advisory_xact_lock(:k)'), {'k': lock})
        old = (await self.db.execute(text(
            f'SELECT * FROM {self.q}.inventory_adjustment_requests WHERE requester_id=:a AND create_key_digest=:k'),
            {'a': actor, 'k': kd})).mappings().one_or_none()
        if direct and not authority.owner_direct_enabled:
            raise staff_error('OWNER_DIRECT_DISABLED', 403)
        if old:
            if old['create_fingerprint'] != fingerprint:
                raise staff_error('IDEMPOTENCY_KEY_CONFLICT')
            return self._view(old, replayed=True)
        if authority.policy_version != expected_policy_version:
            raise staff_error('POLICY_CHANGED')
        if not direct:
            ids = (await self.db.execute(text(f'SELECT user_id FROM {self.q}.inventory_adjustment_approvers WHERE user_id<>:a'),
                                         {'a': actor})).scalars().all()
            eligible = [uid for uid in ids if await self._eligible(uid)]
            if not eligible:
                raise staff_error('NO_ELIGIBLE_APPROVER')
        snapshot, before, reserved = await self._stock(sellable_unit_id)
        if snapshot['stock_revision'] != expected_stock_revision:
            raise staff_error('STOCK_CHANGED')
        payload = {**snapshot, 'quantity_delta': str(quantity), 'reason_kind': reason_kind, 'reason': reason}
        rid = uuid4()
        await self.db.execute(text(f'INSERT INTO {self.q}.inventory_adjustment_requests '
            '(id,requester_id,sellable_unit_id,stock_id,payload,delta,policy_version,create_key_digest,create_fingerprint) '
            'VALUES (:id,:a,:s,:stock,CAST(:p AS jsonb),:delta,:v,:key,:fp)'),
            {'id': rid, 'a': actor, 's': sellable_unit_id, 'stock': UUID(snapshot['stock_id']),
             'p': json.dumps(payload), 'delta': quantity, 'v': authority.policy_version, 'key': kd, 'fp': fingerprint})
        if direct:
            result = await self._apply(rid, actor, payload, before, reserved)
            await self._terminal(rid, actor, 'applied_direct', kd, fingerprint, result)
        else:
            await self.staff.audit(actor, 'adjustment_requested', rid, {'policy_version': authority.policy_version})
        return await self._read(rid)

    async def _read(self, request_id):
        row = (await self.db.execute(text(f'SELECT * FROM {self.q}.inventory_adjustment_requests WHERE id=:id'),
                                    {'id': request_id})).mappings().one_or_none()
        if row is None:
            raise staff_error('ADJUSTMENT_NOT_FOUND', 404)
        return self._view(row)

    async def list_requests(self, actor):
        actor, access, _ = await self._actor(actor, 'inventory:adjustments:read')
        all_visible = access['is_owner'] or await self._eligible(actor)
        rows = (await self.db.execute(text(f'SELECT * FROM {self.q}.inventory_adjustment_requests '
            'WHERE (:all_visible OR requester_id=:a) ORDER BY created_at DESC,id LIMIT 100'),
            {'all_visible': all_visible, 'a': actor})).mappings().all()
        return {'items': [self._view(row) for row in rows], 'can_approve': await self._eligible(actor)}

    async def detail(self, actor, request_id):
        actor, access, _ = await self._actor(actor, 'inventory:adjustments:read')
        row = await self._read(request_id)
        if row['requester_id'] != str(actor) and not access['is_owner'] and not await self._eligible(actor):
            raise staff_error('ADJUSTMENT_NOT_FOUND', 404)
        return row

    async def decide(self, actor, request_id, *, action, key, expected_version, reason=''):
        if action not in {'approve', 'reject', 'withdraw'}:
            raise staff_error('INVALID_ADJUSTMENT_DECISION', 422)
        if not isinstance(reason, str) or len(reason)>1000:
            raise staff_error('ADJUSTMENT_REASON_REQUIRED', 422)
        actor, _, authority = await self._actor(actor, None if action == 'withdraw' else 'inventory:adjustments:approve')
        row = (await self.db.execute(text(f'SELECT * FROM {self.q}.inventory_adjustment_requests WHERE id=:id FOR UPDATE'),
                                    {'id': request_id})).mappings().one_or_none()
        if row is None:
            raise staff_error('ADJUSTMENT_NOT_FOUND', 404)
        if action == 'withdraw':
            if actor != row['requester_id']:
                raise staff_error('ADJUSTMENT_NOT_FOUND', 404)
        else:
            await self._require_approver(actor)
            if actor == row['requester_id']:
                raise staff_error('SELF_APPROVAL_FORBIDDEN', 403)
        kd = self._key(key)
        fp = digest([action, str(request_id), expected_version, reason])
        if row['status'] != 'pending':
            if row['decision_actor_id'] == actor and row['decision_key_digest'] == kd:
                if row['decision_fingerprint'] != fp:
                    raise staff_error('IDEMPOTENCY_KEY_CONFLICT')
                return self._view(row, replayed=True)
            raise staff_error('ADJUSTMENT_ALREADY_DECIDED')
        if row['version'] != expected_version:
            raise staff_error('ADJUSTMENT_ALREADY_DECIDED')
        result = {'reason': reason}
        status = {'approve': 'approved_applied', 'reject': 'rejected', 'withdraw': 'withdrawn'}[action]
        if action == 'approve':
            # Eligibility is current, including the original requester's live capability.
            await self._requester_live(row['requester_id'])
            if authority.policy_version != row['policy_version']:
                raise staff_error('POLICY_CHANGED')
            try:
                snap, before, reserved = await self._stock(row['sellable_unit_id'])
            except HTTPException as error:
                if error.status_code == 404:
                    raise staff_error('STOCK_CHANGED') from None
                raise
            if any(snap[k] != row['payload'][k] for k in snap):
                raise staff_error('STOCK_CHANGED')
            result = await self._apply(row['id'], actor, row['payload'], before, reserved)
        await self._terminal(row['id'], actor, status, kd, fp, result)
        return await self._read(row['id'])

    async def _requester_live(self, requester):
        try:
            access = await current_staff_access(self.db, self.staff.tenant_id, self.staff.schema, requester)
            await self.staff.assert_non_customer_active_user(requester, lock_user=False)
        except HTTPException:
            raise staff_error('REQUESTER_NO_LONGER_ELIGIBLE', 403) from None
        if not access['is_owner'] and (access['staff_state'] != 'active'
                or 'inventory:adjustments:request' not in access['permissions']):
            raise staff_error('REQUESTER_NO_LONGER_ELIGIBLE', 403)

    async def _apply(self, request_id, actor, payload, before, reserved):
        after = before + _manual_quantity_cents(payload['quantity_delta'])
        if after < 0:
            raise staff_error('NEGATIVE_STOCK')
        if after < reserved:
            raise staff_error('STOCK_RESERVED_CONFLICT')
        if after > 999999999999:
            raise staff_error('INVALID_ADJUSTMENT_QUANTITY', 422)
        await self.db.execute(text(f'UPDATE {self.q}.inventory_stocks SET quantity_on_hand=:after,updated_at=now() WHERE id=:id'),
            {'after': _manual_decimal_from_cents(after), 'id': UUID(payload['stock_id'])})
        movement_id = uuid4()
        await self.db.execute(text(f'INSERT INTO {self.q}.inventory_movements '
            '(id,sku_id,movement_type,quantity,quantity_before,quantity_after,reason,reference_type,reference_id,created_by,manual_adjustment_id) '
            "VALUES (:id,:sku,'adjustment',:delta,:before,:after,:reason,'manual',:req,:actor,:req)"),
            {'id': movement_id, 'sku': UUID(payload['sku_id']), 'delta': _manual_decimal_from_cents(_manual_quantity_cents(payload['quantity_delta'])),
             'before': _manual_decimal_from_cents(before), 'after': _manual_decimal_from_cents(after),
             'reason': payload['reason'], 'req': request_id, 'actor': actor})
        return {'movement_id': str(movement_id), 'quantity_before': str(_manual_decimal_from_cents(before)),
                'quantity_after': str(_manual_decimal_from_cents(after))}

    async def _terminal(self, rid, actor, status, kd, fp, result):
        await self.staff.audit(actor, 'adjustment_' + status, rid, result)
        await self.db.execute(text(f'UPDATE {self.q}.inventory_adjustment_requests SET status=:s,version=2,'
            'decision_actor_id=:a,decision_key_digest=:k,decision_fingerprint=:f,result=CAST(:r AS jsonb),decided_at=now() WHERE id=:id'),
            {'s': status, 'a': actor, 'k': kd, 'f': fp, 'r': json.dumps(result), 'id': rid})
