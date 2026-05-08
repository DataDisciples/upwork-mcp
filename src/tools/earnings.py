"""Earnings / financial summary tools."""

from upwork_client import get_client


def register(app):
    @app.tool(
        name="get_earnings",
        description="Get a financial overview and recent transactions.",
    )
    def get_earnings(first_transactions: int = 20) -> dict:
        return get_client().gql(
            """
            query Earnings($first: Int!) {
                financialOverview {
                    totalEarnings
                    pendingPayments
                    availableBalance
                    recentTransactions(first: $first) {
                        edges {
                            node {
                                id
                                amount
                                description
                                date
                                type
                            }
                        }
                    }
                }
            }
            """,
            {"first": first_transactions},
        )
