
# Skill: narrative-engine

## Purpose

Converts structured phase data and intent inferences into human-readable
narratives. Two configurable tones:

1. **professional** — clean, report-style summary for PRs, docs, reviews
2. **story** — engaging, character-driven storytelling (GitStory signature)

## Inputs

| Input       | Type                   | Description                  |
|-------------|------------------------|------------------------------|
| phases      | `list[Phase]`          | From deep-history-analysis   |
| inferences  | `list[IntentInference]`| From intent-inference        |
| repo_name   | `str`                  | Repository name              |
| tone        | `str`                  | `"professional"` or `"story"`|

## Outputs

| Output    | Type  | Description                    |
|-----------|-------|--------------------------------|
| narrative | `str` | Complete markdown document     |

## Sections Generated

### Professional Mode
1. Header — repo name, date range, commit/phase/author counts
2. Executive Summary — 2-3 sentences
3. Phase Analysis — one section per phase with metrics, intent, evidence
4. Dividers between sections

### Story Mode
1. Title — "The Story of `repo-name`"
2. Opening line — sets the scene based on phase count
3. Chapters — one per phase with:
   - Date range, commit count, duration
   - Observation text
   - Intent summary in narrative voice
   - Confidence note in natural language
   - Reasoning bullets
   - Key files mentioned
4. "The Big Picture" — cross-phase patterns and overall assessment

## Design Rules

- Never invents data not present in the structured input
- Professional mode: factual, no personality
- Story mode: uses SOUL.md voice (sharp, observant, slightly sarcastic)
- Both modes include confidence levels and evidence citations