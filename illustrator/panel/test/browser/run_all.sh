#!/bin/sh
# usage: PAINT_TMP=<temp dir with world/<place>> sh run_all.sh   (server.js + Edge on :9333 must be running)
cd "$(dirname "$0")"
for s in view brush_params strokes_undo save_discard layout reload; do echo "=== $s"; node scenario_$s.js > "${TMPDIR:-/tmp}/sc_$s.log" 2>&1; echo "pass $(grep -c '^PASS' ${TMPDIR:-/tmp}/sc_$s.log) fail $(grep -c '^FAIL' ${TMPDIR:-/tmp}/sc_$s.log)"; grep '^FAIL' "${TMPDIR:-/tmp}/sc_$s.log"; done
