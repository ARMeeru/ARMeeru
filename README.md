> AI collapsed "when?" to "now." Quality still hangs on "why?" and "how?"

QA automation engineer. Most of my work is test automation; lately it's tooling for AI coding agents. They turn out to be the same problem: neither gives you a deterministic system to assert against.

Go, Python, TypeScript, Rust.

---

## 🐛 Bug Hunt: Round 1

**Python** · one line below contains a real defect · +10 points for a confirmed report

```text
 1 | def dedupe_keep_newest(events):
 2 |     """Keep only the newest event per id."""
 3 |     if not events:
 4 |         return []
 5 |     seen = {}
 6 |     for e in events:
 7 |         prev = seen.get(e["id"])
 8 |         if prev is None or e["ts"] > prev["ts"]:
 9 |             seen[e["id"]] = e
10 |     ordered = sorted(seen.values(), key=lambda x: x["ts"])
11 |     return ordered[: len(seen) - 1]
```

**File a bug report against the line you suspect:**

[L1](https://github.com/ARMeeru/ARMeeru/issues/new?title=bug-report%3A%20round-1%20line-1) · [L2](https://github.com/ARMeeru/ARMeeru/issues/new?title=bug-report%3A%20round-1%20line-2) · [L3](https://github.com/ARMeeru/ARMeeru/issues/new?title=bug-report%3A%20round-1%20line-3) · [L4](https://github.com/ARMeeru/ARMeeru/issues/new?title=bug-report%3A%20round-1%20line-4) · [L5](https://github.com/ARMeeru/ARMeeru/issues/new?title=bug-report%3A%20round-1%20line-5) · [L6](https://github.com/ARMeeru/ARMeeru/issues/new?title=bug-report%3A%20round-1%20line-6) · [L7](https://github.com/ARMeeru/ARMeeru/issues/new?title=bug-report%3A%20round-1%20line-7) · [L8](https://github.com/ARMeeru/ARMeeru/issues/new?title=bug-report%3A%20round-1%20line-8) · [L9](https://github.com/ARMeeru/ARMeeru/issues/new?title=bug-report%3A%20round-1%20line-9) · [L10](https://github.com/ARMeeru/ARMeeru/issues/new?title=bug-report%3A%20round-1%20line-10) · [L11](https://github.com/ARMeeru/ARMeeru/issues/new?title=bug-report%3A%20round-1%20line-11)

Each link opens a pre-filled GitHub issue. The triage bot judges it, comments, and deploys the next round. Struck-out lines were already reported and closed *works-as-designed*.


### 🏆 Bug hunters

*No confirmed reports yet. The board is yours to open.*

<sub>Powered by GitHub Issues: every guess is a bug report and every verdict is a bot comment. Answers are encrypted in the repo, so reading the source won't help you. The maintainer plays for free and scores nothing.</sub>
