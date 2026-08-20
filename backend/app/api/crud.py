"""Factory for the plain create/read/update/delete routers.

Six route modules were the same sixty lines with a different noun
substituted: insert the payload, list everything, fetch-or-404, assign every
field and save, delete-or-404. Besides the volume, the hand-written PUT
handlers copied fields across one line at a time, so adding a field to a
schema and forgetting to add a line to its PUT meant updates silently
ignored it.

Only the genuinely uniform resources are built this way. Anything with real
domain logic — bookings, payments, guests, auth, images — stays hand
written, as does `categories`, whose endpoint set is deliberately different
(no GET-by-id, and PATCH with its own narrower schema).
"""

import inspect
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from beanie import Document, PydanticObjectId
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.api.common import get_or_404

DocumentT = TypeVar("DocumentT", bound=Document)
PayloadT = TypeVar("PayloadT", bound=BaseModel)

# Maps a validated request body to the field values to store. Async because
# some resources have to resolve a reference first (plans turn a
# cancellation_policy_id into a Link). Applied to create *and* update, so a
# normalization can't silently apply to only one of them.
PayloadTransform = Callable[[Any], Awaitable[dict[str, Any]]]


async def _payload_fields(payload: BaseModel, transform: PayloadTransform | None) -> dict[str, Any]:
    """The field values to write, as validated Python objects rather than
    `model_dump()`'s plain dicts — assigning a dict to a model-typed field
    would bypass validation and store it raw."""
    fields = {name: getattr(payload, name) for name in type(payload).model_fields}
    if transform is not None:
        fields = await transform(payload)
    return fields


def _named_id_param(id_param: str) -> Callable[[Callable], Callable]:
    """Present the handler's document-id argument under `id_param`.

    The generated handlers read the id out of **kwargs, and FastAPI derives
    both the OpenAPI parameter name and the path-template placeholder from
    the signature — so overriding the signature here is what lets each
    resource keep the parameter name it has always published
    ("/admins/{admin_id}", not "/admins/{document_id}").
    """

    def decorate(endpoint: Callable) -> Callable:
        keep = [
            p
            for p in inspect.signature(endpoint).parameters.values()
            if p.kind is not inspect.Parameter.VAR_KEYWORD
        ]
        endpoint.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
            [
                *keep,
                inspect.Parameter(id_param, inspect.Parameter.KEYWORD_ONLY, annotation=PydanticObjectId),
            ]
        )
        return endpoint

    return decorate


def make_crud_router(
    *,
    model: type[DocumentT],
    create_schema: type[PayloadT],
    prefix: str,
    noun: str,
    tags: list[str] | None = None,
    dependencies: list[Any] | None = None,
    id_param: str = "document_id",
    sort: str | None = None,
    fetch_links: bool = False,
    transform_payload: PayloadTransform | None = None,
    on_delete: Callable[[DocumentT], Awaitable[None]] | None = None,
) -> APIRouter:
    """Build the standard five-endpoint router for `model`.

    :param noun: used verbatim in the 404 detail, e.g. "Cancellation policy".
    :param id_param: name of the document-id path parameter, e.g. "admin_id".
    :param sort: optional Mongo sort expression for the list endpoint.
    :param fetch_links: resolve Link fields on the read endpoints.
    :param transform_payload: see PayloadTransform.
    :param on_delete: guard/cleanup run before the document is removed.
    """
    router = APIRouter(prefix=prefix, tags=tags or [prefix.strip("/")], dependencies=dependencies or [])

    @router.post("", response_model=model, status_code=status.HTTP_201_CREATED)
    async def create(payload: create_schema):  # type: ignore[valid-type]
        document = model(**await _payload_fields(payload, transform_payload))
        await document.insert()
        return document

    @router.get("", response_model=list[model])
    async def list_all():
        query = model.find_all(fetch_links=fetch_links)
        if sort is not None:
            query = query.sort(sort)
        return await query.to_list()

    @router.get(f"/{{{id_param}}}", response_model=model)
    @_named_id_param(id_param)
    async def get_one(**kwargs):
        return await get_or_404(model, kwargs[id_param], noun, fetch_links=fetch_links)

    @router.put(f"/{{{id_param}}}", response_model=model)
    @_named_id_param(id_param)
    async def update(payload: create_schema, **kwargs):  # type: ignore[valid-type]
        document = await get_or_404(model, kwargs[id_param], noun)
        for field, value in (await _payload_fields(payload, transform_payload)).items():
            setattr(document, field, value)
        await document.save()
        return document

    @router.delete(f"/{{{id_param}}}", status_code=status.HTTP_204_NO_CONTENT)
    @_named_id_param(id_param)
    async def delete(**kwargs) -> None:
        document = await get_or_404(model, kwargs[id_param], noun)
        if on_delete is not None:
            await on_delete(document)
        await document.delete()

    return router


def admin_dependencies() -> list[Any]:
    """`dependencies=` value for a router only admins may touch."""
    from app.api.deps import require_admin

    return [Depends(require_admin)]
