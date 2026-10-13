#!/bin/bash
set -uo pipefail

PASS=true

run_exact() {
    local executable="$1"
    local expected="$2"
    local name="$3"
    local actual="/tmp/${name}.stdout"

    if ! timeout 30 "$executable" >"$actual" 2>"/tmp/${name}.stderr"; then
        echo "FAIL: $name execution failed"
        PASS=false
        return
    fi

    if ! cmp -s "$actual" "$expected"; then
        echo "FAIL: $name stdout differs from expected output"
        PASS=false
        return
    fi

    echo "PASS: $name"
}

check_standalone() {
    local source="$1"
    local expected="$2"
    local name="$3"
    local executable="/tmp/${name}"

    if ! timeout 120 "$CCC" "$source" -o "$executable" \
        >"/tmp/${name}.compile.stdout" 2>"/tmp/${name}.compile.stderr"; then
        echo "FAIL: $name compilation failed"
        PASS=false
        return
    fi

    run_exact "$executable" "$expected" "$name"
}

check_sqlite() {
    local object="/tmp/sqlite3.o"
    local executable="/tmp/sqlite-driver"

    if ! timeout 180 "$CCC" -c "$TESTS_DIR/workload/sqlite3.c" -o "$object" \
        >/tmp/sqlite.compile.stdout 2>/tmp/sqlite.compile.stderr; then
        echo "FAIL: SQLite compilation failed"
        PASS=false
        return
    fi

    if ! timeout 120 "$CCC" -I "$TESTS_DIR/workload" \
        "$TESTS_DIR/heldout/sqlite_driver.c" "$object" \
        -o "$executable" >/tmp/sqlite.link.stdout 2>/tmp/sqlite.link.stderr; then
        echo "FAIL: SQLite driver link failed"
        PASS=false
        return
    fi

    run_exact "$executable" "$TESTS_DIR/expected/sqlite.txt" "sqlite"
}

check_sqlite
check_standalone \
    "$TESTS_DIR/heldout/hidden_function_mix.c" \
    "$TESTS_DIR/expected/hidden_function_mix.txt" \
    "hidden-function-mix"
check_standalone \
    "$TESTS_DIR/heldout/hidden_struct_heavy.c" \
    "$TESTS_DIR/expected/hidden_struct_heavy.txt" \
    "hidden-struct-heavy"
check_standalone \
    "$TESTS_DIR/heldout/hidden_control_flow.c" \
    "$TESTS_DIR/expected/hidden_control_flow.txt" \
    "hidden-control-flow"

if [ "$PASS" != true ]; then
    echo "CORRECTNESS FAILED"
    exit 1
fi

echo "All correctness checks passed"
