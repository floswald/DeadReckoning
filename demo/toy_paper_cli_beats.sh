#!/usr/bin/env bash
# Plain-CLI walkthrough of demo/toy_paper in three beats — no driver script,
# just `deadreckoning run` invocations, meant to be typed/recorded live
# (e.g. with asciinema) one beat at a time.
#
# Usage:
#   demo/toy_paper_cli_beats.sh 1   # intake questionnaire (interactive TTY)
#   demo/toy_paper_cli_beats.sh 2   # GRAPH..FIX — pipeline catches the lie
#   demo/toy_paper_cli_beats.sh 3   # full run — native fail, Claude fixes it
#
# Beat 1 is interactive: answer "no" (restricted data) and "R" (languages)
# to match the README's claim. Beats 2-3 replay those same answers via
# --answers-file so the contradiction actually surfaces (there's no way to
# carry Beat 1's live answers forward otherwise — each beat is a fresh
# working copy).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="$REPO_ROOT/demo/toy_paper"
ANSWERS="$REPO_ROOT/demo/toy_paper_answers.json"

cat > "$ANSWERS" <<'EOF'
{"restricted_data": "no", "languages_claimed": "R", "data_root": "data", "master_script": ""}
EOF

beat1() {
    echo "--- Beat 1: intake questionnaire (answer live: restricted=no, languages=R) ---"
    deadreckoning run "$PROJECT" --stop-after detect
}

beat2() {
    echo "--- Beat 2: pipeline reads the code, catches the lie ---"
    LOG=$(mktemp)
    deadreckoning run "$PROJECT" --answers-file "$ANSWERS" --stop-after fix | tee "$LOG"
    WC=$(grep "working copy:" "$LOG" | awk '{print $NF}')

    echo
    echo "--- DATA-EXHIBIT-MAP.md (undeclared region_boost.csv feeds table1.tex) ---"
    cat "$WC/DATA-EXHIBIT-MAP.md"

    echo
    echo "--- QUESTIONS.md (Q1: 'you said no Stata, but I found .do files') ---"
    cat "$WC/QUESTIONS.md"
}

beat3() {
    echo "--- Beat 3: full run — native run fails, Claude fixes it live ---"
    LOG=$(mktemp)
    deadreckoning run "$PROJECT" --answers-file "$ANSWERS" | tee "$LOG"
    WC=$(grep "working copy:" "$LOG" | awk '{print $NF}')

    echo
    echo "--- AGENT_REPORT.md (second FIX-loop block: Claude's rewrite_path fix) ---"
    cat "$WC/AGENT_REPORT.md"

    echo
    echo "--- tables/table1.tex (regenerated regression output) ---"
    cat "$WC/tables/table1.tex"
}

case "${1:-}" in
    1) beat1 ;;
    2) beat2 ;;
    3) beat3 ;;
    *) echo "usage: $0 {1|2|3}" >&2; exit 1 ;;
esac
