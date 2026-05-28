"""Discover the live Upwork GraphQL schema via introspection.

Why this exists:
    Upwork's GraphQL schema for a client/organization account is not
    well-documented publicly, and the field names differ from the
    freelancer-earnings shape. Rather than guess query fields (and 404),
    run this once against YOUR account to dump exactly what's available,
    then write correct queries from the output.

Auth: reuses src/upwork_client.py (same env vars as the MCP server and
financial_pull.py):
    UPWORK_CLIENT_ID, UPWORK_CLIENT_SECRET, UPWORK_REFRESH_TOKEN,
    UPWORK_ACCESS_TOKEN (optional), UPWORK_ORG_UID (optional),
    UPWORK_TOKEN_FILE (optional)

Usage:
    # List every root Query field, its args, and its return type:
    python pipeline/discover_schema.py

    # Drill into a specific type's fields (use the type name from the list):
    python pipeline/discover_schema.py --type Organization

    # Machine-readable dump (for pasting back so queries can be finalized):
    python pipeline/discover_schema.py --json > schema_queries.json

Run this from a machine with internet access to api.upwork.com (your
laptop, a Domo Jupyter Workspace, or any non-sandboxed host).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make src/ importable so we reuse upwork_client.py without packaging.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from upwork_client import get_client  # noqa: E402


# ---------------------------------------------------------------------------
# Introspection queries
# ---------------------------------------------------------------------------

# Reusable fragment that unwraps NON_NULL / LIST wrappers up to 3 levels deep,
# which is enough for almost every real field signature.
_TYPE_REF = """
fragment TypeRef on __Type {
  kind
  name
  ofType {
    kind
    name
    ofType {
      kind
      name
      ofType { kind name }
    }
  }
}
"""

ROOT_QUERY_FIELDS = (
    """
query RootQueryFields {
  __schema {
    queryType { name }
    mutationType { name }
  }
  __type(name: "Query") {
    name
    fields(includeDeprecated: false) {
      name
      description
      isDeprecated
      args {
        name
        description
        type { ...TypeRef }
      }
      type { ...TypeRef }
    }
  }
}
"""
    + _TYPE_REF
)

TYPE_FIELDS = (
    """
query TypeFields($name: String!) {
  __type(name: $name) {
    name
    kind
    description
    fields(includeDeprecated: false) {
      name
      description
      isDeprecated
      args { name type { ...TypeRef } }
      type { ...TypeRef }
    }
    inputFields { name type { ...TypeRef } }
    enumValues { name }
  }
}
"""
    + _TYPE_REF
)


# ---------------------------------------------------------------------------
# Type-ref rendering
# ---------------------------------------------------------------------------

def render_type_ref(ref: dict | None) -> str:
    """Render a GraphQL type ref like '[Transaction!]!' from the nested
    introspection shape."""
    if not ref:
        return "?"
    kind = ref.get("kind")
    name = ref.get("name")
    inner = ref.get("ofType")
    if kind == "NON_NULL":
        return f"{render_type_ref(inner)}!"
    if kind == "LIST":
        return f"[{render_type_ref(inner)}]"
    return name or "?"


def _fmt_args(args: list[dict]) -> str:
    if not args:
        return ""
    parts = [f"{a['name']}: {render_type_ref(a.get('type'))}" for a in args]
    return "(" + ", ".join(parts) + ")"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def dump_root_fields(client, as_json: bool) -> int:
    resp = client.gql(ROOT_QUERY_FIELDS)
    if "errors" in resp or "error" in resp:
        print("Introspection failed:", json.dumps(resp, indent=2), file=sys.stderr)
        return 1

    qtype = (resp.get("__type") or {})
    fields = qtype.get("fields") or []

    if as_json:
        slim = [
            {
                "name": f["name"],
                "returns": render_type_ref(f.get("type")),
                "args": {a["name"]: render_type_ref(a.get("type")) for a in (f.get("args") or [])},
                "description": f.get("description"),
            }
            for f in fields
        ]
        print(json.dumps(slim, indent=2))
        return 0

    print(f"Root Query type exposes {len(fields)} fields:\n")
    for f in sorted(fields, key=lambda x: x["name"]):
        sig = f"{f['name']}{_fmt_args(f.get('args') or [])} -> {render_type_ref(f.get('type'))}"
        print(f"  {sig}")
        desc = (f.get("description") or "").strip().replace("\n", " ")
        if desc:
            print(f"      {desc[:160]}")
    print(
        "\nNext: pick the field(s) that look like transactions / financials / "
        "contracts / freelancers, then run:\n"
        "  python pipeline/discover_schema.py --type <ReturnTypeName>\n"
        "to see that type's fields. Paste the output back to finalize queries."
    )
    return 0


def dump_type(client, type_name: str, as_json: bool) -> int:
    resp = client.gql(TYPE_FIELDS, {"name": type_name})
    if "errors" in resp or "error" in resp:
        print("Introspection failed:", json.dumps(resp, indent=2), file=sys.stderr)
        return 1
    t = resp.get("__type")
    if not t:
        print(f"No type named {type_name!r} found. Check spelling/case.", file=sys.stderr)
        return 1

    if as_json:
        print(json.dumps(t, indent=2))
        return 0

    print(f"Type {t['name']} ({t.get('kind')})")
    if t.get("description"):
        print(f"  {t['description'].strip()[:200]}")
    if t.get("enumValues"):
        print("  enum values:", ", ".join(v["name"] for v in t["enumValues"]))
    for f in t.get("fields") or []:
        sig = f"{f['name']}{_fmt_args(f.get('args') or [])} -> {render_type_ref(f.get('type'))}"
        print(f"  {sig}")
        desc = (f.get("description") or "").strip().replace("\n", " ")
        if desc:
            print(f"      {desc[:160]}")
    for f in t.get("inputFields") or []:
        print(f"  [input] {f['name']}: {render_type_ref(f.get('type'))}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--type", help="Dump fields of a specific type instead of root Query fields.")
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = ap.parse_args()

    client = get_client()
    if args.type:
        return dump_type(client, args.type, args.json)
    return dump_root_fields(client, args.json)


if __name__ == "__main__":
    raise SystemExit(main())
