"""SYNTHETIC DEV FIXTURES. Fictional people, not real; used only to exercise the pipeline and UI
before the real 25 are sourced (SPEC §18). Output matches the Apify shapes in SPEC §6.1.
Never ship these as the demo pool."""
from datetime import datetime, timedelta, timezone

NOW = datetime(2026, 9, 20, tzinfo=timezone.utc)

# name, handle, city, headline, about, jobs[(title, company, start_year, end_year|None)], edu, skills,
# li_posts, ig_bio, ig_posts[(caption, song|None, kind)]
PEOPLE = [
    ("Meera Iyer", "meera.makes", "Bengaluru, India", "Product designer at a fintech",
     "I design money apps people actually understand. Outside work: ceramics and long-distance cycling.",
     [("Product Designer", "Razorbyte", 2022, None), ("Designer", "Studio Kaapi", 2019, 2022)],
     ("NID Ahmedabad", "B.Des", "Design"), ["Figma", "Design systems", "User research"],
     ["Shipped our new onboarding after 14 rounds of testing. Most of the wins were deleting things.",
      "Hot take: a good empty state is worth three feature launches."],
     "ceramics • cycling • bangalore", [
         ("Wobbly bowl no. 12. The glaze finally behaved.", None, "Image"),
         ("120 km before breakfast. Legs: gone. Mood: great.", "Kho Gaye Hum Kahan", "Video"),
         ("Sunday market haul, mostly tomatoes.", None, "Sidecar"),
         ("Kiln day #hobby #clay", None, "Image"),
         ("Back at the wheel. Slowly learning to centre.", "Sunflower", "Video")]),
    ("Arjun Nair", "arjun.runs.things", "Mumbai, India", "Investment analyst, long-only equities",
     "Reading annual reports for fun. I want a life with a good routine, a dog and a long-term partner.",
     [("Analyst", "Halcyon Capital", 2021, None), ("Associate", "BlueRiver Advisory", 2018, 2021)],
     ("SP Jain", "MBA", "Finance"), ["Equity research", "Valuation", "Excel"],
     ["Our best idea this year was the one we did nothing on for eight months.",
      "Reading list this quarter: Berkshire letters, one novel, one cookbook."],
     "markets by day, marathon training by night. dog dad soon. looking for something long term.", [
         ("5 am long run along Marine Drive. 28 km done.", None, "Image"),
         ("Annual report season. This is my idea of fun.", None, "Image"),
         ("Sunday roast attempt number 3. Better.", "Cruel Summer", "Video"),
         ("Race day. Sub 4 hours, finally.", "Eye of the Tiger", "Video")]),
    ("Zoya Khan", "zoya.on.road", "Delhi, India", "Documentary filmmaker and freelance editor",
     None,
     [("Freelance editor", "Self-employed", 2020, None), ("Assistant editor", "Hidden Lens Films", 2017, 2020)],
     ("Jamia Millia Islamia", "MA", "Mass Communication"), ["Premiere Pro", "Storytelling", "Documentary"],
     ["Eleven months on one 52 minute film. Worth every frame.",
      "Always carry a spare memory card. Learn from my mistakes."],
     "frames + chai | travel with a camera | always between cities", [
         ("Three trains, one bus, zero sleep. Spiti was worth it.", "Tum Se", "Sidecar"),
         ("Edit suite at 2 am. Cutting the last scene again.", None, "Image"),
         ("Chai at a dhaba outside Kullu.", None, "Image"),
         ("Wanderer", "Ae Dil Hai Mushkil", "Video")]),
    ("Rohan Desai", "rohan.d.codes", "Pune, India", "Staff engineer, infrastructure",
     "Distributed systems, boring technology, board games. I would rather fix the root cause than the symptom.",
     [("Staff Engineer", "Latticeworks", 2020, None), ("Senior Engineer", "Nimbus Labs", 2016, 2020),
      ("Engineer", "TCS", 2012, 2016)],
     ("COEP Pune", "B.Tech", "Computer Science"), ["Kubernetes", "Go", "Postgres", "Mentoring"],
     ["We cut p99 latency by 70 percent by removing a cache. Sometimes the answer is less.",
      "Wrote down our on-call rules in one page. Fewer pages, fewer pages at 3 am."],
     "systems, boardgames, filter coffee. not looking for a fling.", [
         ("Game night. I lost Catan to my own sister.", None, "Image"),
         ("Home brewed filter coffee ritual.", None, "Image"),
         ("Hiking Rajmachi for the fifth time.", "Zindagi Na Milegi Dobara", "Video")]),
    ("Sana Mirza", "sana.moves", "Hyderabad, India", "Physiotherapist and yoga teacher",
     "Helping people move without pain. Weekends: temple dance classes, trek planning, long family lunches.",
     [("Senior Physiotherapist", "MoveWell Clinic", 2019, None)],
     ("Osmania University", "BPT", "Physiotherapy"), ["Rehabilitation", "Yoga", "Patient education"],
     ["Posture advice nobody wants: stand up every 30 minutes. That is it.",
      "Teaching a free community class every Sunday morning."],
     "movement • yoga • Hyderabad • teach Sundays", [
         ("Sunday community class, 30 people this week!", None, "Image"),
         ("Trek to Anantagiri hills with the girls.", "Tum Hi Ho", "Video"),
         ("Cooking biryani with Ammi, learning the secrets.", None, "Sidecar")]),
    ("Kabir Malhotra", "kabir_goes_wild", "Gurugram, India", "Founder, seed-stage logistics startup",
     "Building supply chain tooling for small manufacturers. Sleep is for people who've raised their Series A.",
     [("Founder and CEO", "Cargolane", 2023, None), ("Product Manager", "Swiftkart", 2019, 2023)],
     ("IIT Delhi", "B.Tech", "Mechanical Engineering"), ["Fundraising", "Operations", "Product"],
     ["Eight no's before the first yes. The yes changed everything.",
      "We shipped to 40 factories this quarter. Hiring ops and engineers."],
     "founder. 5am club. open to relocating for the right thing.", [
         ("Closing the seed round. Thank you to everyone who believed.", None, "Image"),
         ("Gym at 5 am, calls at 7.", "Believer", "Video"),
         ("Goa offsite with the team.", None, "Sidecar"),
         ("Late night in the warehouse.", None, "Image")]),
    ("Tara Dsouza", "tara.in.the.hills", "Goa, India", "Marine biologist and science writer",
     "Studying coral reefs and writing about them in plain language. I want a partner who likes the sea and quiet mornings.",
     [("Research Fellow", "CSIR NIO", 2021, None), ("Research Assistant", "TERI", 2019, 2021)],
     ("Goa University", "MSc", "Marine Science"), ["Scientific writing", "Scuba", "Field research"],
     ["Coral bleaching update from our Lakshadweep survey. The recovery was a surprise.",
      "Wrote a short explainer on reef science for kids. Sharing soon."],
     "reefs, writing, sunrise swims. wants kids someday. loves goa.", [
         ("Reef survey. Four dives, one very patient octopus.", None, "Image"),
         ("Sunrise swim before the lab.", "Naina", "Video"),
         ("Writing day, rain outside.", None, "Image")]),
    ("Vikram Rao", "vik.rao.official", "Chennai, India", "Management consultant",
     "Strategy, operations, travel. Currently on a client project in Singapore, home base Chennai.",
     [("Consultant", "Meridian Group", 2022, None), ("Analyst", "Meridian Group", 2020, 2022)],
     ("IIM Bangalore", "MBA", "Strategy"), ["Strategy", "Slides", "Negotiation"],
     ["Seven airports in five days. Lounge coffee tastes the same everywhere.",
      "Three rules I use to run a project post-mortem in under an hour."],
     "consulting. frequent flyer. chennai/singapore. not trying to settle down yet.", [
         ("Airport number six this week.", None, "Image"),
         ("Marina Bay at night.", "Blinding Lights", "Video"),
         ("Dinner with the team, finally.", None, "Image"),
         ("Chennai filter coffee, the only real kind.", None, "Image")]),
]


def _ts(dt):
    return dt.isoformat().replace("+00:00", "Z")


def build(i: int) -> dict:
    (name, handle, city, headline, about, jobs, edu, skills, li_posts, bio, ig_posts) = PEOPLE[i]
    first, last = name.split(" ", 1)
    li_id = name.lower().replace(" ", "-")
    pid = li_id
    ig_latest = []
    for k, (cap, song, kind) in enumerate(ig_posts):
        ig_latest.append({
            "type": kind, "productType": "clips" if kind == "Video" else None, "shortCode": f"{handle[:4]}{k}x{i}",
            "caption": cap, "hashtags": [], "mentions": [], "taggedUsers": [], "isPinned": k == 0 and i % 3 == 0,
            "timestamp": _ts(NOW - timedelta(days=9 * (k + 1))), "likesCount": 80 + 17 * k + i * 11,
            "commentsCount": 3 + k, "displayUrl": f"https://scontent.cdninstagram.com/{handle}/{k}.jpg",
            "musicInfo": ({"song_name": song, "artist_name": "Various", "uses_original_audio": False}
                          if song else {"uses_original_audio": True}),
        })
    ig = [{"username": handle, "fullName": name, "biography": bio, "followersCount": 400 + 90 * i,
           "followsCount": 300, "postsCount": 60 + i * 4, "private": False, "verified": False,
           "isBusinessAccount": False, "latestPosts": ig_latest}]
    li = [{"firstName": first, "lastName": last, "publicIdentifier": li_id, "headline": headline,
           "about": about, "location": {"parsed": {"city": city.split(",")[0], "state": None,
                                                    "country": city.split(", ")[-1]}},
           "experience": [{"position": t, "companyName": c, "startDate": str(s), "endDate": str(e) if e else "present",
                           "description": None} for t, c, s, e in jobs],
           "education": [{"schoolName": edu[0], "degree": edu[1], "fieldOfStudy": edu[2]}],
           "skills": [{"name": s} for s in skills]}]
    posts = [{"id": f"{i}{k}", "content": t, "postedAt": {"timestamp": int((NOW - timedelta(days=20 * (k + 1))).timestamp() * 1000)},
              "author": {"publicIdentifier": li_id}} for k, t in enumerate(li_posts)]
    return {"name": name, "linkedin_url": f"https://www.linkedin.com/in/{li_id}",
            "instagram_url": f"https://www.instagram.com/{handle}", "ig": ig, "li": li, "li_posts": posts}


def all_people() -> list[dict]:
    return [build(i) for i in range(len(PEOPLE))]
