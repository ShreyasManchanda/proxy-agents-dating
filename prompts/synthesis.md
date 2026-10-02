You are given numbered observations (with ids like "obs_3") and computed stats about one person. Fill the profile. Output one JSON object only.

Rules:
- Every claim is {"claim", "evidence": [observation ids], "confidence": 0-1}. Cite only ids that exist. A claim without evidence is dropped.
- Every item in needs, hobbies, interests, values, community_and_extras, partner_wants, contradictions and wildcards MUST be an object {"claim", "evidence", "confidence"}. Plain strings are invalid and are thrown away. Only "tags" and "conversation_hooks" and "unknowns" hold plain strings.
- If there is not enough signal for a field, return an empty list for it. Do not invent. Avoid generic filler ("curious", "driven", "loves life").
- Be specific: name the actual activities, places, tools, songs, roles from the observations.
- A contradiction must cite at least one observation from Instagram and one from LinkedIn (ids starting with obs_ are tagged with their source). Phrase it as a range ("formal on LinkedIn, playful off-hours"), never as a flaw.
- partner_wants items have a "type": "stated" (explicit), "revealed" (from behavior, e.g. what they praise or amplify) or "inferred" (logical inference from needs and lifestyle). Prefer stated and revealed.
- Do not infer sensitive attributes. Do not mention religion, orientation, health, politics, caste or immigration unless it appears in the provided stated_signals.
- "tags": pick from the allowed vocabulary only: values, lifestyle, interests (use the words exactly; no others).
- "dials": numbers 0-1 for pace (0 slow, 1 fast), social_style (0 introverted, 1 outgoing), tempo (0 measured, 1 rapid-fire). Omit a dial if there is no evidence.

Schema:
{"identity": {"name": str, "location": str|null, "languages": [str]},
 "work": {"summary": str, "role": str|null, "industry": str|null, "trajectory": str|null},
 "education": [str],
 "community_and_extras": [{"claim","evidence","confidence"}],
 "needs": [claims], "hobbies": [claims], "interests": [claims], "values": [claims],
 "communication_style": {"tempo": str, "humor": str, "formality": str, "disclosure": "open|curated|guarded"},
 "lifestyle": {"pace": str, "social_style": str, "travel": str, "aesthetic": str},
 "partner_wants": [{"claim","evidence","confidence","type"}],
 "contradictions": [claims],
 "wildcards": [claims],
 "conversation_hooks": [3-5 short strings, each a concrete thing to ask them about],
 "unknowns": [things an agent must deflect on and never invent, e.g. "family", "salary", "exes"],
 "current_season": str|null,
 "tags": {"values": [str], "lifestyle": [str], "interests": [str]},
 "dials": {"pace": num, "social_style": num, "tempo": num}}
