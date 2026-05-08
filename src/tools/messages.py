"""Messaging tools (rooms / messages).

send_message is gated behind UPWORK_ALLOW_DESTRUCTIVE.
"""

from upwork_client import get_client
from tools._helpers import destructive_enabled


def register(app):
    @app.tool(name="list_rooms", description="List message rooms/threads.")
    def list_rooms(first: int = 20) -> dict:
        return get_client().gql(
            """
            query Rooms($first: Int!) {
                rooms(first: $first) {
                    edges {
                        node {
                            id
                            topic
                            roomType
                            lastActivity
                            participants { name }
                            unreadCount
                        }
                    }
                    pageInfo { hasNextPage endCursor }
                }
            }
            """,
            {"first": first},
        )

    @app.tool(name="get_messages", description="Read messages in a specific room.")
    def get_messages(room_id: str, first: int = 50) -> dict:
        return get_client().gql(
            """
            query Messages($roomId: ID!, $first: Int!) {
                room(id: $roomId) {
                    id
                    topic
                    messages(first: $first) {
                        edges {
                            node {
                                id
                                body
                                createdAt
                                author { name }
                            }
                        }
                    }
                }
            }
            """,
            {"roomId": room_id, "first": first},
        )

    @app.tool(
        name="send_message",
        description=(
            "Send a real message in a room. Disabled unless "
            "UPWORK_ALLOW_DESTRUCTIVE=true. Requires explicit user confirmation."
        ),
    )
    def send_message(room_id: str, body: str) -> dict:
        if not destructive_enabled():
            return {
                "error": "Sending is disabled. Set UPWORK_ALLOW_DESTRUCTIVE=true to enable."
            }
        return get_client().gql(
            """
            mutation Send($roomId: ID!, $body: String!) {
                sendMessage(roomId: $roomId, body: $body) {
                    id
                    body
                    createdAt
                }
            }
            """,
            {"roomId": room_id, "body": body},
        )
