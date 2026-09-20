from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    # `environment` is here so this endpoint can tell preprod and prod apart.
    # They share a host and an IP behind one edge proxy, and a misrouted
    # request returns a perfectly healthy-looking response — without a
    # discriminator in the body there is no way to detect it. The frontend has
    # one already (NEXT_PUBLIC_API_URL is baked into its bundle); this is the
    # API's. See docs/single-host-deployment-proposal.md.
    return {"status": "ok", "environment": settings.environment}
