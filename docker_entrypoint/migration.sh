#!/bin/sh
# Migration script for Ten31 Thoughts
# For the initial version, migrations are no-ops
set -e

if [ "$1" = "from" ]; then
    echo '{"configured": true}'
    exit 0
fi

if [ "$1" = "to" ]; then
    echo '{"configured": true}'
    exit 0
fi

echo "Unknown migration direction: $1" >&2
exit 1
