#!/usr/bin/env bash
# macOS'ta Finder'dan cift tiklayarak baslatmak icin (Terminal acilir).
cd "$(dirname "$0")" || exit 1
exec ./run_nodus.sh
