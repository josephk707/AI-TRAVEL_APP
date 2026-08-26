"""
F21 — Safety / SOS Trusted-Contact Sharing (IMPLEMENTATION_BLUEPRINT.md
F21, API_SPECIFICATION.md §16). Location sharing is strictly opt-in per
trip (never enabled by default, §27 business rule) — `start_share`/
`stop_share` are the only ways a `trip_location_shares` row becomes
active, and the public viewer (`get_public_share`) only ever serves that
one trip's latest location to a holder of the exact, unguessable
`share_token` — never a generic authenticated read.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.exceptions import ForbiddenError, NotFoundError
from app.repositories.safety_repository import SafetyRepository
from app.repositories.trips_repository import TripsRepository
from app.services import email_client, notification_service
from app.services.email_client import EmailDeliveryError

_DEFAULT_SHARE_DURATION = timedelta(hours=24)


def _share_url(share_token: str) -> str:
    return f"aitouristguide://share/{share_token}"


async def add_trusted_contact(
    user_id: str, name: str, phone: str | None, email: str | None
) -> dict:
    if not phone and not email:
        from app.core.exceptions import AppError

        raise AppError(
            "CONTACT_NEEDS_PHONE_OR_EMAIL",
            "A trusted contact needs a phone number or an email address.",
            400,
        )
    return await SafetyRepository().add_contact(user_id, name, phone, email)


async def list_trusted_contacts(user_id: str) -> list[dict]:
    return await SafetyRepository().list_contacts(user_id)


async def start_share(trip_id: str, user_id: str) -> dict:
    trips_repo = TripsRepository()
    trip = await trips_repo.get_trip(trip_id)
    if trip is None:
        raise NotFoundError("This trip could not be found.")
    if not await trips_repo.is_trip_accessible(trip_id, user_id):
        raise ForbiddenError("You do not have access to this trip.")

    if trip["end_date"] is not None:
        expires_at = datetime.combine(
            trip["end_date"], datetime.min.time(), tzinfo=UTC
        ) + timedelta(days=1)
    else:
        expires_at = datetime.now(UTC) + _DEFAULT_SHARE_DURATION

    row = await SafetyRepository().start_share(trip_id, user_id, expires_at)
    return {**row, "share_url": _share_url(row["share_token"])}


async def stop_share(trip_id: str, user_id: str) -> None:
    trips_repo = TripsRepository()
    if not await trips_repo.is_trip_accessible(trip_id, user_id):
        raise ForbiddenError("You do not have access to this trip.")
    await SafetyRepository().stop_share(trip_id, user_id)


async def get_public_share(share_token: str) -> dict:
    repo = SafetyRepository()
    share = await repo.get_active_share_by_token(share_token)
    if share is None:
        raise NotFoundError("This share link is invalid, expired, or has been stopped.")

    location = await repo.get_latest_location(str(share["trip_id"]), str(share["user_id"]))
    return {
        "trip_id": str(share["trip_id"]),
        "is_active": share["is_active"],
        "expires_at": share["expires_at"],
        "last_known_lat": location["lat"] if location else None,
        "last_known_lng": location["lng"] if location else None,
        "recorded_at": location["recorded_at"] if location else None,
    }


async def trigger_sos(user_id: str, trip_id: str | None) -> dict:
    """FR-017 exception flow: location unavailable at trigger time ->
    last-known location + timestamp is sent instead of failing silently."""
    safety_repo = SafetyRepository()

    resolved_trip_id = trip_id
    if resolved_trip_id is None:
        trips = await TripsRepository().list_trips(user_id)
        active = next((t for t in trips if t["status"] == "active"), None)
        resolved_trip_id = str(active["id"]) if active else None

    last_location = None
    if resolved_trip_id:
        last_location = await safety_repo.get_latest_location(resolved_trip_id, user_id)

    event = await safety_repo.create_sos_event(
        user_id,
        resolved_trip_id,
        last_location["lat"] if last_location else None,
        last_location["lng"] if last_location else None,
        last_location["recorded_at"] if last_location else None,
    )

    await notification_service.dispatch(
        user_id,
        type_="sos",
        title="SOS alert sent",
        body="Your trusted contacts are being notified.",
        trip_id=resolved_trip_id,
    )

    contacts = await safety_repo.list_contacts(user_id)
    notified = 0
    location_text = (
        f"Last known location: {event['last_known_lat']}, {event['last_known_lng']}"
        if event["last_known_lat"] is not None
        else "Location was not available at the time of the alert."
    )
    for contact in contacts:
        if not contact["email"]:
            continue
        try:
            await email_client.send_email(
                contact["email"],
                subject="Yatra AI safety alert",
                body=(
                    f"{contact['name']}, this is an automated safety alert from Yatra AI. "
                    f"A traveller you are listed as a trusted contact for has triggered SOS. "
                    f"{location_text}"
                ),
            )
            notified += 1
        except EmailDeliveryError:
            # Never let one contact's delivery failure block notifying the
            # rest, or block the SOS event itself from having been recorded.
            continue

    return {**event, "contacts_notified": notified}
