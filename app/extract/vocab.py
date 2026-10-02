"""Controlled tag vocabulary (SPEC §7). Versioned and fixed: existing tags never shift."""
VOCAB_VERSION = 1

VALUES = ["family_oriented", "career_driven", "ambitious", "community_minded", "adventurous", "creative_expression",
          "independence", "stability", "kindness", "honesty", "curiosity", "tradition", "environmental_care",
          "social_impact", "learning", "work_life_balance", "faith_practice_stated", "humor", "loyalty", "frugality"]
LIFESTYLE = ["early_riser", "night_owl", "homebody", "frequent_traveler", "city_life", "outdoorsy", "social_butterfly",
             "quiet_evenings", "fitness_routine", "foodie", "home_cook", "plant_based_diet", "minimalist",
             "work_heavy", "weekend_plans_packed", "pet_owner", "live_music_goer", "spontaneous", "planner"]
INTERESTS = ["trekking", "running", "gym_training", "yoga", "cricket", "football", "cycling", "swimming", "climbing",
             "photography", "film", "music_listening", "music_making", "reading", "writing", "gaming", "board_games",
             "cooking", "baking", "coffee", "travel", "art_design", "dance", "fashion", "technology", "startups",
             "finance", "science", "volunteering", "theatre", "podcasts", "gardening", "diy_making"]

ALL = {"values": VALUES, "lifestyle": LIFESTYLE, "interests": INTERESTS}


def clean_tags(tags: dict) -> dict:
    """Drop anything outside the vocabulary (tags the model invented never reach the baselines)."""
    return {g: [t for t in dict.fromkeys((tags or {}).get(g) or []) if t in ALL[g]] for g in ALL}
