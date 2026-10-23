---
description: Commit work and update status
---

# WORKFLOW: WRAP

**TRIGGER:** /wrap

## STEP 1: INPUT DECRYPTION

1. **Analyze:** "{{input}}" (Optional user comments).
2. **Translate:** Format for Git Commit Body.

## STEP 2: ACTION

1. `git status` check.
2. Update `@PROJECT-PLAN.md` (Mark Done).
3. Generate Conventional Commit.
4. `git commit`.
5. Output: "✅ Saved & Clean."
