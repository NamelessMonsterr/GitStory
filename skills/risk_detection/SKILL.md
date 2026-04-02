# Skill: risk-detection

## Purpose

Transforms pattern analysis into **decision intelligence** by flagging
unstable, fragile, or high-risk development patterns. This skill elevates
GitStory from a retrospective analysis tool to a forward-looking risk
assessment system.

## Risk Signals

| Signal | Detection | Severity |
|--------|-----------|----------|
| Production Instability | Hotfix phase + high commit frequency + fix density >60% | CRITICAL/HIGH |
| Fragile Code | Same files modified 5+ times across commits | HIGH/MEDIUM |
| Bus Factor Risk | Single author responsible for >80% of critical-path commits | HIGH |
| Quality Erosion | High-churn phase with zero test file changes | MEDIUM |
| Fatigue Signal | Declining message length + increasing commit frequency over time | MEDIUM |
| No Stabilization | Feature phases not followed by test/CI work | LOW |

## Output

