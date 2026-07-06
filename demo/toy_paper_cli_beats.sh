# Plain-CLI walkthrough of demo/toy_paper, in three beats.
# Not meant to be executed as one script — a cheatsheet to type along,
# command by command. Run from the repo root.
#
# All three beats use the same canned intake answers (author claims "R",
# matching README.md) so the R-vs-Stata contradiction shows up in beat 2.
# Each `run` prints a line like:
#   working copy: /var/folders/.../dr_XXXXXXXX/toy_paper
# copy that path in place of $WC below.


# --- setup: canned intake answers, so nobody has to type them live ---

cat > demo/toy_paper_answers.json <<'EOF'
{"restricted_data": "no", "languages_claimed": "R", "data_root": "data", "master_script": ""}
EOF


# --- Beat 1: intake -> DETECT (author claims "R", matching the README) ---

deadreckoning run demo/toy_paper --answers-file demo/toy_paper_answers.json --stop-after detect


# --- Beat 2: pipeline reads the code, catches the lie ---

deadreckoning run demo/toy_paper --answers-file demo/toy_paper_answers.json --stop-after fix

# note the "working copy: ..." path above, then:
WC=/var/folders/.../dr_XXXXXXXX/toy_paper

cat $WC/DATA-EXHIBIT-MAP.md
# -> undeclared region_boost.csv feeds table1.tex

cat $WC/QUESTIONS.md
# -> Q1: "you said this project does not use Stata, but I found .do files"


# --- Beat 3: full run — native run fails, Claude fixes it ---

deadreckoning run demo/toy_paper --answers-file demo/toy_paper_answers.json

# note the new "working copy: ..." path above, then:
WC=/var/folders/.../dr_YYYYYYYY/toy_paper

cat $WC/AGENT_REPORT.md
# -> second FIX-loop block: rewrite_path data/survey_data.csv -> data/survey.csv

cat $WC/tables/table1.tex
# -> regenerated regression table, proof it actually ran
