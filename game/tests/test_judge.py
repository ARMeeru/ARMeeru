"""Unit tests for the bug-hunt judge. No GitHub, no crypto (except the
roundtrip test), no network — pure logic against fixture data."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

GAME_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GAME_DIR))

import judge as J  # noqa: E402

CORPUS = json.loads((GAME_DIR / "corpus.json").read_text())
ANSWERS = json.loads((GAME_DIR / "answers.json").read_text())
OWNER = "ARMeeru"


def fresh_state(**over):
    s = {"round": 1, "snippet": 0, "guesses": {}, "history": [],
         "scores": {}, "total_solved": 0}
    s.update(over)
    return s


def run(state, rnd, line, author="hunter1", issue=101, **kw):
    return J.judge(state, CORPUS, ANSWERS, rnd, line, author, issue,
                   OWNER, **kw)


# ---------------------------------------------------------------- parsing

@pytest.mark.parametrize("title,expected", [
    ("bug-report: round-1 line-4", (1, 4)),
    ("  bug-report: round-47 line-11  ", (47, 11)),
    ("bug-report: round-999999 line-999", (999999, 999)),
])
def test_parse_valid(title, expected):
    assert J.parse_title(title) == expected


@pytest.mark.parametrize("title", [
    "",
    "help me",
    "bug-report:",
    "bug-report: round-1",
    "bug-report: line-4",
    "bug-report: round-x line-4",
    "bug-report: round-1 line-4 <script>alert(1)</script>",
    "bug-report: round-1 line-4; rm -rf /",
    "BUG-REPORT: ROUND-1 LINE-4",
    "bug-report: round-1 line-4 extra",
    "prefix bug-report: round-1 line-4",
    "bug-report: round-1 line--4",
    "bug-report: round-1 line-4.5",
    "bug-report: round-1234567 line-4",
])
def test_parse_rejects_garbage(title):
    assert J.parse_title(title) is None


def test_all_corpus_ids_have_answers_and_valid_bug_lines():
    for sn in CORPUS:
        ans = ANSWERS[sn["id"]]
        assert 1 <= ans["bug"] <= len(sn["lines"]), sn["id"]
        for near_line in ans.get("near", {}):
            n = int(near_line)
            assert 1 <= n <= len(sn["lines"]) and n != ans["bug"], sn["id"]


# ---------------------------------------------------------------- verdicts

def test_correct_guess_confirms_scores_and_rotates():
    v = run(fresh_state(), 1, ANSWERS["py-dedupe"]["bug"])
    assert v["kind"] == "confirmed"
    assert v["close_reason"] == "completed"
    assert v["state"]["scores"]["hunter1"] == 10
    assert v["state"]["round"] == 2
    assert v["state"]["snippet"] == 1
    assert v["state"]["guesses"] == {}
    assert "after 1 report" in v["state"]["history"][0]


def test_wrong_guess_records_and_closes_wad():
    v = run(fresh_state(), 1, 3, issue=55)
    assert v["kind"] == "wad"
    assert v["close_reason"] == "not planned"
    assert v["state"]["guesses"] == {"3": 55}
    assert v["state"]["round"] == 1
    assert "hunter1" not in v["state"]["scores"]


def test_duplicate_guess_references_first_issue():
    s = fresh_state(guesses={"3": 55})
    v = run(s, 1, 3, issue=56)
    assert v["kind"] == "duplicate"
    assert "#55" in v["comment"]
    assert v["state"]["guesses"] == {"3": 55}  # unchanged


def test_near_miss_gets_custom_text():
    # go-fetchall: bug=5, near miss on 4
    s = fresh_state(snippet=1, round=2)
    v = run(s, 2, 4)
    assert v["kind"] == "wad"
    assert "inside" in v["comment"]


def test_stale_round_rejected_without_state_change():
    s = fresh_state(round=3, snippet=2)
    v = run(s, 1, 2)
    assert v["kind"] == "stale"
    assert v["state"]["guesses"] == {}
    assert "round 3" in v["comment"]


@pytest.mark.parametrize("line", [0, -1, 12, 999])
def test_out_of_range_line_rejected(line):
    v = run(fresh_state(), 1, line)  # py-dedupe has 11 lines
    assert v["kind"] == "invalid"
    assert v["state"]["guesses"] == {}


def test_owner_gets_verdict_but_no_points():
    v = run(fresh_state(), 1, ANSWERS["py-dedupe"]["bug"], author=OWNER)
    assert v["kind"] == "confirmed"
    assert v["state"]["scores"] == {}
    assert "plays for free" in v["comment"]
    assert v["state"]["round"] == 2  # round still rotates


def test_owner_scores_when_score_owner_enabled():
    v = run(fresh_state(), 1, ANSWERS["py-dedupe"]["bug"], author=OWNER,
            score_owner=True)
    assert v["state"]["scores"][OWNER] == 10


def test_guess_count_in_history_includes_wrong_guesses():
    s = fresh_state(guesses={"3": 55, "7": 56})
    v = run(s, 1, ANSWERS["py-dedupe"]["bug"])
    assert "after 3 reports" in v["state"]["history"][0]


def test_snippet_rotation_wraps_around():
    s = fresh_state(round=10, snippet=len(CORPUS) - 1)
    bug = ANSWERS[CORPUS[-1]["id"]]["bug"]
    v = run(s, 10, bug)
    assert v["state"]["snippet"] == 0


def test_points_accumulate_across_rounds():
    s = fresh_state(scores={"hunter1": 40})
    v = run(s, 1, ANSWERS["py-dedupe"]["bug"])
    assert v["state"]["scores"]["hunter1"] == 50
    assert "SDET II" in v["comment"]


def test_malicious_login_rejected():
    v = run(fresh_state(), 1, 3, author="evil](http://x.com)")
    assert v["kind"] == "invalid"


def test_judge_never_mutates_input_state():
    s = fresh_state()
    frozen = json.dumps(s, sort_keys=True)
    run(s, 1, ANSWERS["py-dedupe"]["bug"])
    assert json.dumps(s, sort_keys=True) == frozen


# ---------------------------------------------------------------- ranks

@pytest.mark.parametrize("pts,rank", [
    (0, "Junior Tester"), (10, "Junior Tester"), (20, "Tester II"),
    (30, "SDET I"), (50, "SDET II"), (100, "Senior SDET"),
    (150, "Staff SDET"), (200, "Principal Bug Hunter"),
    (999, "Principal Bug Hunter"),
])
def test_rank_thresholds(pts, rank):
    assert J.rank_for(pts) == rank


# ---------------------------------------------------------------- render

def test_render_contains_link_per_line_with_encoded_title():
    s = fresh_state()
    md = J.render_readme(s, CORPUS, "ARMeeru/ARMeeru")
    n = len(CORPUS[0]["lines"])
    for i in range(1, n + 1):
        assert (f"issues/new?title=bug-report%3A%20round-1%20line-{i})"
                in md), i
    assert f"line-{n + 1})" not in md


def test_render_strikes_wrong_guesses():
    s = fresh_state(guesses={"3": 55})
    md = J.render_readme(s, CORPUS, "ARMeeru/ARMeeru")
    assert "~~[L3](" in md
    assert "~~[L4](" not in md


def test_render_is_deterministic():
    s = fresh_state(scores={"b": 10, "a": 10}, history=["Round 0 — x"])
    a = J.render_readme(s, CORPUS, "ARMeeru/ARMeeru")
    b = J.render_readme(json.loads(json.dumps(s)), CORPUS, "ARMeeru/ARMeeru")
    assert a == b


def test_render_leaderboard_sorted_desc_then_alpha():
    s = fresh_state(scores={"zed": 10, "abe": 30, "moe": 30})
    md = J.render_readme(s, CORPUS, "ARMeeru/ARMeeru")
    assert md.index("@abe") < md.index("@moe") < md.index("@zed")


def test_render_empty_board_message():
    md = J.render_readme(fresh_state(), CORPUS, "ARMeeru/ARMeeru")
    assert "board is yours" in md


def test_render_numbered_lines_match_corpus():
    md = J.render_readme(fresh_state(), CORPUS, "ARMeeru/ARMeeru")
    assert " 1 | def dedupe_keep_newest(events):" in md
    assert "11 | " in md


# ---------------------------------------------------------------- verdict.env

def test_verdict_env_is_shell_sourceable(tmp_path):
    """CLOSE_REASON contains a space ("not planned") — the file must survive
    a bash `source`, not just look like env syntax."""
    v = run(fresh_state(), 1, 3)  # wad -> close_reason "not planned"
    env_file = tmp_path / "verdict.env"
    J.write_verdict_env(v, env_file)
    out = subprocess.run(
        ["bash", "-euc", f'source "{env_file}" && printf "%s|%s" "$LABEL" "$CLOSE_REASON"'],
        capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout == "works-as-designed|not planned"


# ---------------------------------------------------------------- crypto

def test_answers_encrypt_decrypt_roundtrip(tmp_path):
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    enc = tmp_path / "answers.enc"
    raw = (GAME_DIR / "answers.json").read_bytes()
    enc.write_bytes(Fernet(key.encode()).encrypt(raw))
    loaded = J.load_answers(key, enc)
    assert loaded == ANSWERS
