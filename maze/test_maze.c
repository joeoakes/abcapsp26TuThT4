#include <stdio.h>
#include <string.h>
#include <stdbool.h>

// include your maze file
#include "maze_sdl2_final_send.c"

// simple macros
#define PASS(msg) printf("[PASS] %s\n", msg)
#define FAIL(msg) printf("[FAIL] %s\n", msg)

// ----------------------
// 5.1 + 5.2 in_bounds()
// ----------------------
void test_in_bounds() {
    if (in_bounds(0,0) && in_bounds(MAZE_W-1, MAZE_H-1)) {
        PASS("in_bounds valid coords");
    } else {
        FAIL("in_bounds valid coords");
    }

    if (!in_bounds(-1,0) && !in_bounds(MAZE_W,0)) {
        PASS("in_bounds invalid coords");
    } else {
        FAIL("in_bounds invalid coords");
    }
}

// ----------------------
// 5.6 move_dir_name()
// ----------------------
void test_move_dir_name() {
    if (strcmp(move_dir_name(0,-1),"UP")==0 &&
        strcmp(move_dir_name(0,1),"DOWN")==0 &&
        strcmp(move_dir_name(-1,0),"LEFT")==0 &&
        strcmp(move_dir_name(1,0),"RIGHT")==0) {
        PASS("move_dir_name directions");
    } else {
        FAIL("move_dir_name directions");
    }
}

// ----------------------
// 5.7 + 5.8 manual_move_matches_plan()
// ----------------------
void test_manual_move_matches_plan() {
    strcpy(ai_plan[0], "RIGHT");
    ai_plan_len = 1;
    ai_plan_index = 0;

    if (manual_move_matches_plan(1,0) && ai_plan_index == 1) {
        PASS("manual move matches");
    } else {
        FAIL("manual move matches");
    }

    strcpy(ai_plan[0], "UP");
    ai_plan_index = 0;

    if (!manual_move_matches_plan(1,0) && ai_plan_index == 0) {
        PASS("manual move mismatch");
    } else {
        FAIL("manual move mismatch");
    }
}

// ----------------------
// 5.9 + 5.10 parse_plan_response()
// ----------------------
void test_parse_plan() {
    parse_plan_response("{\"plan\":[\"UP\",\"RIGHT\"]}");

    if (ai_plan_len == 2 &&
        strcmp(ai_plan[0],"UP")==0 &&
        strcmp(ai_plan[1],"RIGHT")==0) {
        PASS("parse valid JSON");
    } else {
        FAIL("parse valid JSON");
    }

    parse_plan_response("not json");

    if (ai_plan_len == 0) {
        PASS("parse invalid JSON");
    } else {
        FAIL("parse invalid JSON");
    }
}

// ----------------------
// 5.11 generate_session_id()
// ----------------------
void test_session_id() {
    char buf[64];
    generate_session_id(buf, sizeof(buf));

    if (strncmp(buf, "team4-", 6) == 0 && strlen(buf) <= 63) {
        PASS("session id format");
    } else {
        FAIL("session id format");
    }
}

// ----------------------
// 5.13 discard_response()
// ----------------------
void test_discard() {
    int result = discard_response(NULL, 5, 10, NULL);

    if (result == 50) {
        PASS("discard_response");
    } else {
        FAIL("discard_response");
    }
}

// ----------------------
// MAIN TEST RUNNER
// ----------------------
int main() {
    printf("Running Maze Tests...\n\n");

    test_in_bounds();
    test_move_dir_name();
    test_manual_move_matches_plan();
    test_parse_plan();
    test_session_id();
    test_discard();

    printf("\nDone.\n");
    return 0;
}