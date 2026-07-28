#!/usr/bin/env python3
"""Judge for the profile bug-hunt game.

Every guess arrives as a GitHub issue titled `bug-report: round-<N> line-<L>`.
The workflow calls `judge` with the issue details in env vars; this script
decides the verdict, writes the bot's comment, updates game state, and
re-renders README.md. All game logic lives here so it can be unit-tested
without GitHub.

Answers (bug line + explanations) live encrypted in answers.enc so a public
repo doesn't leak them; the Fernet key is the GAME_KEY Actions secret.
"""

import argparse
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

GAME_DIR = Path(__file__).resolve().parent
REPO_DIR = GAME_DIR.parent

TITLE_RE = re.compile(r"bug-report: round-(\d{1,6}) line-(\d{1,3})")
LOGIN_RE = re.compile(r"[A-Za-z0-9-]{1,39}")
POINTS = 10
HISTORY_KEEP = 5

RANKS = [
    (200, "Principal Bug Hunter"),
    (150, "Staff SDET"),
    (100, "Senior SDET"),
    (50, "SDET II"),
    (30, "SDET I"),
    (20, "Tester II"),
    (0, "Junior Tester"),
]


def rank_for(points):
    for floor, title in RANKS:
        if points >= floor:
            return title
    return RANKS[-1][1]


def parse_title(title):
    """Strict parse of an issue title into (round, line), else None."""
    m = TITLE_RE.fullmatch(title.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def valid_login(login):
    return bool(LOGIN_RE.fullmatch(login or ""))


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_answers(key, path=None):
    from cryptography.fernet import Fernet

    path = path or GAME_DIR / "answers.enc"
    blob = Path(path).read_bytes()
    return json.loads(Fernet(key.encode()).decrypt(blob))


# ---------------------------------------------------------------- verdicts

def judge(state, corpus, answers, rnd, line, author, issue_no, owner,
          score_owner=False):
    """Pure verdict + state transition. Returns a dict:
    kind, label, close_reason, comment (markdown), state (the new state).
    Never mutates its inputs."""
    state = json.loads(json.dumps(state))  # deep copy; state files are small
    snippet = corpus[state["snippet"]]
    ans = answers[snippet["id"]]
    n_lines = len(snippet["lines"])

    if not valid_login(author):
        return _verdict("invalid", "invalid", "not planned", state,
                        "Could not attribute this report. Closing.")

    if rnd != state["round"]:
        return _verdict(
            "stale", "invalid", "not planned", state,
            f"This report targets **round {rnd}**, but **round "
            f"{state['round']}** is live — the link you clicked came from a "
            "cached README. Refresh the profile and report again.")

    if line < 1 or line > n_lines:
        return _verdict(
            "invalid", "invalid", "not planned", state,
            f"Line {line} does not exist in this round's snippet "
            f"(1–{n_lines}). Closing.")

    if line == ans["bug"]:
        is_owner = author == owner and not score_owner
        if not is_owner:
            state["scores"][author] = state["scores"].get(author, 0) + POINTS
        guesses_taken = len(state["guesses"]) + 1
        state["history"].insert(
            0, f"Round {state['round']} — solved by **@{author}** after "
               f"{guesses_taken} report{'s' if guesses_taken != 1 else ''}")
        state["history"] = state["history"][:HISTORY_KEEP]
        state["round"] += 1
        state["snippet"] = (state["snippet"] + 1) % len(corpus)
        state["guesses"] = {}
        state["total_solved"] += 1
        comment = (
            f"**Confirmed.** {ans['confirm']}\n\n"
            f"Severity: **{ans['severity']}**. Fix queued for next sprint.\n\n")
        if is_owner:
            comment += ("House rule: the maintainer plays for free — "
                        "no points. ")
        else:
            comment += (f"**+{POINTS} points** — that puts you at "
                        f"**{state['scores'][author]}** "
                        f"({rank_for(state['scores'][author])}). ")
        comment += f"**Round {state['round']} is live** — refresh the profile."
        return _verdict("confirmed", "confirmed", "completed", state, comment)

    key = str(line)
    if key in state["guesses"]:
        return _verdict(
            "duplicate", "duplicate", "not planned", state,
            f"Duplicate of #{state['guesses'][key]}. Closing.")

    state["guesses"][key] = issue_no
    near = ans.get("near", {}).get(key)
    if near:
        comment = f"{near}\n\nClosing as *works-as-designed*."
    else:
        comment = (
            f"**Cannot reproduce.** Line {line} behaves per spec. Closing as "
            "*works-as-designed*. Re-test and file a new report if you still "
            "suspect a defect.")
    return _verdict("wad", "works-as-designed", "not planned", state, comment)


def _verdict(kind, label, close_reason, state, comment):
    return {"kind": kind, "label": label, "close_reason": close_reason,
            "state": state, "comment": comment}


# ---------------------------------------------------------------- rendering

QUOTE = ('Quality is compromised by default as soon as "when?" is a matter '
         'of concern before "why?" is explained or "how?" is planned.')

IDENTITY = """\
QA automation engineer. Most of my work is test automation; lately it's \
tooling for AI coding agents. They turn out to be the same problem — neither \
gives you a deterministic system to assert against.

Python, Go, Rust, TypeScript. [portfolio.meeru.dev](https://portfolio.meeru.dev/)\
"""


def issue_url(repo, rnd, line):
    title = urllib.parse.quote(f"bug-report: round-{rnd} line-{line}")
    return f"https://github.com/{repo}/issues/new?title={title}"


def render_readme(state, corpus, repo):
    snippet = corpus[state["snippet"]]
    rnd = state["round"]
    n_lines = len(snippet["lines"])

    numbered = "\n".join(
        f"{i + 1:>2} | {text}" for i, text in enumerate(snippet["lines"]))

    pills = []
    for i in range(1, n_lines + 1):
        link = f"[L{i}]({issue_url(repo, rnd, i)})"
        pills.append(f"~~{link}~~" if str(i) in state["guesses"] else link)
    pill_row = " · ".join(pills)

    rows = sorted(state["scores"].items(), key=lambda kv: (-kv[1], kv[0]))
    if rows:
        board = "| # | Hunter | Points | Rank |\n|---|---|---|---|\n"
        for pos, (login, pts) in enumerate(rows, 1):
            board += f"| {pos} | @{login} | {pts} | {rank_for(pts)} |\n"
    else:
        board = "*No confirmed reports yet — the board is yours to open.*\n"

    history = ""
    if state["history"]:
        history = "\n".join(f"- {h}" for h in state["history"][:3]) + "\n"

    return f"""\
> {QUOTE}

{IDENTITY}

---

## 🐛 Bug Hunt — Round {rnd}

**{snippet['lang']}** · one line below contains a real defect · \
+{POINTS} points for a confirmed report

```text
{numbered}
```

**File a bug report against the line you suspect:**

{pill_row}

Each link opens a pre-filled GitHub issue — the triage bot judges it, \
comments, and deploys the next round. Struck-out lines were already \
reported and closed *works-as-designed*.

{history}
### 🏆 Bug hunters

{board}
<sub>Powered by GitHub Issues — every guess is a bug report, every verdict \
is a bot comment. Answers are encrypted in the repo, so reading the source \
won't help you. The maintainer plays for free and scores nothing.</sub>
"""


# ---------------------------------------------------------------- CLI

def cmd_judge(args):
    title = os.environ["ISSUE_TITLE"]
    author = os.environ["ISSUE_AUTHOR"]
    issue_no = int(os.environ["ISSUE_NUMBER"])
    repo = args.repo or os.environ["GITHUB_REPOSITORY"]
    owner = repo.split("/")[0]
    score_owner = os.environ.get("SCORE_OWNER", "").lower() == "true"

    state = load_json(GAME_DIR / "state.json")
    corpus = load_json(GAME_DIR / "corpus.json")
    answers = load_answers(os.environ["GAME_KEY"])

    parsed = parse_title(title)
    if parsed is None:
        verdict = _verdict(
            "invalid", "invalid", "not planned", state,
            "Could not parse this bug report. Reports are filed by clicking "
            "the line links in the README — hand-rolled titles are not "
            "triaged.")
    else:
        verdict = judge(state, corpus, answers, parsed[0], parsed[1],
                        author, issue_no, owner, score_owner)

    (GAME_DIR / "comment.md").write_text(verdict["comment"], encoding="utf-8")
    (GAME_DIR / "verdict.env").write_text(
        f"LABEL={verdict['label']}\nCLOSE_REASON={verdict['close_reason']}\n",
        encoding="utf-8")
    with open(GAME_DIR / "state.json", "w", encoding="utf-8") as f:
        json.dump(verdict["state"], f, indent=2)
        f.write("\n")
    (REPO_DIR / "README.md").write_text(
        render_readme(verdict["state"], corpus, repo), encoding="utf-8")
    print(f"verdict: {verdict['kind']}")


def cmd_render(args):
    state = load_json(GAME_DIR / "state.json")
    corpus = load_json(GAME_DIR / "corpus.json")
    repo = args.repo or os.environ["GITHUB_REPOSITORY"]
    (REPO_DIR / "README.md").write_text(
        render_readme(state, corpus, repo), encoding="utf-8")
    print(f"rendered README for {repo}, round {state['round']}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    j = sub.add_parser("judge", help="judge the issue in env vars")
    j.add_argument("--repo", help="owner/name; defaults to GITHUB_REPOSITORY")
    j.set_defaults(fn=cmd_judge)
    r = sub.add_parser("render", help="re-render README from state")
    r.add_argument("--repo", help="owner/name; defaults to GITHUB_REPOSITORY")
    r.set_defaults(fn=cmd_render)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
