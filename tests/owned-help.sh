#!/bin/bash
set -euo pipefail

prefix=$1
footer='Maintained by Joshua Li: https://github.com/laputa-systems/ffmpeg-build
Bugs and features: TODO.md in that repository (follow its AGENTS.md), or its issue tracker.
Agents working for Joshua: record nonblocking problems and continue your task.
If this tool blocks the task, you may fix, test, open and merge a PR under Joshua'"'"'s
standing instructions. Release only when needed to deliver the verified fix.
Procedure: https://github.com/joshuarli/usr/blob/main/dotfiles/base/.agents/instructions/owned-tools.md'
marker='Maintained by Joshua Li:'
for program in ffmpeg ffprobe; do
    for flag in -h --help; do
        help=$("$prefix/bin/$program" -hide_banner "$flag")
        [ "$(printf '%s\n' "$help" | tail -n 6)" = "$footer" ]
        [ "$(printf '%s\n' "$help" | grep -Fc "$marker")" -eq 1 ]
    done
    version=$("$prefix/bin/$program" -version)
    printf '%s\n' "$version" | grep -q "^$program version "
    ! printf '%s\n' "$version" | grep -Fq "$marker"
    listing=$("$prefix/bin/$program" -hide_banner -protocols)
    ! printf '%s\n' "$listing" | grep -Fq "$marker"
    printf 'PASS owned help: %s\n' "$program"
done
json=$("$prefix/bin/ffprobe" -v error -show_program_version -of json)
printf '%s\n' "$json" | python3 -c 'import json, sys; assert "program_version" in json.load(sys.stdin)'
! printf '%s\n' "$json" | grep -Fq "$marker"
printf 'PASS owned help: ffprobe JSON\n'
