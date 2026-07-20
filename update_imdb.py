# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""Fetch the IMDb watchlist and update README.md.

IMDb's web pages sit behind an AWS WAF JavaScript challenge that plain HTTP
clients can't solve, so we talk to IMDb's public GraphQL endpoint instead
(the same one the site's frontend uses). The share link only exposes a new
"profile id" handle, which we first resolve to the classic `ur...` user id.
"""

import json
import re
import urllib.request

# Profile id from the watchlist share link:
# https://www.imdb.com/user/<PROFILE_ID>/watchlist/
PROFILE_ID = "p.pkvt3c4nyvbmduk765nreda5ya"
GRAPHQL_URL = "https://caching.graphql.imdb.com/"
# IMDb serves an empty body / bot challenge without a realistic desktop UA.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
)
PAGE_SIZE = 250

README_PATH = "README.md"
START_MARKER = "<!-- IMDB_START -->"
END_MARKER = "<!-- IMDB_END -->"


def _graphql(query: str, variables: dict) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={"content-type": "application/json", "user-agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode())
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload["data"]


def resolve_user_id(profile_id: str) -> str:
    """Map a share-link profile id (`p...`) to a classic user id (`ur...`)."""
    query = (
        "query($p:ID!){ userProfile(input:{profileId:$p}){ userId } }"
    )
    return _graphql(query, {"p": profile_id})["userProfile"]["userId"]


def fetch_films() -> list[dict]:
    user_id = resolve_user_id(PROFILE_ID)
    query = """
    query($u:ID!,$after:ID){
      predefinedList(classType:WATCH_LIST, userId:$u){
        items(first:%d, after:$after){
          pageInfo{ hasNextPage endCursor }
          edges{ node{ listItem{ __typename
            ... on Title { id titleText{text} releaseYear{year} }
          } } }
        }
      }
    }
    """ % PAGE_SIZE

    films = []
    after = None
    while True:
        items = _graphql(query, {"u": user_id, "after": after})[
            "predefinedList"
        ]["items"]
        for edge in items["edges"]:
            item = edge["node"]["listItem"]
            if item.get("__typename") != "Title":
                continue
            films.append(
                {
                    "name": item["titleText"]["text"],
                    "year": (item.get("releaseYear") or {}).get("year"),
                    "id": item["id"],
                }
            )
        page = items["pageInfo"]
        if not page["hasNextPage"]:
            break
        after = page["endCursor"]
    return films


def build_section(films: list[dict]) -> str:
    lines = []
    for film in films:
        url = f"https://www.imdb.com/title/{film['id']}/"
        year = f" ({film['year']})" if film["year"] else ""
        lines.append(f"- [{film['name']}{year}]({url})")
    return "\n".join(lines)


def update_readme(section: str) -> None:
    with open(README_PATH) as f:
        content = f.read()

    pattern = re.compile(
        rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}",
        re.DOTALL,
    )
    replacement = f"{START_MARKER}\n{section}\n{END_MARKER}"
    content = pattern.sub(replacement, content)

    with open(README_PATH, "w") as f:
        f.write(content)


def main() -> None:
    films = fetch_films()
    section = build_section(films)
    update_readme(section)
    print(f"Updated README with {len(films)} films from IMDb.")


if __name__ == "__main__":
    main()
