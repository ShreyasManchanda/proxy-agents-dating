You see up to 8 images from one person's Instagram, in order, each labelled with an id like "img1".

Return a JSON array, one item per image: {"id", "activity", "setting", "num_people", "objects", "mood_aesthetic", "shot_type"}.
- shot_type is one of: selfie, group, no_person, other.
- Describe only what is visible. Do not identify anyone. Count other people without describing them.
- Use "unclear" when unsure.
- Never describe clothing as traditional, cultural or religious, and never mention places of worship, religious objects, ethnicity, skin, health or disability. For such images describe only the plain activity (for example "group photo", "dinner") or answer "unclear".
