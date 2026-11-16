#!/usr/bin/env bash
# Record the three asciinema casts used by the "cast" profile of the deck.
#
# Run this yourself, interactively, from a real terminal — NOT via a
# sandboxed tool shell (asciinema needs a real TTY, and act 1 of the toy
# demo is a live questionnaire you answer by typing, which is the point).
#
#   cd slides
#   ! bash record-casts.sh toy        # one demo at a time
#   ! bash record-casts.sh bus
#   ! bash record-casts.sh landuse
#   ! bash record-casts.sh all        # all three, back to back
#
# Requirements per demo:
#   toy      - needs $ANTHROPIC_API_KEY (LLM fix-loop act). Run WITHOUT
#              --non-interactive so act 1's "claim R-only" questionnaire is
#              answered live, on camera. Use --skip-docker unless you also
#              have $STATA_LICENSE_PATH + the stata18_5-mp base image built.
#   bus      - needs $ANTHROPIC_API_KEY. No Docker in this segment.
#   landuse  - needs $ANTHROPIC_API_KEY + a local Stata install
#              (native RUN step actually drives Stata).
#
# --idle-time-limit 2 caps any silence (Stata startup, API latency) at 2s
# so a ~5-6 min real run plays back closer to 2-3 min without losing any
# actual output.

set -euo pipefail
cd "$(dirname "$0")/../demo"

OUT="../slides/offline-assets/casts"
mkdir -p "$OUT"

record_toy() {
  echo ">>> Recording toy demo (act 1 is interactive — answer as the author, claim R-only)"
  asciinema rec --idle-time-limit 2 -c "python3 run_demo.py --skip-docker" "$OUT/toy.cast"
}

record_bus() {
  echo ">>> Recording bus_locations demo"
  asciinema rec --idle-time-limit 2 -c "python3 run_demo_bus_locations.py" "$OUT/bus.cast"
}

record_landuse() {
  echo ">>> Recording landuse demo"
  asciinema rec --idle-time-limit 2 -c "python3 run_demo_landuse.py" "$OUT/landuse.cast"
}

case "${1:-}" in
  toy) record_toy ;;
  bus) record_bus ;;
  landuse) record_landuse ;;
  all) record_toy; record_bus; record_landuse ;;
  *) echo "usage: $0 {toy|bus|landuse|all}"; exit 1 ;;
esac

echo
echo ">>> Wrapping recordings into data-URL JS for offline embedding..."
cd ../slides
for name in toy bus landuse; do
  cast="offline-assets/casts/$name.cast"
  if [ -f "$cast" ]; then
    python3 make-cast-js.py "$cast" "CAST_$(echo "$name" | tr '[:lower:]' '[:upper:]')"
  fi
done

echo ">>> Done. Re-render the deck to pick up the new recordings:"
echo "    quarto render dead-reckoning.qmd --profile cast"
