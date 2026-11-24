#!/usr/bin/env bash
# The ONE test command. Exits non-zero on any failure, script error or crash.
set -uo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
fail=0

echo "== static checks =="
$PY tools/check_site.py . || fail=1

if [ -d .git ] && git rev-parse HEAD >/dev/null 2>&1; then
  if git log --all --format='%an %ae %s %b' | grep -qi "mil""ken"; then echo "FAIL: forbidden name in git log"; fail=1; else echo "ok:   git log clean"; fi
fi

echo "== negative self-checks (the checker must catch these) =="
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
neg() { # name, sed-or-append action on copy
  rm -rf "$T/c"; mkdir "$T/c"; cp -r index.html style.css favicon.svg img "$T/c/"
  eval "$2"
  if $PY tools/check_site.py "$T/c" >/dev/null 2>&1; then echo "SELF-CHECK FAILED: '$1' was NOT caught"; fail=1; else echo "ok:   caught '$1'"; fi
}
neg "forbidden name in html" 'echo "<!-- Mil""ken -->" >> "$T/c/index.html"'
neg "text-shadow"            'echo ".a{text-shadow:0 0 8px #a78bfa}" >> "$T/c/style.css"'
neg "coloured box-shadow"    'echo ".a{box-shadow:0 0 20px #7c3aed}" >> "$T/c/style.css"'
neg "large-blur neutral shadow" 'echo ".a{box-shadow:0 4px 40px rgba(0,0,0,.2)}" >> "$T/c/style.css"'
neg "filter blur"            'echo ".a{filter:blur(6px)}" >> "$T/c/style.css"'
neg "missing asset"          'rm "$T/c/img/team.webp"'
neg "missing team name"      'sed -i "s/Eylul Karabulak/X/" "$T/c/index.html"'
neg "heavy page"             'head -c 1600000 /dev/zero > "$T/c/img/big.jpg"'

echo "== screenshots (local, 390 and 1280 px) =="
if command -v chromium >/dev/null; then
  mkdir -p "$T/s"
  for w in 390 1280; do
    chromium --headless=new --no-sandbox --disable-gpu --hide-scrollbars --window-size=$w,1400 --screenshot="$T/s/$w.png" "file://$PWD/index.html" >/dev/null 2>&1
    if [ -s "$T/s/$w.png" ]; then echo "ok:   screenshot $w px ($(stat -c%s "$T/s/$w.png") bytes)"; else echo "FAIL: screenshot $w px"; fail=1; fi
  done
else echo "FAIL: chromium not installed"; fail=1; fi

if [ $fail -ne 0 ]; then echo "TESTS FAILED"; exit 1; fi
echo "ALL TESTS PASSED"
