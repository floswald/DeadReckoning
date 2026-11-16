# DeadReckoning — 40-minute talk

Built from [`floswald/quarto-revealjs-clean`](https://github.com/floswald/quarto-revealjs-clean).
One source file, `dead-reckoning.qmd`, rendered twice via Quarto
profiles into two self-contained decks:

| Profile | Output | What the three narrated demos (toy / bus / landuse) do |
|---|---|---|
| `cast` *(default)* | `dead-reckoning-cast.html` | Play pre-recorded asciinema casts, embedded inline — no terminal, no network, no API key needed in the room |
| `live` | `dead-reckoning-live.html` | Cue slide tells you to alt-tab to a real terminal and run the real pipeline live |

Demo 4 (coauthor drift / silent fidelity drift) is always live-only — it
needs no API key, no Docker, no Stata license, so there's nothing to
record and nothing to fail on stage.

Demo 5 (fan-out fidelity — same drift mechanism, six exhibits sharing
one input) is also live-only: no API key, no Docker, but it does need a
local Stata install (same as demo 3) to run the native RUN step.

## Rendering

```bash
cd slides
quarto render dead-reckoning.qmd --profile cast -o dead-reckoning-cast.html
quarto render dead-reckoning.qmd --profile live -o dead-reckoning-live.html --no-clean
```

(`--no-clean` on the second call — otherwise Quarto's website build
wipes `_site/` and deletes the first output.)

## Recording the casts (one-time, before a cast-profile talk)

Needs a real terminal — `asciinema rec` needs a TTY, and act 1 of the
toy demo is an interactive questionnaire meant to be answered live, on
camera, by whoever's presenting. Run from your own shell, not a
sandboxed tool shell:

```bash
! bash record-casts.sh toy       # needs $ANTHROPIC_API_KEY, --skip-docker
! bash record-casts.sh bus       # needs $ANTHROPIC_API_KEY
! bash record-casts.sh landuse   # needs $ANTHROPIC_API_KEY + local Stata
# or all three back to back:
! bash record-casts.sh all
```

This writes `offline-assets/casts/{toy,bus,landuse}.cast` and wraps
each into a `.js` data-URL (via `make-cast-js.py`) so the deck plays
them offline, with no server and no CORS/`file://` issues. Re-render
the `cast` profile afterward to pick them up.

## Picking a strategy for the room

- **HDMI confirmed, comfortable live-coding:** present the `live` deck.
  Demos 1–3 are genuinely live; demos 4 and 5 always are. If a live demo hangs
  (API latency, a flaky typo in the live-typed intake answers), don't
  fight it on stage — open the `cast` deck in a second tab and narrate
  over the recording instead. That's why both decks exist.
- **No HDMI, unreliable wifi, or presenting remotely:** use the `cast`
  deck. Everything plays inline, self-contained, no live dependencies.

## Checklist before a live run

- `$ANTHROPIC_API_KEY` set in the shell you'll present from (demos 1–3)
- Local Stata install (demo 3; demo 1 only if not using `--skip-docker`)
- `$STATA_LICENSE_PATH` + the `stata18_5-mp` base image, only if you
  want the Docker act in demo 1 (otherwise pass `--skip-docker`)
- R + Julia on PATH (demo 4 — usually already true)
- Local Stata install (demo 5, same as demo 3)

## Files

- `dead-reckoning.qmd` — the one source file for both profiles
- `_quarto.yml` — profile group `[cast, live]`, default `cast`
- `record-casts.sh` / `make-cast-js.py` — recording + embedding helpers
- `offline-assets/` — local asciinema player + recorded casts (no CDN)
- `img/` — `picture.png` (the "it doesn't run anymore" screenshot),
  `coauthor_drift_timeline.svg` (the silent-drift timeline)
