"""Contract / engagement tools.

Schema NOTE: field names below are unverified (see tools/_helpers.py).
"""

from typing import Optional

from upwork_client import get_client


def register(app):
    @app.tool(
        name="list_contracts",
        description="List freelancer contracts/engagements. status: 'active' | 'closed' | 'all'.",
    )
    def list_contracts(status: Optional[str] = "active", first: int = 50) -> dict:
        variables = {"first": first}
        filter_clause = ""
        if status and status.lower() != "all":
            variables["status"] = status.upper()
            filter_clause = "status: $status,"
        query = f"""
            query Engagements($first: Int!{', $status: EngagementStatus' if filter_clause else ''}) {{
                engagements({filter_clause} first: $first) {{
                    edges {{
                        node {{
                            id
                            title
                            status
                            startDate
                            endDate
                            client {{ name companyName }}
                            weeklyBudget
                            totalCharges
                        }}
                    }}
                    pageInfo {{ hasNextPage endCursor }}
                }}
            }}
        """
        return get_client().gql(query, variables)

    @app.tool(
        name="get_contract",
        description="Get detailed information about a single contract by id.",
    )
    def get_contract(contract_id: str) -> dict:
        return get_client().gql(
            """
            query GetEngagement($id: ID!) {
                engagement(id: $id) {
                    id
                    title
                    status
                    startDate
                    endDate
                    description
                    client { name companyName }
                    weeklyBudget
                    totalCharges
                    hoursPerWeek
                    feedback { score comment }
                }
            }
            """,
            {"id": contract_id},
        )
