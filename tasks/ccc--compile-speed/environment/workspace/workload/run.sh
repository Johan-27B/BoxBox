#!/bin/sh
set -eu

cd "$(dirname "$0")"
exec ../ccc/target/release/ccc -c sqlite3.c -o /tmp/sqlite3.o
