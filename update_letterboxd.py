# /// script
# requires-python = ">=3.14"
# dependencies = [
#   "letterboxdpy",
# ]
# ///
"""Fetch watched films from Letterboxd and update README.md."""

import re

from letterboxdpy.user import User

USERNAME = "1995parham"
README_PATH = "README.md"
START_MARKER = "<!-- LETTERBOXD_START -->"
END_MARKER = "<!-- LETTERBOXD_END -->"


def fetch_films() -> list[dict]:
    u = User(USERNAME)
    data = u.get_films()
    films = []
    for slug, film in data["movies"].items():
        films.append(
            {
                "name": film["name"],
                "year": film.get("year"),
                "slug": slug,
                "rating": film.get("rating"),
            }
        )
    return films


def build_section(films: list[dict]) -> str:
    lines = []
    for film in films:
        url = f"https://letterboxd.com/film/{film['slug']}/"
        year = f" ({film['year']})" if film["year"] else ""
        rating_val = film["rating"]
        if rating_val:
            stars = "★" * int(rating_val) + ("½" if rating_val % 1 else "")
            rating = f" {stars}"
        else:
            rating = ""
        lines.append(f"- [{film['name']}{year}]({url}){rating}")
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
    print(f"Updated README with {len(films)} films from Letterboxd.")


if __name__ == "__main__":
    main()
