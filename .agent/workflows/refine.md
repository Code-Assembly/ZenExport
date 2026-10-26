---
description: Optimize a prompt before execution
---

# WORKFLOW: REFINE-PROMPT (Prompt Optimizer)

**TRIGGER:** /refine [input]

## STEP 1: CONTEXT & TRANSLATION

1. **The "Senior Dev" Filter:**
   - **Act as:** A Senior Technical Lead interpreting a client request.
   - **Input:** "{{input}}"
   - **Goal:** Rewrite the raw input into a specific Engineering Task.
   - **Logic:**
     - IF input is vague ("a bug") -> Locate error in active files & describe the fix.
     - IF input is new ("feature") -> check if it contradicts `PROJECT-PLAN.md`.

## STEP 2: OUTPUT

**Output:**
"""
🧠 **OPTIMIZED PROMPT**
Use this prompt with `/new-task`:

```text
[Insert Refined Prompt Here]
```
"""
