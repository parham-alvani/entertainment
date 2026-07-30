# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""Fetch the IMDb watchlist and favorite people, and update README.md.

IMDb's web pages sit behind an AWS WAF JavaScript challenge that plain HTTP
clients can't solve, so we talk to IMDb's public GraphQL endpoint instead
(the same one the site's frontend uses). The share link only exposes a new
"profile id" handle, which we first resolve to the classic `ur...` user id.

Both lists are predefined lists (`WATCH_LIST` and `FAVORITE_ACTORS`), and both
have to be set to public in IMDb's privacy settings — otherwise the API answers
with `FORBIDDEN: Permission denied` even for the owner's own anonymous request.
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
PEOPLE_START_MARKER = "<!-- IMDB_PEOPLE_START -->"
PEOPLE_END_MARKER = "<!-- IMDB_PEOPLE_END -->"


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


def fetch_list_items(user_id: str, class_type: str, item_fields: str) -> list[dict]:
    """Page through a predefined list, yielding the raw `listItem` nodes."""
    query = """
    query($u:ID!,$after:ID){
      predefinedList(classType:%s, userId:$u){
        items(first:%d, after:$after){
          pageInfo{ hasNextPage endCursor }
          edges{ node{ listItem{ __typename %s } } }
        }
      }
    }
    """ % (class_type, PAGE_SIZE, item_fields)

    items = []
    after = None
    while True:
        page = _graphql(query, {"u": user_id, "after": after})[
            "predefinedList"
        ]["items"]
        items.extend(edge["node"]["listItem"] for edge in page["edges"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]
    return items


def fetch_films(user_id: str) -> list[dict]:
    fields = "... on Title { id titleText{text} releaseYear{year} }"
    return [
        {
            "name": item["titleText"]["text"],
            "year": (item.get("releaseYear") or {}).get("year"),
            "id": item["id"],
        }
        for item in fetch_list_items(user_id, "WATCH_LIST", fields)
        if item.get("__typename") == "Title"
    ]


def fetch_people(user_id: str) -> list[dict]:
    fields = """
    ... on Name {
      id
      nameText{text}
      primaryProfessions{ category{text} }
      knownFor(first:1){ edges{ node{ title{
        titleText{text} releaseYear{year}
      } } } }
    }
    """
    people = []
    for item in fetch_list_items(user_id, "FAVORITE_ACTORS", fields):
        if item.get("__typename") != "Name":
            continue
        professions = [
            profession["category"]["text"]
            for profession in (item.get("primaryProfessions") or [])
        ]
        known_for = (item.get("knownFor") or {}).get("edges") or []
        title = known_for[0]["node"]["title"] if known_for else None
        people.append(
            {
                "name": item["nameText"]["text"],
                "id": item["id"],
                "profession": professions[0] if professions else None,
                "known_for": title["titleText"]["text"] if title else None,
                "known_for_year": (
                    (title.get("releaseYear") or {}).get("year") if title else None
                ),
            }
        )
    return people


def build_section(films: list[dict]) -> str:
    lines = []
    for film in films:
        url = f"https://www.imdb.com/title/{film['id']}/"
        year = f" ({film['year']})" if film["year"] else ""
        lines.append(f"- [{film['name']}{year}]({url})")
    return "\n".join(lines)


def build_people_section(people: list[dict]) -> str:
    lines = []
    for person in people:
        url = f"https://www.imdb.com/name/{person['id']}/"
        notes = []
        if person["profession"]:
            notes.append(person["profession"])
        if person["known_for"]:
            year = (
                f" ({person['known_for_year']})" if person["known_for_year"] else ""
            )
            notes.append(f"known for {person['known_for']}{year}")
        suffix = f" — {', '.join(notes)}" if notes else ""
        lines.append(f"- [{person['name']}]({url}){suffix}")
    return "\n".join(lines)


def update_readme(sections: dict[tuple[str, str], str]) -> None:
    with open(README_PATH) as f:
        content = f.read()

    for (start, end), section in sections.items():
        pattern = re.compile(
            rf"{re.escape(start)}.*?{re.escape(end)}",
            re.DOTALL,
        )
        replacement = f"{start}\n{section}\n{end}"
        content, count = pattern.subn(replacement, content)
        if not count:
            raise RuntimeError(f"marker block {start} not found in {README_PATH}")

    with open(README_PATH, "w") as f:
        f.write(content)


def main() -> None:
    user_id = resolve_user_id(PROFILE_ID)
    films = fetch_films(user_id)
    people = fetch_people(user_id)
    update_readme(
        {
            (START_MARKER, END_MARKER): build_section(films),
            (PEOPLE_START_MARKER, PEOPLE_END_MARKER): build_people_section(people),
        }
    )
    print(
        f"Updated README with {len(films)} films "
        f"and {len(people)} favorite people from IMDb."
    )


if __name__ == "__main__":
    main()
