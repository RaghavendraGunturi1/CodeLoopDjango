import requests
import re
from bs4 import BeautifulSoup

def _extract_int(text):
    if not text:
        return None
    m = re.search(r"\d+", text)
    return int(m.group()) if m else None


def fetch_codechef_stats(username):
    url = f"https://www.codechef.com/users/{username}"

    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )

        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        # Rating
        rating = _extract_int(
            soup.find("div", class_="rating-number").text
            if soup.find("div", class_="rating-number") else None
        )

        # Stars
        stars = (
            soup.find("span", class_="rating").text.strip()
            if soup.find("span", class_="rating") else None
        )

        # Highest Rating
        highest_rating = None
        for li in soup.select(".rating-data-section ul li"):
            if "Highest Rating" in li.text:
                highest_rating = _extract_int(li.text)

        # Global & Country Rank
        ranks = soup.select(".rating-ranks li strong")
        global_rank = _extract_int(ranks[0].text) if len(ranks) > 0 else None
        country_rank = _extract_int(ranks[1].text) if len(ranks) > 1 else None

        # ✅ Problems Solved (FINAL VERIFIED FIX)
        solved_count = 0
        page_text = soup.get_text(separator=" ").lower()
        if "total problems solved" in page_text:
            after = page_text.split("total problems solved", 1)[1]
            solved_count = _extract_int(after) or 0

        return {
            "username": username,
            "rating": rating,
            "highest_rating": highest_rating,
            "stars": stars,
            "global_rank": global_rank,
            "country_rank": country_rank,
            "problems_solved": solved_count,
        }

    except Exception as e:
        print("CodeChef fetch error:", e)
        return None
