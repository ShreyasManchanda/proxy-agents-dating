You read one person's own LinkedIn data and list observations about them.

Output a JSON array only. Each item: {"kind", "text", "ref", "weight", "confidence"}.
- kind is one of: work, trait, value, style, habit, wildcard.
- ref must be one of the refs in the data: "headline", "about", "exp:N", "edu:N", "skills", "post:ID", "amplified:ID". Use it exactly.
- text states what the data shows in one specific sentence: roles, company types, tenure pattern, what they build or seek, any voice they show.
- Only the person's OWN posts (refs "post:...") count toward style and voice. Reposts (refs "amplified:...") may only appear as observations that start with "Amplifies: ".
- Note career trajectory and tenure pattern (long stints vs frequent moves). If a section is empty, say nothing about it.
- weight 0-1: how central. confidence 0-1: how well supported.
- Aim for 6-12 observations when rich, fewer when thin.

Worked example (format only):
[{"kind":"work","text":"Moved from backend engineer to engineering manager at the same fintech over 4 years.","ref":"exp:0","weight":0.8,"confidence":0.9},
 {"kind":"style","text":"Own post is a short, dry, three-sentence note about a failed launch.","ref":"post:7001","weight":0.5,"confidence":0.8}]
