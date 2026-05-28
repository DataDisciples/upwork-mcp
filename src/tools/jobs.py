"""Job-search tool (read-only).

NOTE: Upwork does not allow proposal submission via API. This is research-only.
"""

from upwork_client import get_client


def register(app):
    @app.tool(
        name="search_jobs",
        description=(
            "Search Upwork job postings (read-only). Cannot submit proposals "
            "via API; this tool is for research only."
        ),
    )
    def search_jobs(query: str, first: int = 20) -> dict:
        return get_client().gql(
            """
            query SearchJobs($query: String!, $first: Int!) {
                jobPostings(search: $query, first: $first) {
                    edges {
                        node {
                            id
                            title
                            description
                            budget
                            hourlyRate
                            skills
                            category
                            postedAt
                            client { name rating totalSpent }
                        }
                    }
                }
            }
            """,
            {"query": query, "first": first},
        )
