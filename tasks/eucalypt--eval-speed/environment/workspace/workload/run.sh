#!/bin/sh
set -eu

cd "$(dirname "$0")"
exec ../eucalypt/target/release/eu day06.eu -t part-2
