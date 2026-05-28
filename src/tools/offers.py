"""Offer tools. respond_to_offer is gated behind UPWORK_ALLOW_DESTRUCTIVE."""

from typing import Optional

from upwork_client import get_client
from tools._helpers import destructive_enabled


def register(app):
    @app.tool(name="list_offers", description="List incoming client offers.")
    def list_offers(status: Optional[str] = "pending") -> dict:
        return get_client().gql(
            """
            query Offers($status: OfferStatus!) {
                offers(status: $status) {
                    edges {
                        node {
                            id
                            title
                            client { name companyName }
                            budget
                            duration
                            description
                            createdAt
                        }
                    }
                }
            }
            """,
            {"status": (status or "pending").upper()},
        )

    @app.tool(
        name="respond_to_offer",
        description=(
            "Accept or decline an offer. Binding action. Disabled unless "
            "UPWORK_ALLOW_DESTRUCTIVE=true. Requires explicit user confirmation."
        ),
    )
    def respond_to_offer(offer_id: str, action: str) -> dict:
        if action.lower() not in ("accept", "decline"):
            return {"error": "action must be 'accept' or 'decline'"}
        if not destructive_enabled():
            return {
                "error": "Responding is disabled. Set UPWORK_ALLOW_DESTRUCTIVE=true to enable."
            }
        mutation_name = "acceptOffer" if action.lower() == "accept" else "declineOffer"
        return get_client().gql(
            f"""
            mutation Respond($id: ID!) {{
                {mutation_name}(offerId: $id) {{
                    id
                    status
                }}
            }}
            """,
            {"id": offer_id},
        )
