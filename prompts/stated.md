From the person's OWN text only (Instagram bio and own captions, LinkedIn about, own posts, causes, volunteering), extract explicit statements on: relationship_intent, family_plans, faith_practice, diet, political_stance, causes, languages, location_relocation.

Output a JSON array only. Each item: {"topic", "value", "quote", "ref", "value_normalized"}.
- quote must be an exact substring of the text you were given. ref is the ref of the block it came from.
- If nothing is stated for a topic, omit it. Never guess. Most people state few or none; an empty array [] is a normal answer.
- value_normalized: for family_plans one of wants_kids | no_kids | open; for relationship_intent one of long_term | casual | open; for location_relocation an object {"country": "...", "open_to_relocate": true|false}; otherwise null.
- family_plans is only about having children or starting a family. Pets, partners and living arrangements are NOT family plans.
- Never extract gender identity, sexual orientation, health or disability, caste or immigration status, even if stated.
