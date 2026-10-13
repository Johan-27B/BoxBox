/* PerfRace driver for the visible SQLite amalgamation.
 *
 * Links sqlite3.o into an application and executes SQL against an in-memory
 * database. The verifier compares a checksum computed by SQLite's SUM
 * aggregate over a deterministic table.
 *
 * This file is part of the PerfRace task and not derived from SQLite.
 */

#include <stdio.h>
#include <stdlib.h>
#include "sqlite3.h"

static int die(const char *msg, sqlite3 *db) {
    fprintf(stderr, "%s: %s\n", msg, db ? sqlite3_errmsg(db) : "(no db)");
    if (db) sqlite3_close(db);
    return 1;
}

int main(void) {
    sqlite3 *db = NULL;
    if (sqlite3_open(":memory:", &db) != SQLITE_OK)
        return die("sqlite3_open", db);

    /* Deterministic data: 9 base rows, expanded to 18 by *10, then to 36
     * by *100. The SUM is what the verifier checks; if any part of the
     * amalgamation is mis-compiled (parser, optimizer, vdbe, etc.), the
     * result will not match the precomputed expected value.
     */
    const char *setup =
        "CREATE TABLE t(x INTEGER);"
        "INSERT INTO t VALUES (1),(2),(3),(4),(5),(6),(7),(8),(9);"
        "INSERT INTO t SELECT x*10 FROM t;"
        "INSERT INTO t SELECT x*100 FROM t;";
    if (sqlite3_exec(db, setup, NULL, NULL, NULL) != SQLITE_OK)
        return die("sqlite3_exec(setup)", db);

    sqlite3_stmt *stmt = NULL;
    if (sqlite3_prepare_v2(db, "SELECT SUM(x) FROM t;", -1, &stmt, NULL) != SQLITE_OK)
        return die("sqlite3_prepare_v2", db);

    if (sqlite3_step(stmt) != SQLITE_ROW)
        return die("sqlite3_step", db);

    sqlite3_int64 sum = sqlite3_column_int64(stmt, 0);
    printf("Checksum: %lld\n", (long long)sum);

    sqlite3_finalize(stmt);
    sqlite3_close(db);
    return 0;
}
