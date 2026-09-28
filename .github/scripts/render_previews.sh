#!/usr/bin/env bash
# Lädt jede Symbol- und Footprint-Library mit kicad-cli und rendert SVG-Vorschauen.
# Kann KiCad eine Datei nicht laden, schlägt das Skript fehl – das ist der
# eigentliche Format-Check, die SVGs sind ein Nebenprodukt.
#
#   .github/scripts/render_previews.sh [ausgabeordner]     (Standard: previews)
#   KICAD_CLI=/pfad/zu/kicad-cli .github/scripts/render_previews.sh

set -uo pipefail

out=${1:-previews}
root=$(cd "$(dirname "$0")/../.." && pwd)
cli=${KICAD_CLI:-kicad-cli}
failed=0

fail() {
    echo "::error file=$1::$2"
    failed=1
}

"$cli" version

for lib in "$root"/symbols/*.kicad_sym; do
    name=$(basename "$lib" .kicad_sym)
    dest="$out/symbols/$name"
    mkdir -p "$dest"
    if ! log=$("$cli" sym export svg -o "$dest" "$lib" 2>&1); then
        fail "symbols/$name.kicad_sym" "kicad-cli kann die Library nicht laden: $(tail -n 3 <<<"$log" | tr '\n' ' ')"
        continue
    fi
    n=$(find "$dest" -name '*.svg' | wc -l)
    [[ $n -gt 0 ]] || fail "symbols/$name.kicad_sym" "kicad-cli hat keine Vorschau erzeugt"
    echo "symbols/$name: $n SVG"
done

for pretty in "$root"/footprints/*.pretty; do
    name=$(basename "$pretty" .pretty)
    dest="$out/footprints/$name"
    mkdir -p "$dest"
    # Ohne --layers stehen Fab-Text und REF** so groß im Bild, dass man den Footprint nicht erkennt.
    if ! log=$("$cli" fp export svg --layers F.Cu,B.Cu,Edge.Cuts -o "$dest" "$pretty" 2>&1); then
        fail "footprints/$name.pretty" "kicad-cli kann die Library nicht laden: $(tail -n 3 <<<"$log" | tr '\n' ' ')"
        continue
    fi
    # kicad-cli meldet auch dann Erfolg, wenn einzelne SVGs nicht geschrieben
    # werden konnten – deshalb nachzählen.
    want=$(find "$pretty" -maxdepth 1 -name '*.kicad_mod' | wc -l)
    got=$(find "$dest" -name '*.svg' | wc -l)
    [[ $got -eq $want ]] || fail "footprints/$name.pretty" "nur $got von $want Footprints gerendert"
    echo "footprints/$name: $got SVG"
done

exit $failed
