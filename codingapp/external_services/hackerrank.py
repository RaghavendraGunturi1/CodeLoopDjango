import requests
import json
import re

def fetch_hackerrank_stats(username):
    """
    Fetch Hackos count and badges from HackerRank public profile.
    Uses embedded JSON inside HTML (safe method).
    """

    url = f"https://www.hackerrank.com/{username}"

    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "text/html",
            },
            timeout=10
        )

        if response.status_code != 200:
            return None

        html = response.text

        # 🔎 Extract embedded JSON
        match = re.search(r"window\.__INITIAL_STATE__\s*=\s*({.*?});", html, re.S)

        if not match:
            return None

        data = json.loads(match.group(1))

        profile = data.get("profile", {})
        badges = profile.get("badges", [])
        hackos = profile.get("hackos", 0)

        badge_list = [
            {
                "name": b.get("badge_name"),
                "level": b.get("level"),
            }
            for b in badges
        ]

        return {
            "username": username,
            "hackos": hackos,
            "total_badges": len(badge_list),
            "badges": badge_list,
            "profile_url": url,
        }

    except Exception as e:
        print("HackerRank fetch error:", e)
        return None
