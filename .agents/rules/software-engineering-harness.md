# Software Engineering Harness & Rules

This rule defines the operational contract for AI-assisted software engineering, harmonizing **Ponytail**'s minimal-diff/YAGNI philosophy with **Everything Claude Code (ECC)** rigor, research-first discipline, and native subagent delegation.

---

## 1. Scope & Execution Hierarchy

Do not treat "always plan" and "be minimal" as conflicting. Use this scope hierarchy:

- **Trivial / Localized Task** (single-file bug fix, simple function addition, documentation typo, or direct config tweak):
  - Execute directly using **Ponytail Mode**.
  - No speculative abstractions, wrappers, or boilerplate.
  - Shortest working diff wins.
- **Non-Trivial / Multi-File / Architectural / Ambiguous Task**:
  - Follow the **Mandatory Execution Protocol**:
    1. **Research First**: Inspect local code structure, existing helpers, and upstream documentation/patterns before designing.
    2. **Plan First**: Formulate bounded milestones with acceptance criteria (via `/plan` mode or plan artifact).
    3. **Delegate**: Spawn independent subagents for research, implementation packets, or review.
    4. **Verify**: Run tests, type checks, and diff review before claiming completion.

---

## 2. Ponytail 7-Rung Decision Ladder

Before writing new code, stop at the first rung that holds:

1. **Does this need to exist at all? (YAGNI)** Skip speculative options, flags, and flexibility nobody asked for.
2. **Already in this codebase?** Search the repo. Reuse existing helpers, utilities, and components before writing new ones.
3. **Does the standard library do this?** Use standard library functions before adding custom implementations.
4. **Does a native platform feature cover it?** Platform features beat custom abstractions.
5. **Does an already-installed dependency solve it?** Use installed libraries. Never add a dependency for a few lines of logic.
6. **Can this be one line?** Make it one readable line.
7. **Only then: write the minimum code that works.**

### Ponytail Core Directives:
- **Root Cause, Not Symptom**: Before editing a shared function, grep all callers and fix the shared root cause once.
- **Deletion Beats Addition**: Prefer simplifying, consolidating, or deleting code over adding layers.
- **Shortcut Tagging**: Deliberate temporary shortcuts must be marked with: `shortcut: <the limit>, <when to upgrade>`.
- **Never Cut**: Validation at trust boundaries, security invariants, error handling that prevents data loss, or accessibility.

---

## 3. Explicit Subagent Utilization Policy

Do not perform non-trivial multi-stream tasks solely in the main agent's context.

### Delegation Thresholds:
- **Trivial task**: Main agent only.
- **Standard non-trivial task** (research + implementation, multi-file change, or test diagnosis): Delegate at least one independent workstream. Target **2 total workers**.
- **Large / complex task** (4+ files, multi-layer architecture, refactor): Coordinate **2–4 concurrent subagents** with distinct deliverables:
  - `researcher` (read-only): Investigates structure, callers, docs, and external libraries.
  - `implementer` / `tdd-guide`: Implements bounded, non-overlapping work packets.
  - `build-error-resolver`: Reproduces test failures and pinpoints root causes.
  - `code-reviewer` (read-only): Performs fresh-context diff review on the final patch.

### Subagent Prompting Contract:
- Every subagent prompt must be **self-contained** (goals, paths, constraints, deliverable format).
- Agents never edit overlapping files concurrently.
- The main agent integrates results, runs final checks, and remains accountable.

---

## 4. Correctness Gates & TDD

- **Tests Before Code (TDD)**: For new non-trivial logic, write the failing test first, verify failure (RED), implement minimal code (GREEN), and refactor.
- **Coverage**: Aim for 80%+ test coverage on modified code. Critical paths require 100%.
- **Evidence Over Assumption**:
  - Run the narrowest relevant test first, then the suite.
  - Inspect `git diff` for unintended edits, debug leftovers, or weak assertions.
  - Never fake success: commands not run are `NOT RUN`; failures are `FAIL`.

---

## 5. Anti-Loop & Anti-Drift Protocol

- **Detect Repeated Failure**: If a fix or command fails twice, stop repeating it. Re-read the full error trace, revise the hypothesis, or delegate root-cause analysis to `build-error-resolver`.
- **Bound Retries**: After 3 distinct failed hypotheses, pause and summarize findings, attempted fixes, and next steps to the user.
- **Durable State**: Update plan milestones as work proceeds so session resumption preserves context.
