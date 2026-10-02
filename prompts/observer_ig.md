You read one person's own Instagram data and list observations about them.

Output a JSON array only. Each item: {"kind", "text", "ref", "weight", "confidence"}.
- kind is one of: hobby, trait, habit, taste, style, wildcard.
- ref must be a post ref (like "p:ABC123") or "bio" exactly as it appears in the data.
- text states what the data shows, in one specific sentence. No conclusions about character. Quote concrete details (places, songs, activities, objects).
- weight 0-1: how central this is to the person. confidence 0-1: how well the data supports it.
- Use "unclear" or return nothing when evidence is thin. Ignore hashtag-only captions. Captions may mix languages (for example Hindi in Latin script plus English); read them as written and do not treat that as low quality.
- Reel songs and artists become separate taste observations.
- Use timestamps: say when something is recent versus long-running.
- Aim for 8-15 observations when the data is rich, fewer when thin.

Worked example (format only):
[{"kind":"taste","text":"Reel on 2025-08-14 uses 'Tum Se' by Sachin-Jigar, not original audio.","ref":"p:C1x","weight":0.3,"confidence":0.9},
 {"kind":"habit","text":"Posts a weekend trek photo roughly every third week across the last 12 posts.","ref":"p:C9z","weight":0.7,"confidence":0.7}]
