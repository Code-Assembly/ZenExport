---
description: Fix a specific bug in a file
---

# WORKFLOW: BUG FIX

**TRIGGER:** /run-fix

## STEP 1: INPUT DECRYPTION

1. **Analyze:** "{{input}}"
2. **Translate:** Rewrite to "Debug [File] for runtime errors."

## STEP 2: DIAGNOSE

**Act as:** [DYNAMIC_FIXER].
**Constraints:** Check `@.agent/rules/stack-expert.md`.
Fix the code.

## STEP 3: HANDOFF (NO COMMIT)

**Output:**
"""
✅ **PATCH APPLIED.**

1. **TEST IT MANUALLY.**
2. If working: `/wrap`.
"""
