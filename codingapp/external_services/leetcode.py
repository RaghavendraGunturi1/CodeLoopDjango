import requests

LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql/"


def fetch_leetcode_stats(username):
    """
    Stable LeetCode stats fetch (2025).
    Uses ONLY matchedUser + submitStatsGlobal + profile.
    """

    query = """
    query userProfile($username: String!) {
      matchedUser(username: $username) {
        username
        profile {
          ranking
          reputation
        }
        submitStatsGlobal {
          acSubmissionNum {
            difficulty
            count
          }
        }
      }
    }
    """

    try:
        response = requests.post(
            LEETCODE_GRAPHQL_URL,
            json={
                "query": query,
                "variables": {"username": username},
            },
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://leetcode.com",
                "Origin": "https://leetcode.com",
            },
            timeout=10,
        )

        data = response.json()

        # 🔎 TEMP DEBUG (keep for now)
        print("LEETCODE RAW RESPONSE:", data)

        user = data.get("data", {}).get("matchedUser")

        if not user or not user.get("submitStatsGlobal"):
            return None

        solved = {
            item["difficulty"].lower(): item["count"]
            for item in user["submitStatsGlobal"]["acSubmissionNum"]
        }

        return {
            "username": username,
            "total_solved": solved.get("all", 0),
            "easy_solved": solved.get("easy", 0),
            "medium_solved": solved.get("medium", 0),
            "hard_solved": solved.get("hard", 0),
            "ranking": user.get("profile", {}).get("ranking"),
            "reputation": user.get("profile", {}).get("reputation"),
        }

    except Exception as e:
        print("LeetCode fetch exception:", e)
        return None
