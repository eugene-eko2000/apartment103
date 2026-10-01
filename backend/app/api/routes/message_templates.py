"""Admin CRUD for automated guest messages, plus a test send and the
delivery log. The schedule and the sending itself live in
app.services.guest_messages."""

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.common import get_or_404
from app.api.crud import make_crud_router
from app.api.deps import Principal, require_admin
from app.models.message_delivery import MessageDelivery
from app.models.message_template import MessageTemplate
from app.schemas.message_template import (
    MessageTemplateCreate,
    MessageTemplateStats,
    MessageTestSend,
    MessageTestSendResult,
)
from app.services.guest_messages import send_test_message


async def _drop_deliveries(template: MessageTemplate) -> None:
    await MessageDelivery.find(MessageDelivery.template_id == template.id).delete()


router = make_crud_router(
    model=MessageTemplate,
    create_schema=MessageTemplateCreate,
    prefix="/message-templates",
    noun="Message",
    id_param="template_id",
    tags=["message-templates"],
    dependencies=[Depends(require_admin)],
    sort="name",
    on_delete=_drop_deliveries,
)


# Mounted ahead of `router` in main.py so "/message-templates/stats" is
# matched before "/message-templates/{template_id}".
stats_router = APIRouter(prefix="/message-templates", tags=["message-templates"], dependencies=[Depends(require_admin)])


@stats_router.get("/stats", response_model=list[MessageTemplateStats])
async def delivery_stats() -> list[MessageTemplateStats]:
    cursor = await MessageDelivery.get_pymongo_collection().aggregate(
        [
            {
                "$group": {
                    "_id": "$template_id",
                    "sent": {"$sum": {"$cond": [{"$eq": ["$email_status", "sent"]}, 1, 0]}},
                    "failed": {"$sum": {"$cond": [{"$eq": ["$email_status", "failed"]}, 1, 0]}},
                    "skipped": {"$sum": {"$cond": [{"$eq": ["$email_status", "skipped"]}, 1, 0]}},
                }
            }
        ]
    )
    return [
        MessageTemplateStats(template_id=row["_id"], sent=row["sent"], failed=row["failed"], skipped=row["skipped"])
        for row in await cursor.to_list(None)
    ]


@router.get("/{template_id}/deliveries", response_model=list[MessageDelivery])
async def list_deliveries(template_id: PydanticObjectId) -> list[MessageDelivery]:
    return await MessageDelivery.find(MessageDelivery.template_id == template_id).sort("-created_at").to_list()


@router.post("/{template_id}/test-send", response_model=MessageTestSendResult)
async def test_send(
    template_id: PydanticObjectId, payload: MessageTestSend, principal: Principal = Depends(require_admin)
) -> MessageTestSendResult:
    template = await get_or_404(MessageTemplate, template_id, "Message")
    to = principal.admin.email
    try:
        message = await send_test_message(template, payload.language, to)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return MessageTestSendResult(to=to, subject=message.subject)
