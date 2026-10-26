---
description: Execute a new task (Plan -> Execute)
---
# WORKFLOW: NEW TASK (System Orchestrator)

**TRIGGER:** /new-task [input]

## STEP 1: CONTEXT & TRANSLATION

1. **Context Check:**
   - Read `@.agent/rules/watchdog.md`.
   - Read `@.agent/rules/anti-patterns.md`.
   - Read `@.agent/rules/stack-expert.md`.
   - Read `@PROJECT-PLAN.md` (Current Focus).
   - Check active file structure (`tree` or `ls`).

2. **Intent Detection:**
   - **EXECUTE:** Building/Fixing -> Target: `/run-feature` (implicit) or `/run-fix`.
   - **IDEATE:** Future idea/Backlog -> Target: `/update-plan`.

## STEP 2: GOD PROMPT DRAFTING

Draft a detailed technical plan using the input.
**Action:** Create a **Native Implementation Plan Artifact** containing:
1. The Technical Spec.
2. The specific file paths to touch.
3. The definition of done.

## STEP 3: APPROVAL GATE

**Output:**
"""
📋 **PLAN READY**
**Target:** [Target Workflow]
**Persona:** [Selected Persona]

[Display the Implementation Plan Artifact]

👉 **Type 'Y' to Auto-Execute this plan.**
"""

## STEP 4: AUTO-TRIGGER

**Logic:**
- **IF** Input == "Y":
  - **Action:** Call [Target Workflow] passing the plan as `{{input}}`.
- **ELSE**:
  - **Action:** Rewrite Plan Artifact based on feedback.
