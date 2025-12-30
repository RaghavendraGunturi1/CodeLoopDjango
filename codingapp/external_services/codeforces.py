import requests
from collections import defaultdict

CODEFORCES_INFO_API = "https://codeforces.com/api/user.info"
CODEFORCES_STATUS_API = "https://codeforces.com/api/user.status"


def fetch_codeforces_stats(username):
    """
    Fetch detailed Codeforces statistics:
    - rating info
    - total solved problems
    - accepted submissions
    - contest count
    - language usage
    """

    try:
        # -----------------------
        # 1. Basic user info
        # -----------------------
        info_resp = requests.get(
            CODEFORCES_INFO_API,
            params={"handles": username},
            timeout=10
        )
        info_data = info_resp.json()

        if info_data.get("status") != "OK":
            return None

        user = info_data["result"][0]

        # -----------------------
        # 2. Submission history
        # -----------------------
        status_resp = requests.get(
            CODEFORCES_STATUS_API,
            params={"handle": username},
            timeout=10
        )
        status_data = status_resp.json()

        if status_data.get("status") != "OK":
            return None

        submissions = status_data["result"]

        solved_problems = set()
        accepted_count = 0
        contests = set()
        languages = defaultdict(int)

        for sub in submissions:
            if sub.get("verdict") == "OK":
                problem = sub.get("problem", {})
                problem_id = f"{problem.get('contestId')}-{problem.get('index')}"
                solved_problems.add(problem_id)
                accepted_count += 1

                if sub.get("contestId"):
                    contests.add(sub.get("contestId"))

                lang = sub.get("programmingLanguage")
                if lang:
                    languages[lang] += 1

        return {
            # Basic info
            "handle": user.get("handle"),
            "rating": user.get("rating"),
            "max_rating": user.get("maxRating"),
            "rank": user.get("rank"),
            "max_rank": user.get("maxRank"),
            "contribution": user.get("contribution"),
            "organization": user.get("organization"),
            "avatar": user.get("avatar"),

            # Problem stats
            "total_problems_solved": len(solved_problems),
            "accepted_submissions": accepted_count,
            "contests_participated": len(contests),

            # Languages
            "languages": dict(languages),
        }

    except Exception:
        return None
