# KN_12 — DEVELOPMENT PROTOCOLS
## Kain Nusantara Platform — Workflow & Collaboration Guidelines

**Versi:** 1.0 | **Berlaku sejak:** 2026-05-23

---

## 🔄 DEVELOPMENT WORKFLOW

### Git Branching Strategy

```
main (production-ready)
  │
  ├── develop (integration branch)
  │     │
  │     ├── feature/pos-discount-field
  │     ├── feature/qc-form-checklist
  │     ├── bugfix/order-reservation-expiry
  │     └── hotfix/critical-stock-bug (direct from main)
```

### Branch Naming Convention
```
feature/[feature-name]      # New feature
bugfix/[bug-description]    # Bug fix
hotfix/[critical-issue]     # Production hotfix
refactor/[module-name]      # Code refactoring
docs/[doc-update]           # Documentation only
```

### Commit Message Format
```
[type]: [short description]

[optional body - WHY this change]

[optional footer - issue reference]

Examples:
feat: add discount field to POS cart items
fix: resolve order reservation race condition
refactor: split App.js into smaller components (reduce to <500 lines)
docs: update KN_13 navigation map with new admin settings page
test: add pytest for stock allocation logic
```

---

## 👥 TEAM ROLES & RESPONSIBILITIES

### Agent (AI Developer)
- Read **all** standards docs (KN_00-KN_13) before starting
- Follow 3-Gate system (Pre-Code, During Code, Post-Code)
- Update PRD.md, SESSION_LOG.md, plan.md after each session
- Call testing_agent before marking task complete
- Ask clarification when requirements ambiguous

### Human User (Product Owner)
- Provide clear requirements & priorities
- Review screenshots/demos from agent
- Approve major architectural decisions
- Provide credentials (API keys, etc) when needed
- Give feedback on testing agent reports

### Testing Agent (QA)
- Run comprehensive tests (backend + frontend + E2E)
- Generate test report (`/app/test_reports/iteration_X.json`)
- Prioritize bugs (High/Medium/Low)
- Verify bug fixes in subsequent iterations

---

## 🔑 DECISION-MAKING AUTHORITY

### Agent CAN Decide (Auto-Execute)
- Bug fixes dengan regression test
- Add data-testid attributes
- Add loading/error/empty states
- Performance optimizations
- Code refactoring (within standards)
- Styling improvements (within design system)

### Agent MUST Ask User (Stop & Ask)

#### 🔴 CRITICAL (Always ask)
- Drop atau migrate MongoDB collection
- Delete atau rename API endpoint (breaking change)
- Change authentication/authorization flow
- Add new dependency (pip/yarn package)
- Restructure folder/module (large refactor)
- Add menu/navigation item not in KN_13

#### 🟡 CONFIRMATION (Ask if uncertain)
- Refactor file >500 lines
- Change shared utility/helper function
- Add new portal/section
- Modify MongoDB schema with existing data

---

## 📦 PULL REQUEST (PR) PROCESS

### PR Checklist (Author)
Before creating PR:
- [ ] Code passes all linters (ruff, eslint)
- [ ] All tests pass (`pytest`, `yarn test`)
- [ ] Testing agent called & all bugs fixed
- [ ] Screenshots attached (for UI changes)
- [ ] PRD.md updated (if feature)
- [ ] SESSION_LOG.md updated
- [ ] No console.log or debug print() left
- [ ] data-testid added to new interactive elements

### PR Template
```markdown
## Description
[Brief description of what this PR does]

## Type of Change
- [ ] New feature
- [ ] Bug fix
- [ ] Refactoring
- [ ] Documentation
- [ ] Performance improvement

## Related Documents
- PRD section: [Link to PRD.md section]
- Session log: [Link to SESSION_LOG.md entry]
- Design: [Link to design_guidelines.md if UI change]

## Testing
- [ ] Testing agent report attached (`iteration_X.json`)
- [ ] Manual testing done (describe)
- [ ] Screenshot/video attached (for UI)

## Quality Lens Review (Self-Assessment)
- LENS 1 (Readability): [Pass/Partial/Fail]
- LENS 2 (Architecture): [Pass/Partial/Fail]
- LENS 5 (Performance): [Pass/Partial/Fail]
- LENS 8 (UX): [Pass/Partial/Fail]
- **Overall Grade:** [A-F]

## Checklist
- [ ] Linters pass
- [ ] Tests pass
- [ ] Documentation updated
- [ ] No breaking changes (or documented)
```

### PR Review Checklist (Reviewer)
- [ ] Code readable (LENS 1)
- [ ] Architecture coherent (LENS 2)
- [ ] Performance acceptable (LENS 5)
- [ ] UX complete (loading/error/empty states) (LENS 8)
- [ ] Tests adequate
- [ ] Documentation clear
- [ ] No security issues (LENS 6)

**Review outcome:**
- ✅ **Approve** — Merge ready
- 🛠️ **Request Changes** — Minor fixes needed
- ❌ **Block** — Major issues (fail LENS 3, 5, or 6)

---

## 🎛️ ENVIRONMENT MANAGEMENT

### Environments
```
1. Local Development
   - Backend: http://localhost:8001
   - Frontend: http://localhost:3000
   - MongoDB: localhost:27017

2. Preview (Kubernetes)
   - URL: https://po-pdf-sender.preview.emergentagent.com
   - Auto-deploy from develop branch
   - Seed data available

3. Production (Future)
   - URL: TBD
   - Deploy from main branch
   - Real data
```

### Environment Variables
```bash
# Backend (.env)
MONGO_URL=mongodb://localhost:27017/kn_dev
CORS_ORIGINS=http://localhost:3000
JWT_SECRET_KEY=[from secure vault]

# Frontend (.env)
REACT_APP_BACKEND_URL=http://localhost:8001
```

**⚠️ NEVER commit `.env` files to Git!**

---

## 🚨 INCIDENT RESPONSE

### Severity Levels

#### P0 (Critical) — Production Down
- **Definition:** Core functionality broken, users cannot work
- **Response Time:** Immediate (0-15 minutes)
- **Protocol:**
  1. Create hotfix branch from `main`
  2. Fix issue (minimal change)
  3. Test critical path only
  4. Deploy to production
  5. Post-mortem report (RCA)

#### P1 (High) — Major Feature Broken
- **Definition:** Important feature unavailable, workaround exists
- **Response Time:** <4 hours
- **Protocol:**
  1. Create bugfix branch from `develop`
  2. Fix + comprehensive testing
  3. Merge to develop
  4. Deploy in next release window

#### P2 (Medium) — Minor Bug
- **Definition:** Non-critical issue, UX affected but functional
- **Response Time:** <24 hours
- **Protocol:** Standard bugfix workflow

#### P3 (Low) — Enhancement
- **Definition:** Feature request, nice-to-have
- **Response Time:** Backlog (prioritized)
- **Protocol:** Add to PRD.md backlog

---

## 📝 DOCUMENTATION MAINTENANCE

### Update Triggers

| Document | Update When | Owner |
|---|---|---|
| **PRD.md** | Feature completed, backlog changed | Agent |
| **SESSION_LOG.md** | End of each session | Agent |
| **TECH_DECISIONS.md** | Major architectural decision | Agent + User |
| **KN_13 (Nav Map)** | New menu/page added | Agent |
| **plan.md** | Task status changed, new phase | Agent |
| **CLEANUP_ANALYSIS.md** | After major cleanup | Agent |

### Documentation Review Cycle
- **Weekly:** plan.md, SESSION_LOG.md (current sprint)
- **Sprint End:** PRD.md, TECH_DECISIONS.md
- **Quarterly:** All KN_XX standards docs

---

## ⚙️ TOOLS & AUTOMATION

### Required Tools (Local Dev)
```bash
# Backend
python 3.11+
pip (package manager)
ruff (linter + formatter)
pytest (testing)

# Frontend
Node.js 18+
yarn (package manager, NOT npm)
eslint (linter)

# Database
MongoDB 6.0+
MongoDB Compass (GUI, optional)

# Git
git 2.40+
```

### Pre-commit Hooks (Future)
```bash
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: ruff
        name: Ruff (Python linter)
        entry: ruff check
        language: system
        types: [python]
      
      - id: eslint
        name: ESLint (JS linter)
        entry: yarn lint
        language: system
        types: [javascript, jsx]
      
      - id: no-console-log
        name: Block console.log
        entry: 'console\.log'
        language: pygrep
        types: [javascript, jsx]
```

---

## 📚 KNOWLEDGE SHARING

### Onboarding New Agent/Developer
1. **Day 1:** Read KN_00 (Quick Start)
2. **Day 1:** Read KN_01 (System Overview)
3. **Day 1-2:** Read memory/ENGINEERING_GUARDRAILS.md + FRONTEND_GUARDRAILS.md (kontrak NYATA — menggantikan KN_02–KN_07 aspiratif yang sudah dihapus)
4. **Day 2:** Read PRD.md (current features)
5. **Day 2:** Read plan.md (current work)
6. **Day 3:** Read KN_08 (Design), KN_13 (Nav), KN_14–KN_17 (domain)
7. **Day 3:** Setup local environment
8. **Day 4:** Shadow session (observe agent working)
9. **Day 5:** Pair programming (small bug fix)
10. **Week 2+:** Independent feature work

### Pair Programming Protocol
- **Driver:** Writes code
- **Navigator:** Reviews, suggests, searches docs
- **Switch:** Every 25 minutes (Pomodoro)
- **Focus:** One task at a time
- **Communication:** Think aloud, explain decisions

---

## ✅ SESSION COMPLETION CHECKLIST

Before ending work session:

- [ ] All code committed & pushed
- [ ] PRD.md updated (if feature completed)
- [ ] SESSION_LOG.md entry created
- [ ] plan.md status updated
- [ ] Testing agent called & bugs fixed
- [ ] Screenshots taken (for UI work)
- [ ] Linters clean (no warnings)
- [ ] Services running (supervisorctl status)
- [ ] Next steps documented (in plan.md or SESSION_LOG)

---

**Last Updated:** 23 Mei 2026  
**Maintained by:** Development Team  
**Review Cycle:** Quarterly
