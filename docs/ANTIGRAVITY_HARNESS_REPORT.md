# Antigravity Software Engineering Harness Upgrade Report

**Date & Time**: 2026-10-20T17:40:00+05:30  
**Host Environment**: Windows 11 Desktop (x64), Shell: PowerShell  
**Antigravity Surface**: Google Antigravity IDE (Electron standalone application, v2.24.0.0, install path: `C:\Users\Hp\AppData\Local\Programs\antigravity`)  
**Active Project Workspace**: `c:\Users\Hp\Documents\GitHub\settle_ai`  
**Git Working Tree Status**: Clean (0 tracked modifications; newly added untracked harness files: `AGENTS.md`, `.agents/`)  
**Python Runtime**: Python 3.11.9 (`C:\Users\Hp\AppData\Local\Programs\Python\Python311\python.exe`)  
**Node.js / npm Status**: Not installed in PATH (`git` and `python` available)

---

## 1. Environment & Surface Verification

- **Antigravity IDE vs. CLI**: Detected Antigravity IDE (VS Code-based AI-first integrated development environment coexisting with Antigravity 2.0 app architecture).
- **Workspace Customization Root**: `.agents/` (canonical Antigravity 2.0 root) at repository root `c:\Users\Hp\Documents\GitHub\settle_ai`.
- **Global App Customization Root**: `~/.gemini/config/` (resolved on Windows to `C:\Users\Hp\.gemini\config`).
- **Global Discovery Path**: `C:\Users\Hp\.gemini\config\skills/` and `C:\Users\Hp\.gemini\config\skills.json`.
- **Legacy Compatibility Check**: No legacy `.agent/` or `.workflow` files were active in the workspace or home root; no migration was required.

---

## 2. Initial Customization Paths & Skill Count

Before modifications, discovery across user locations revealed **56 total existing skills**:

1. **User Dot-Dir Skills (`C:\Users\Hp\.agents\skills/`)**: 26 skills
   - `automate`, `autopilot`, `canvas`, `create-hook`, `create-rule`, `create-skill`, `create-subagent`, `deploy-with-vercel`, `goal`, `loop`, `migrate-to-skills`, `new-repo`, `onboard`, `origin`, `rename-chat`, `review`, `review-bugbot`, `review-security`, `sdk`, `share`, `shell`, `split-to-prs`, `statusline`, `update-cli-config`, `update-cursor-settings`, `visualize`.
   - *Note*: These 26 skills resided in `C:\Users\Hp\.agents\skills` (the user's home directory root, not a Git repository root), so projects like `settle_ai` could not automatically inherit them without a global or workspace mapping.
2. **Global Plugins (`C:\Users\Hp\.gemini\config\plugins/`)**: 22 skills
   - `chrome-devtools-plugin` (6 skills: `a11y-debugging`, `chrome-devtools`, `cookie-debugging`, `debug-optimize-lcp`, `memory-leak-debugging`, `troubleshooting`)
   - `firebase` (13 skills: `extension_to_functions_codebase`, `firebase_ai_logic_basics`, `firebase_app_hosting_basics`, `firebase_auth_basics`, `firebase_basics`, `firebase_crashlytics`, `firebase_data_connect_basics`, `firebase_firestore`, `firebase_hosting_basics`, `firebase_remote_config_basics`, `firebase_security_rules_auditor`, `firestore_rules_creation`, `xcode_project_setup`)
   - `gemini-api` (3 skills: `gemini-api-dev`, `gemini-live-api-dev`, `gemini-omni-flash-api`)
3. **Application Builtin Skills (`C:\Users\Hp\.gemini\antigravity\builtin\skills/`)**: 8 skills
   - `agy-customizations`, `antigravity_guide`, `automation`, `generative_ui`, `migrate-workflows`, `permissioned-github`, `plugin`, `ui-plugin-navigation`.
4. **Ponytail Initial Status**: Ponytail was not present on disk in active directories prior to this run (documented by deep file searches); it was fetched cleanly from upstream `DietrichGebert/ponytail` and installed into the global skills store.

---

## 3. Complete Skill Inventory & Classification

Every discovered and installed skill was evaluated according to the classification policy:

| Skill Identifier | Source Location | Classification | Evidence & Purpose | Action Taken |
| :--- | :--- | :--- | :--- | :--- |
| `ponytail` | Upstream `DietrichGebert/ponytail` | **KEEP — Ponytail** | Core lazy-senior-dev mode: 7-rung decision ladder, YAGNI, shortest working diff | Installed globally & workspace |
| `ponytail-review` | Upstream `DietrichGebert/ponytail` | **KEEP — Ponytail** | Code review focused on over-engineering, bloat, and missing caller tests | Installed globally & workspace |
| `ponytail-audit` | Upstream `DietrichGebert/ponytail` | **KEEP — Ponytail** | Whole-repo quality audit: dead code, slow paths, simplifications | Installed globally |
| `ponytail-debt` | Upstream `DietrichGebert/ponytail` | **KEEP — Ponytail** | Debt ledger harvesting `shortcut:` comments | Installed globally |
| `ponytail-help` | Upstream `DietrichGebert/ponytail` | **KEEP — Ponytail** | Quick-reference card for levels (lite, full, ultra) and commands | Installed globally |
| `tdd-workflow` | Upstream `affaan-m/ECC` | **KEEP — Core** | Test-driven development workflow: red/green/refactor, 80%+ test coverage | Installed globally & workspace |
| `verification-loop`| Upstream `affaan-m/ECC` | **KEEP — Core** | 6-phase verification: build, typecheck, lint, test, security, diff review | Installed globally & workspace |
| `security-review` | Upstream `affaan-m/ECC` | **KEEP — Core** | Proactive security audit: secrets, OWASP, input validation | Installed globally & workspace |
| `coding-standards`| Upstream `affaan-m/ECC` | **KEEP — Core** | Baseline naming, immutability, readability standards | Installed globally |
| `python-testing` | Upstream `affaan-m/ECC` | **KEEP — Specialist**| Pytest fixtures, mocking, parametrization, and coverage patterns | Installed globally & workspace |
| `automate` | Original `~/.agents/skills` | **KEEP — Specialist**| Creates Codex automations | Preserved & linked globally |
| `autopilot` | Original `~/.agents/skills` | **KEEP — Specialist**| PR merge readiness, conflict resolution | Preserved & linked globally |
| `canvas` | Original `~/.agents/skills` | **KEEP — Specialist**| Codex Canvas UI live React component rendering | Preserved & linked globally |
| `create-hook` | Original `~/.agents/skills` | **KEEP — Core** | Authoring and configuring lifecycle hooks (`hooks.json`) | Preserved & linked globally |
| `create-rule` | Original `~/.agents/skills` | **KEEP — Core** | Authoring rules (`GEMINI.md`, `AGENTS.md`) | Preserved & linked globally |
| `create-skill` | Original `~/.agents/skills` | **KEEP — Core** | Skill generation and metadata configuration | Preserved & linked globally |
| `create-subagent`| Original `~/.agents/skills` | **KEEP — Core** | Custom subagent definition workflow | Preserved & linked globally |
| `deploy-with-vercel`| Original `~/.agents/skills`| **KEEP — Specialist**| Linking and deploying repositories to Vercel | Preserved & linked globally |
| `goal` | Original `~/.agents/skills` | **KEEP — Core** | Long-running goal pursuit and task orchestration | Preserved & linked globally |
| `loop` | Original `~/.agents/skills` | **KEEP — Core** | Session prompt looping on recurring/variable intervals | Preserved & linked globally |
| `migrate-to-skills`| Original `~/.agents/skills`| **KEEP — Core** | Rule/workflow migration to skills | Preserved & linked globally |
| `new-repo` | Original `~/.agents/skills` | **KEEP — Core** | Repository initialization and remote setup | Preserved & linked globally |
| `onboard` | Original `~/.agents/skills` | **KEEP — Core** | Repository onboarding and developer guide generation | Preserved & linked globally |
| `origin` | Original `~/.agents/skills` | **KEEP — Specialist**| Origin CLI tool integration | Preserved & linked globally |
| `rename-chat` | Original `~/.agents/skills` | **KEEP — Core** | Session renaming utility | Preserved & linked globally |
| `review` | Original `~/.agents/skills` | **KEEP — Core** | General code review dispatch | Preserved & linked globally |
| `review-bugbot` | Original `~/.agents/skills` | **KEEP — Core** | Bugbot subagent review invocation | Preserved & linked globally |
| `review-security`| Original `~/.agents/skills`| **KEEP — Core** | Security review subagent invocation | Preserved & linked globally |
| `sdk` | Original `~/.agents/skills` | **KEEP — Specialist**| Agent SDK application and automation builder | Preserved & linked globally |
| `share` | Original `~/.agents/skills` | **KEEP — Specialist**| Project sharing and remote snapshot creation | Preserved & linked globally |
| `shell` | Original `~/.agents/skills` | **KEEP — Core** | Literal command execution adapter | Preserved & linked globally |
| `split-to-prs` | Original `~/.agents/skills` | **KEEP — Core** | Large change decomposition into small PRs | Preserved & linked globally |
| `statusline` | Original `~/.agents/skills` | **KEEP — Specialist**| Custom statusline styling and prompt formatting | Preserved & linked globally |
| `update-cli-config`| Original `~/.agents/skills`| **KEEP — Specialist**| CLI configuration settings modification | Preserved & linked globally |
| `update-cursor-settings`| Original `~/.agents/skills`| **KEEP — Specialist**| Settings.json configuration | Preserved & linked globally |
| `visualize` | Original `~/.agents/skills` | **KEEP — Specialist**| Markdown chart, diagram, and graphic rendering | Preserved & linked globally |
| `a11y-debugging`..`troubleshooting` (6)| Global plugins | **KEEP — Specialist**| Chrome DevTools browser inspection, memory, LCP, cookies | Intact in plugin directory |
| `firebase_*` (13)| Global plugins | **KEEP — Specialist**| Cloud Firestore, Auth, Hosting, App Hosting, Data Connect | Intact in plugin directory |
| `gemini-api-*` (3)| Global plugins | **KEEP — Specialist**| Gemini Live, multimodal, and Omni Flash API dev | Intact in plugin directory |
| `agy-customizations`.. (8)| Builtin skills | **KEEP — Core** | Antigravity guide, plugin navigation, automation | Intact in application builtin |

- **CONSOLIDATE Decisions**: 0 items (each skill addresses a distinct domain).
- **QUARANTINE Decisions**: 0 items (no broken, obsolete, or unsafe duplicates were found; all 26 existing skills had valid frontmatter and contents).

---

## 4. Backup & Rollback Protocol

- **Timestamped Backup Path**: `C:\Users\Hp\.gemini\antigravity\backup_20261020_171945`
- **Total Files Backed Up**: 171 files (including full copies of `~/.agents` and `~/.gemini/config`).
- **Integrity Manifest**: `backup_manifest.csv` with SHA-256 digests for all 171 files.
- **Rollback Steps**:
  1. Remove newly created global skills: `Remove-Item -Recurse -Force "C:\Users\Hp\.gemini\config\skills"`
  2. Remove newly created global agents: `Remove-Item -Recurse -Force "C:\Users\Hp\.gemini\config\agents"`
  3. Remove global rules: `Remove-Item -Force "C:\Users\Hp\.gemini\config\rules\AGENTS.md"`
  4. Remove global manifest: `Remove-Item -Force "C:\Users\Hp\.gemini\config\skills.json"`
  5. In `c:\Users\Hp\Documents\GitHub\settle_ai`, remove untracked additions: `Remove-Item -Recurse -Force ".agents", "AGENTS.md"`
  6. Restore backed-up directories from `C:\Users\Hp\.gemini\antigravity\backup_20261020_171945`.

---

## 5. Components Added, Configured, and Retained

### A. Global Skills Directory (`C:\Users\Hp\.gemini\config\skills/`)
Total 36 skills installed and verified with YAML frontmatter:
- **26 Original Skills**: `automate`, `autopilot`, `canvas`, `create-hook`, `create-rule`, `create-skill`, `create-subagent`, `deploy-with-vercel`, `goal`, `loop`, `migrate-to-skills`, `new-repo`, `onboard`, `origin`, `rename-chat`, `review`, `review-bugbot`, `review-security`, `sdk`, `share`, `shell`, `split-to-prs`, `statusline`, `update-cli-config`, `update-cursor-settings`, `visualize`.
- **5 Ponytail Skills**: `ponytail`, `ponytail-review`, `ponytail-audit`, `ponytail-debt`, `ponytail-help` (Source: `https://github.com/DietrichGebert/ponytail`).
- **5 ECC Minimal Skills**: `tdd-workflow`, `verification-loop`, `security-review`, `python-testing`, `coding-standards` (Source: `https://github.com/affaan-m/ECC`).

### B. Global Manifest (`C:\Users\Hp\.gemini\config\skills.json`)
Explicitly registers the global skills folder with Antigravity:
```json
{
  "entries": [
    {
      "path": "C:\\Users\\Hp\\.gemini\\config\\skills"
    }
  ]
}
```

### C. Custom Subagents (`~/.gemini/config/agents/` and `.agents/agents/`)
Created 4 verified subagents conforming to Antigravity's native schema:
1. `researcher.md`: Read-only investigator (`view_file`, `grep_search`, `find_by_name`, `list_dir`, `run_command`, `search_web`).
2. `code-reviewer.md`: Read-only independent final diff reviewer (`view_file`, `grep_search`, `find_by_name`, `list_dir`, `run_command`).
3. `tdd-guide.md`: TDD implementation worker (`view_file`, `write_to_file`, `replace_file_content`, `grep_search`, `find_by_name`, `list_dir`, `run_command`).
4. `build-error-resolver.md`: Root-cause failure diagnostic worker (`view_file`, `write_to_file`, `replace_file_content`, `grep_search`, `find_by_name`, `list_dir`, `run_command`).

### D. Reconciled Governance Rules (`AGENTS.md`)
Placed in workspace root (`settle_ai\AGENTS.md`), workspace rules (`settle_ai\.agents\rules\software-engineering-harness.md`), and global rules (`C:\Users\Hp\.gemini\config\rules\AGENTS.md`):
- **Hierarchy Reconciliation**: Resolves tension between Ponytail's minimal-diff philosophy and planning requirements:
  - Trivial, localized changes use direct Ponytail minimal-diff (no unnecessary files, shortest working diff, root-cause bug fixing).
  - Multi-file, architectural, ambiguous, or risky changes trigger research-first, milestone planning (`/plan`), subagent delegation, and correctness gates.
- **Subagent Utilization Contract**: Standard non-trivial tasks target 2 workers; large/complex tasks target 2–4 concurrent subagents.
- **Correctness Gates**: TDD red/green cycle, caller inspection prior to shared-function edits, and independent diff review.

---

## 6. MCP, Hooks, and Compatibility Limitations

1. **MCP Configuration**:
   - `C:\Users\Hp\.gemini\config\mcp_config.json` was examined. Active MCP tools (`gemini-api-docs_gemini_search_docs`, `gemini-api-docs_gemini_get_doc`) function properly. No speculative external MCP servers were injected.
2. **Lifecycle Hooks**:
   - Node-based Claude Code hook runtimes cannot be directly run on this machine because Node.js is not installed in the Windows PATH. Antigravity native hooks (`hooks.json`) support PowerShell/command execution if configured. In accordance with the ECC Antigravity Guide, the minimal profile deliberately avoids installing the heavy Claude hook runtime.
3. **Execution Policy**:
   - `C:\Users\Hp\.gemini\config\config.json` was preserved untouched. Security settings remain under user control.

---

## 7. Verification Commands & Truthful Outcomes

| Verification Item | Command Executed | Expected State | Actual Result | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Backup Integrity** | PowerShell hash manifest comparison | 171 files backed up with SHA-256 | 171 files verified in `backup_manifest.csv` | **PASS** |
| **Global Skills Existence** | `Get-ChildItem C:\Users\Hp\.gemini\config\skills` | 36 subdirectories | 36 directories listed | **PASS** |
| **Skill Frontmatter Check** | Regex parse of all 36 `SKILL.md` files | All have `name` and `description` | 36 valid, 0 failed | **PASS** |
| **Ponytail Preservation** | Verification script check for 5 components | All 5 Ponytail skills present | All 5 present & intact | **PASS** |
| **Agent Tool Whitelist** | Frontmatter tool list inspection | Only native Antigravity tools used | All 4 agents use valid tools | **PASS** |
| **Rule Size Constraint** | Byte length check on `AGENTS.md` | Under 24,000 bytes (24 KB limit) | 4,631 bytes (19% of budget) | **PASS** |
| **Skills Manifest Schema** | JSON parse of `skills.json` | Valid JSON with `entries` array | Valid JSON, 1 path entry | **PASS** |
| **Workspace Git Safety** | `git status` & `git diff` in `settle_ai` | 0 modified tracked files | 0 modifications; tree clean | **PASS** |
| **Independent Review** | Read-only reviewer subagent audit | Verify zero missing backup skills | 0 missing skills reported | **PASS** |

---

## 8. Research-First Behavior & Upstream References Checked

1. **Ponytail**:
   - Repository: `https://github.com/DietrichGebert/ponytail` (inspected `skills/`, `AGENTS.md`, and README).
   - Antigravity Adaptation: `https://github.com/rizalrepo/ponytail-antigravity-IDE` (inspected slash command mappings and global skills folder contract).
   - *Decision*: Adopted canonical Ponytail 7-rung decision ladder directly into `AGENTS.md` and installed the full 5-skill Ponytail suite globally.
2. **Everything Claude Code (ECC)**:
   - Repository: `https://github.com/affaan-m/ECC` (inspected `docs/ANTIGRAVITY-GUIDE.md`, `manifests/install-profiles.json`, `manifests/install-modules.json`, `scripts/lib/install/antigravity-agent.js`, and `scripts/lib/install-targets/antigravity-project.js`).
   - *Decision*: Avoided heavy npm installer dependency when Node was missing. Extracted the proven minimal profile components (`tdd-workflow`, `verification-loop`, `security-review`, `python-testing`, `coding-standards`) and subagent definitions adapted with Antigravity tool mappings.
3. **Antigravity Internal Guidelines**:
   - Inspected `C:\Users\Hp\.gemini\antigravity\builtin\skills\agy-customizations\SKILL.md` and `docs/` (`skills.md`, `rules.md`, `plugins.md`, `hooks.md`, `json_configs.md`).
   - *Decision*: Placed global skills in `~/.gemini/config/skills/`, registered via `skills.json`, and respected the 24 KB per-rule file budget.

---

## 9. Subagent Utilization Evidence

- **Subagent 1: Upstream Open-Source Researcher (`research`, conversation `f9d0cdce-a474-4217-ab36-5d9f1b47ccd2`)**:
  - *Task*: Read-only retrieval of Ponytail `SKILL.md`, `AGENTS.md`, ladder modes, and ECC minimal profile manifest definitions.
  - *Result*: Successfully retrieved raw content and identified exact minimal profile modules (`rules-core`, `agents-core`, `commands-core`, `platform-configs`, `workflow-quality`).
- **Subagent 2: Independent Quality Reviewer (`research`, conversation `8f174477-07fb-4deb-a4c2-4d5f7e050695`)**:
  - *Task*: Independent read-only audit of file paths, rule sizes, and backup comparison.
  - *Result*: Confirmed `AGENTS.md` is 4,631 bytes, validated `skills.json`, and confirmed 0 missing skills from the 48 backed-up skills.

---

## 10. Community-Reported Failure Modes Addressed

1. **Subagent Tool Hangs (`docs/subagents`)**:
   - Prevented by strictly using verified Antigravity tool identifiers (`view_file`, `write_to_file`, `replace_file_content`, `grep_search`, `find_by_name`, `list_dir`, `run_command`, `search_web`). No guessed tool names like `Bash` or `Read` were emitted.
2. **Global Rules Ignored / Collisions**:
   - Rules were deployed both globally (`C:\Users\Hp\.gemini\config\rules\AGENTS.md`) and project-locally (`settle_ai\AGENTS.md` and `.agents/rules/`). Antigravity's hierarchical walker loads rules from file location up to repo root.
3. **Agent Looping & Over-Engineering**:
   - Bound retry policy (max 3 failed hypotheses before stopping) and Ponytail 7-rung ladder enforced in `AGENTS.md`.
4. **Context Window Exhaustion**:
   - Kept rules compact (4.6 KB vs 24 KB limit). Heavy procedural guides reside in skills loaded on-demand via progressive disclosure.

---

## 11. Manual User Actions Required

1. **Reload Antigravity IDE Session**:
   - Antigravity loads skills and rules at session initialization. Start a **New Conversation** (or restart the IDE) to ensure the refreshed global skill inventory (`36 global skills`) and `AGENTS.md` rules take effect.
2. **Review Untracked Workspace Files in `settle_ai`**:
   - In `c:\Users\Hp\Documents\GitHub\settle_ai`, run `git status`. You will see `AGENTS.md` and `.agents/`. If you want to share these harness rules and core skills with your repository collaborators, commit them (`git add .agents AGENTS.md; git commit -m "feat: add antigravity engineering harness"`). If not, add them to `.git/info/exclude`.
