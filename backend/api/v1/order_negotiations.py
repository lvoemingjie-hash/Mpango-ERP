"""Live-authorized S3 endpoints. Responses remain inside the request transaction."""
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequirePermission
from api.v1.client.dependencies import ClientIdentity, resolve_client_identity
from core.security import TokenPayload
from schemas.common import DataResponse
from schemas.order_negotiation import ProposalCreate, ProposalDecision
from services.order_negotiation_service import (
    accept_proposal, authoritative_now, create_proposal, decide_proposal, list_proposals, proposal_view,
)

router = APIRouter()


async def merchant_scope(request: Request) -> TokenPayload:
    await RequirePermission('pricing:write')(request)
    return await RequirePermission('orders:update')(request)


async def client_scope(request: Request) -> ClientIdentity:
    await RequirePermission('client:orders:read')(request)
    await RequirePermission('client:orders:create')(request)
    return await resolve_client_identity(request)


@router.get('/orders/{order_id}/negotiations', response_model=DataResponse[dict])
async def merchant_list(order_id: UUID, token: TokenPayload = Depends(merchant_scope),
                        db: AsyncSession = Depends(get_tenant_db_session)):
    return DataResponse(success=True, data={'items': await list_proposals(
        db, order_id=order_id, wholesaler_id=token.tenant_id)})


@router.post('/orders/{order_id}/negotiations', response_model=DataResponse[dict], status_code=201)
async def merchant_propose(order_id: UUID, body: ProposalCreate,
                           token: TokenPayload = Depends(merchant_scope),
                           db: AsyncSession = Depends(get_tenant_db_session)):
    proposal = await create_proposal(db, order_id=order_id, wholesaler_id=token.tenant_id,
                                     actor_id=token.user_id, request=body)
    return DataResponse(success=True, data=proposal_view(proposal, now=await authoritative_now(db)))


@router.post('/orders/{order_id}/negotiations/{proposal_id}/withdraw', response_model=DataResponse[dict])
async def merchant_withdraw(order_id: UUID, proposal_id: UUID, body: ProposalDecision,
                            token: TokenPayload = Depends(merchant_scope),
                            db: AsyncSession = Depends(get_tenant_db_session)):
    proposal, replayed = await decide_proposal(db, order_id=order_id, proposal_id=proposal_id,
        wholesaler_id=token.tenant_id, actor_id=token.user_id, decision=body, action='withdrawn')
    return DataResponse(success=True, data=proposal_view(proposal, now=await authoritative_now(db)) | {'replayed': replayed})


@router.get('/client/orders/{order_id}/negotiations', response_model=DataResponse[dict])
async def client_list(order_id: UUID,
                       token: TokenPayload = Depends(RequirePermission('client:orders:read')),
                       identity: ClientIdentity = Depends(resolve_client_identity),
                       db: AsyncSession = Depends(get_tenant_db_session)):
    return DataResponse(success=True, data={'items': await list_proposals(db, order_id=order_id,
        wholesaler_id=identity.tenant_id, retailer_id=identity.retailer_id)})


@router.post('/client/orders/{order_id}/negotiations/{proposal_id}/accept', response_model=DataResponse[dict])
async def client_accept(order_id: UUID, proposal_id: UUID, body: ProposalDecision,
                         identity: ClientIdentity = Depends(client_scope),
                         idempotency_key: str | None = Header(None, alias='X-Idempotency-Key'),
                         db: AsyncSession = Depends(get_tenant_db_session)):
    proposal, replayed = await accept_proposal(db, order_id=order_id, proposal_id=proposal_id,
        wholesaler_id=identity.tenant_id, retailer_id=identity.retailer_id, actor_id=identity.user_id,
        decision=body, idempotency_key=idempotency_key)
    return DataResponse(success=True, data=proposal_view(proposal, now=await authoritative_now(db)) | {'replayed': replayed})


@router.post('/client/orders/{order_id}/negotiations/{proposal_id}/reject', response_model=DataResponse[dict])
async def client_reject(order_id: UUID, proposal_id: UUID, body: ProposalDecision,
                        identity: ClientIdentity = Depends(client_scope),
                        db: AsyncSession = Depends(get_tenant_db_session)):
    proposal, replayed = await decide_proposal(db, order_id=order_id, proposal_id=proposal_id,
        wholesaler_id=identity.tenant_id, retailer_id=identity.retailer_id, actor_id=identity.user_id,
        decision=body, action='rejected')
    return DataResponse(success=True, data=proposal_view(proposal, now=await authoritative_now(db)) | {'replayed': replayed})
