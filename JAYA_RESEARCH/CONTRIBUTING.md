# Contributing to JAYA Research

Thank you for your interest in contributing! JAYA Research is an open research tool — we welcome contributions from students, researchers, and developers.

## 🚀 Getting Started

1. **Fork** the repository
2. **Clone** your fork: `git clone https://github.com/YOUR_USERNAME/jaya-research.git`
3. **Create a branch**: `git checkout -b feature/your-feature-name`
4. **Setup environment** (see [README.md](README.md#installation))
5. **Make changes**, commit, and push
6. **Open a Pull Request** against `main`

## 📋 Areas to Contribute

| Area | Description |
|---|---|
| **New Analysis Modules** | Add new academic analysis (e.g., plagiarism check, statistical review) |
| **UI Improvements** | Improve the React dashboard (ThesisPage, ResearchPage, etc.) |
| **PDF Extraction** | Better text extraction for complex layouts (tables, equations) |
| **Language Support** | Multi-language UI/prompts (English, Bahasa Indonesia) |
| **Documentation** | Improve docs, add tutorials, write examples |
| **Tests** | Add unit/integration tests for backend modules |
| **Bug Fixes** | Check the Issues tab for open bugs |

## 🧑‍💻 Code Style

- **Python**: Follow PEP 8, use type hints where possible
- **JavaScript/React**: Functional components, hooks only (no class components)
- **CSS**: Use existing Tailwind design tokens (`notebook-*` classes)
- **Commits**: Use conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`

## 🔒 Privacy Rules for Contributors

> [!CAUTION]
> **NEVER commit personal data.** The following directories are in `.gitignore` and must stay that way:
> - `data/` — vector stores, PDF uploads, JAYA's memory
> - `workspaces/` — per-workspace embeddings
> - `logs/` — runtime logs
> - `.env` — your API keys

If you add a new data directory, **add it to `.gitignore` immediately** and note it in your PR.

## 🐛 Reporting Bugs

Open a GitHub Issue with:
1. Steps to reproduce
2. Expected behavior
3. Actual behavior
4. Your OS + Python version
5. Relevant log output (sanitize any API keys!)

## 💡 Proposing Features

Open a GitHub Discussion or Issue with the `enhancement` label. Describe:
- What problem it solves
- How it fits JAYA Research's goal (academic research assistant)
- Any technical approach you have in mind

## 📝 Pull Request Checklist

- [ ] Code runs without errors
- [ ] No personal data or API keys committed
- [ ] `.gitignore` updated if new data dirs were added
- [ ] README updated if adding a new feature
- [ ] Existing tests still pass

---

*JAYA Research — Built for students, by researchers.*
