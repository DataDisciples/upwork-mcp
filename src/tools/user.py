"""User / organization tools."""

from upwork_client import get_client


def register(app):
    @app.tool(
        name="get_user",
        description="Get the current authenticated user's profile and organization.",
    )
    def get_user() -> dict:
        return get_client().gql(
            """
            query {
                user {
                    id
                    nid
                    rid
                    name
                    email
                }
                organization {
                    id
                    name
                }
            }
            """
        )
