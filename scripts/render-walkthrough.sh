#!/usr/bin/env bash
# Turn the walkthrough clips (make demo-record) into:
#   <dir>/mp4/NN-scene.mp4   one H.264 clip per scene, for editing
#   <dir>/walkthrough.mp4    all scenes in order
#   <dir>/walkthrough.gif    a short README preview (first scenes, sped up)
# Usage: scripts/render-walkthrough.sh walkthrough-output
set -euo pipefail

dir="${1:-walkthrough-output}"
command -v ffmpeg >/dev/null || { echo "ffmpeg is required" >&2; exit 1; }
mkdir -p "$dir/mp4"

list="$dir/mp4/concat.txt"
: > "$list"
for clip in "$dir"/[0-9][0-9]-*.webm; do
  name="$(basename "$clip" .webm)"
  ffmpeg -loglevel error -y -i "$clip" -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p \
    -r 30 -movflags +faststart "$dir/mp4/$name.mp4"
  echo "file '$name.mp4'" >> "$list"
done

ffmpeg -loglevel error -y -f concat -safe 0 -i "$list" -c copy "$dir/walkthrough.mp4"

# README GIF: command center and detection, 2x speed, 960 px, 12 fps, own palette.
first=("$dir"/mp4/01-*.mp4 "$dir"/mp4/02-*.mp4)
preview="$dir/mp4/preview.mp4"
printf "file '%s'\n" "${first[@]##*/}" > "$dir/mp4/preview.txt"
ffmpeg -loglevel error -y -f concat -safe 0 -i "$dir/mp4/preview.txt" -c copy "$preview"
filters="setpts=0.5*PTS,fps=12,scale=960:-1:flags=lanczos"
ffmpeg -loglevel error -y -i "$preview" -vf "$filters,palettegen=stats_mode=diff" "$dir/mp4/palette.png"
ffmpeg -loglevel error -y -i "$preview" -i "$dir/mp4/palette.png" \
  -lavfi "$filters [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=4" "$dir/walkthrough.gif"
rm -f "$preview" "$dir/mp4/preview.txt" "$dir/mp4/palette.png" "$list"

du -h "$dir/walkthrough.mp4" "$dir/walkthrough.gif"
