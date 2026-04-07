#define _GNU_SOURCE
// maze_sdl2_final_send.c
// SDL2 maze game with JSON event reporting via HTTPS (mTLS)
//
// Build (run from maze/):
/*   
gcc -O2 -Wall -Wextra -std=c11 maze_sdl2_final_send.c -o maze_sdl2_final_send \
       $(pkg-config --cflags --libs sdl2) -lcurl -lcjson -lhiredis -lpthread
*/
// Requires: infra/security/certs/client.crt, infra/security/certs/client.key, infra/security/certs/ca.crt (mTLS)
// Run from project root or src/robot/maze directory.
//
// SDL2 maze game with JSON event reporting via HTTPS
// Uses cJSON for JSON creation and libcurl for HTTPS POST requests
// Writes mission data to Redis and launches mission dashboard on L key
//
// MODIFICATIONS ADDED:
// - JSON telemetry now sent to:
//   * Logging Server (10.170.8.130:8446)
//   * MiniPupper (10.170.8.123:8446)
// - Redis mission data sent ONLY to:
//   * AI Server (10.170.8.109:8446)
// - Confirmation or error printed for each server on every input
// - Maze logic remains completely unchanged
//
// FIXES APPLIED:
// - [FIX 1] HTTPS requests now fire in detached background threads (pthread)
//           so the SDL event loop is never blocked. Previously each move
//           froze the game waiting for server responses.
// - [FIX 2] Added startup connectivity probe so connection status is printed
//           before the player presses any key.
// - [FIX 3] Added fflush(stdout) so output appears immediately in WSL
//           terminals that buffer stdout.
// - [FIX 4] Added SDL_Init, SDL_CreateWindow, and SDL_CreateRenderer error
//           checks so the program exits cleanly instead of crashing silently.
// - [FIX 5] Server response body suppressed from stdout via CURLOPT_WRITEFUNCTION
//           for clean, aligned status output.

#include <SDL2/SDL.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <string.h>
#include <unistd.h>
#include <sys/wait.h>
#include <netdb.h>
#include <pthread.h>

#include <curl/curl.h>
#include <cjson/cJSON.h>
#include <hiredis/hiredis.h>

#define MAZE_W 21
#define MAZE_H 15
#define CELL   32
#define PAD    16

/* HTTPS endpoints */
#define LOGGING_ENDPOINT    "https://10.170.8.130:8446/telemetry"
#define AI_ENDPOINT         "https://10.170.8.109:8446/mission"
#define AI_MAZE_ENDPOINT    "https://10.170.8.109:8447/maze"
#define AI_MISSION_WEB_API  "https://10.170.8.109:8447/mission"
#define MINIPUPPER_ENDPOINT "https://10.170.8.123:8446/telemetry"
enum { WALL_N = 1, WALL_E = 2, WALL_S = 4, WALL_W = 8 };

typedef struct {
    uint8_t walls;
    bool    visited;
} Cell;

static Cell g[MAZE_H][MAZE_W];

static char session_id[64];
static int  move_sequence = 0;

/* Mission tracking for Redis */
static int    moves_left_turn  = 0;
static int    moves_right_turn = 0;
static int    moves_straight   = 0;
static int    moves_reverse    = 0;
static time_t mission_start_time;
static redisContext *redis_ctx = NULL;
static bool mission_won = false;

/* AI auto-play state */
#define MAX_PLAN_MOVES 1024
#define AUTOPLAY_DELAY_MS 150
static char   ai_plan[MAX_PLAN_MOVES][8];
static int    ai_plan_len   = 0;
static int    ai_plan_index = 0;
static bool   ai_autoplay   = false;
static Uint32 ai_last_tick  = 0;

/* -------------------------------------------------------
   HTTPS helper — fire-and-forget via background thread
   [FIX 1] Each POST runs in a detached pthread so the SDL
   event loop is never blocked, even if a server is down.
   [FIX 5] Response body is discarded to keep output clean.
------------------------------------------------------- */

typedef struct {
    char  url[256];
    char *json;
    char  label[32];
    const char *client_cert;
    const char *client_key;
    const char *ca_file;
} PostTask;

/* mTLS: client cert paths (override via env: MTLS_CLIENT_CERT, MTLS_CLIENT_KEY, MTLS_CA_FILE) */
static const char *mtls_client_cert;
static const char *mtls_client_key;
static const char *mtls_ca_file;

/* Discard server response body so it doesn't print to stdout */
static size_t discard_response(void *ptr, size_t size, size_t nmemb, void *ud) {
    (void)ptr; (void)ud;
    return size * nmemb;
}

static void *post_thread(void *arg) {
    PostTask *task = (PostTask *)arg;

    CURL *curl = curl_easy_init();
    if (curl) {
        struct curl_slist *headers = NULL;
        headers = curl_slist_append(headers, "Content-Type: application/json");

        curl_easy_setopt(curl, CURLOPT_URL,            task->url);
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER,     headers);
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS,     task->json);
        /* mTLS: client presents cert, verify server against CA (professor's approach) */
        curl_easy_setopt(curl, CURLOPT_SSLCERT,        task->client_cert);
        curl_easy_setopt(curl, CURLOPT_SSLCERTTYPE,    "PEM");
        curl_easy_setopt(curl, CURLOPT_SSLKEY,         task->client_key);
        curl_easy_setopt(curl, CURLOPT_SSLKEYTYPE,     "PEM");
        curl_easy_setopt(curl, CURLOPT_CAINFO,         task->ca_file);
        curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);
        curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 2L);
        curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 3L);
        curl_easy_setopt(curl, CURLOPT_TIMEOUT,        5L);
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION,  discard_response);

        CURLcode res = curl_easy_perform(curl);

        if (res == CURLE_OK)
            printf("-> %-18s [OK]\n", task->label);
        else
            printf("-> %-18s [FAIL] %s\n", task->label, curl_easy_strerror(res));
        fflush(stdout); /* FIX 3 */

        curl_slist_free_all(headers);
        curl_easy_cleanup(curl);
    }

    free(task->json);
    free(task);
    return NULL;
}

static void https_post_async(const char *url, const char *json, const char *label) {
    PostTask *task = malloc(sizeof(PostTask));
    if (!task) return;
    snprintf(task->url,   sizeof(task->url),   "%s", url);
    task->json = strdup(json);
    snprintf(task->label, sizeof(task->label), "%s", label);
    task->client_cert = mtls_client_cert;
    task->client_key  = mtls_client_key;
    task->ca_file     = mtls_ca_file;

    pthread_t tid;
    pthread_create(&tid, NULL, post_thread, task);
    pthread_detach(tid);
}

/* -------------------------------------------------------
   JSON telemetry → Logging + MiniPupper (non-blocking)
------------------------------------------------------- */
static void send_json_telemetry(
    const char *event_type,
    int px, int py,
    bool goal_reached
) {
    cJSON *root = cJSON_CreateObject();

    char timestamp[32];
    time_t now = time(NULL);
    strftime(timestamp, sizeof(timestamp), "%Y-%m-%dT%H:%M:%SZ", gmtime(&now));

    cJSON_AddStringToObject(root, "session_id",    session_id);
    cJSON_AddStringToObject(root, "event_type",    event_type);
    cJSON_AddBoolToObject  (root, "goal_reached",  goal_reached);
    cJSON_AddStringToObject(root, "timestamp",     timestamp);
    cJSON_AddNumberToObject(root, "move_sequence", move_sequence);
    cJSON_AddNumberToObject(root, "x",             px);
    cJSON_AddNumberToObject(root, "y",             py);

    char *json_str = cJSON_PrintUnformatted(root);
    printf("\n--- JSON Payload ---\n%s\n", json_str);

    https_post_async(LOGGING_ENDPOINT,    json_str, "Logging server");
    https_post_async(MINIPUPPER_ENDPOINT, json_str, "MiniPupper");

    free(json_str);
    cJSON_Delete(root);
}

/* -------------------------------------------------------
   Send mission data to AI server (non-blocking)
------------------------------------------------------- */
static void send_mission_to_ai_server(void) {
    cJSON *root = cJSON_CreateObject();

    cJSON_AddStringToObject(root, "session_id",      session_id);
    cJSON_AddNumberToObject(root, "moves_left_turn",  moves_left_turn);
    cJSON_AddNumberToObject(root, "moves_right_turn", moves_right_turn);
    cJSON_AddNumberToObject(root, "moves_straight",   moves_straight);
    cJSON_AddNumberToObject(root, "moves_reverse",    moves_reverse);
    cJSON_AddBoolToObject  (root, "mission_won",      mission_won);

    char *json_str = cJSON_PrintUnformatted(root);

    https_post_async(AI_ENDPOINT, json_str, "AI server");

    free(json_str);
    cJSON_Delete(root);
}

/* -------------------------------------------------------
   Send full maze grid to AI solver (SYNCHRONOUS).
   Captures the JSON response, parses the plan array,
   and stores it in ai_plan[] for auto-play.
   Increases timeout to 60s since the LLM may be slow.
------------------------------------------------------- */

struct response_buf { char *data; size_t size; };

static size_t capture_response(void *ptr, size_t size, size_t nmemb, void *ud) {
    struct response_buf *buf = (struct response_buf *)ud;
    size_t total = size * nmemb;
    buf->data = realloc(buf->data, buf->size + total + 1);
    memcpy(buf->data + buf->size, ptr, total);
    buf->size += total;
    buf->data[buf->size] = '\0';
    return total;
}

/* Local Redis (GameHat) + POST /mission/{id}/summary on maze server (web dashboard). */
static void post_mission_summary_to_web(
    const char *result_label, const char *abort_reason,
    const char *start_buf, const char *end_buf,
    int total, const char *dist_buf, int duration)
{
    cJSON *root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "robot_id", "keyboard-player");
    cJSON_AddStringToObject(root, "mission_type", "explore");
    cJSON_AddStringToObject(root, "start_time", start_buf);
    cJSON_AddStringToObject(root, "end_time", end_buf);
    cJSON_AddNumberToObject(root, "moves_left_turn", moves_left_turn);
    cJSON_AddNumberToObject(root, "moves_right_turn", moves_right_turn);
    cJSON_AddNumberToObject(root, "moves_straight", moves_straight);
    cJSON_AddNumberToObject(root, "moves_reverse", moves_reverse);
    cJSON_AddNumberToObject(root, "moves_total", total);
    cJSON_AddStringToObject(root, "distance_traveled", dist_buf);
    cJSON_AddNumberToObject(root, "duration_seconds", duration);
    cJSON_AddStringToObject(root, "mission_result", result_label);
    cJSON_AddStringToObject(root, "abort_reason", abort_reason ? abort_reason : "");

    char *json_str = cJSON_PrintUnformatted(root);
    char url[384];
    snprintf(url, sizeof(url), "%s/%s/summary", AI_MISSION_WEB_API, session_id);

    printf("--- Sync mission summary to web API ---\n");
    fflush(stdout);

    CURL *curl = curl_easy_init();
    if (curl) {
        struct curl_slist *headers = NULL;
        headers = curl_slist_append(headers, "Content-Type: application/json");
        curl_easy_setopt(curl, CURLOPT_URL, url);
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, json_str);
        curl_easy_setopt(curl, CURLOPT_SSLCERT, mtls_client_cert);
        curl_easy_setopt(curl, CURLOPT_SSLCERTTYPE, "PEM");
        curl_easy_setopt(curl, CURLOPT_SSLKEY, mtls_client_key);
        curl_easy_setopt(curl, CURLOPT_SSLKEYTYPE, "PEM");
        curl_easy_setopt(curl, CURLOPT_CAINFO, mtls_ca_file);
        curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);
        curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 2L);
        curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 5L);
        curl_easy_setopt(curl, CURLOPT_TIMEOUT, 15L);
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, discard_response);

        CURLcode res = curl_easy_perform(curl);
        if (res == CURLE_OK)
            printf("-> Mission web sync   [OK]\n");
        else
            printf("-> Mission web sync   [FAIL] %s\n", curl_easy_strerror(res));
        fflush(stdout);
        curl_slist_free_all(headers);
        curl_easy_cleanup(curl);
    }

    free(json_str);
    cJSON_Delete(root);
}

static void flush_mission_summary(bool goal_reached, const char *abort_reason) {
    const char *ar = (abort_reason && abort_reason[0]) ? abort_reason : "";
    const char *result_label;
    if (goal_reached)
        result_label = "Success";
    else if (ar[0])
        result_label = "Aborted";
    else
        result_label = "In Progress";

    time_t now     = time(NULL);
    int    duration = (int)(now - mission_start_time);
    int    total = moves_left_turn + moves_right_turn + moves_straight + moves_reverse;

    char start_buf[32], end_buf[32];
    snprintf(start_buf, sizeof(start_buf), "%ld", (long)mission_start_time);
    snprintf(end_buf, sizeof(end_buf), "%ld", (long)now);

    char dist_buf[32];
    snprintf(dist_buf, sizeof(dist_buf), "%.2f", (double)total * 0.39);

    if (redis_ctx) {
        char key[256];
        snprintf(key, sizeof(key), "mission:%s:summary", session_id);
        redisCommand(redis_ctx,
            "HSET %s robot_id %s mission_type %s start_time %s end_time %s "
            "moves_left_turn %d moves_right_turn %d moves_straight %d moves_reverse %d "
            "moves_total %d distance_traveled %s duration_seconds %d "
            "mission_result %s abort_reason %s",
            key,
            "keyboard-player", "explore",
            start_buf, end_buf,
            moves_left_turn, moves_right_turn, moves_straight, moves_reverse,
            total, dist_buf, duration,
            result_label, ar);
    }

    post_mission_summary_to_web(result_label, ar, start_buf, end_buf, total, dist_buf, duration);
}

static void launch_mission_dashboard(void) {
    printf("\n--- Launching Mission Dashboard ---\n");
    flush_mission_summary(mission_won, "");

    pid_t pid = fork();
    if (pid == 0) {
        execl("./missions/mission_dashboard", "mission_dashboard", session_id, NULL);
        perror("execl failed");
        _exit(1);
    } else if (pid > 0) {
        int status;
        waitpid(pid, &status, 0);
        printf("--- Mission Dashboard closed ---\n");
    }
}

/** Window close / Esc: snapshot mission for web dashboard. */
static void flush_mission_on_game_exit(void) {
    if (move_sequence == 0 && !mission_won)
        return;
    if (mission_won)
        flush_mission_summary(true, "");
    else
        flush_mission_summary(false, "user exited");
}

static void parse_plan_response(const char *json_body) {
    ai_plan_len   = 0;
    ai_plan_index = 0;

    cJSON *root = cJSON_Parse(json_body);
    if (!root) return;

    cJSON *plan = cJSON_GetObjectItem(root, "plan");
    if (!cJSON_IsArray(plan)) { cJSON_Delete(root); return; }

    int n = cJSON_GetArraySize(plan);
    if (n > MAX_PLAN_MOVES) n = MAX_PLAN_MOVES;

    for (int i = 0; i < n; i++) {
        cJSON *item = cJSON_GetArrayItem(plan, i);
        if (cJSON_IsString(item) && item->valuestring)
            snprintf(ai_plan[i], sizeof(ai_plan[i]), "%s", item->valuestring);
    }
    ai_plan_len = n;
    cJSON_Delete(root);

    printf("AI plan received: %d moves\n", ai_plan_len);
    fflush(stdout);
}

static void send_maze_grid(void) {
    cJSON *root = cJSON_CreateObject();

    cJSON_AddStringToObject(root, "session_id", session_id);
    cJSON_AddNumberToObject(root, "width",      MAZE_W);
    cJSON_AddNumberToObject(root, "height",     MAZE_H);
    cJSON_AddNumberToObject(root, "start_x",    0);
    cJSON_AddNumberToObject(root, "start_y",    0);
    cJSON_AddNumberToObject(root, "goal_x",     MAZE_W - 1);
    cJSON_AddNumberToObject(root, "goal_y",     MAZE_H - 1);

    cJSON *arr = cJSON_CreateArray();
    for (int y = 0; y < MAZE_H; y++)
        for (int x = 0; x < MAZE_W; x++)
            cJSON_AddItemToArray(arr, cJSON_CreateNumber(g[y][x].walls));
    cJSON_AddItemToObject(root, "cells", arr);

    char *json_str = cJSON_PrintUnformatted(root);

    printf("\n--- Sending maze grid to AI solver ---\n");
    fflush(stdout);

    struct response_buf resp = { .data = NULL, .size = 0 };

    CURL *curl = curl_easy_init();
    if (curl) {
        struct curl_slist *headers = NULL;
        headers = curl_slist_append(headers, "Content-Type: application/json");

        curl_easy_setopt(curl, CURLOPT_URL,            AI_MAZE_ENDPOINT);
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER,     headers);
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS,     json_str);
        curl_easy_setopt(curl, CURLOPT_SSLCERT,        mtls_client_cert);
        curl_easy_setopt(curl, CURLOPT_SSLCERTTYPE,    "PEM");
        curl_easy_setopt(curl, CURLOPT_SSLKEY,         mtls_client_key);
        curl_easy_setopt(curl, CURLOPT_SSLKEYTYPE,     "PEM");
        curl_easy_setopt(curl, CURLOPT_CAINFO,         mtls_ca_file);
        curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);
        curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 2L);
        curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 5L);
        curl_easy_setopt(curl, CURLOPT_TIMEOUT,        60L);
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION,  capture_response);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA,      &resp);

        CURLcode res = curl_easy_perform(curl);

        if (res == CURLE_OK && resp.data) {
            printf("-> AI maze solver   [OK]\n");
            parse_plan_response(resp.data);
        } else {
            printf("-> AI maze solver   [FAIL] %s\n", curl_easy_strerror(res));
            ai_plan_len = 0;
        }
        fflush(stdout);

        curl_slist_free_all(headers);
        curl_easy_cleanup(curl);
    }

    free(resp.data);
    free(json_str);
    cJSON_Delete(root);
}

/* -------------------------------------------------------
   Re-plan from current position (synchronous).
   Called after a manual move to generate a new A* path
   from the robot's current position to the goal.
------------------------------------------------------- */
static void replan_from_position(int px, int py) {
    cJSON *root = cJSON_CreateObject();
    cJSON_AddNumberToObject(root, "from_x", px);
    cJSON_AddNumberToObject(root, "from_y", py);
    char *json_str = cJSON_PrintUnformatted(root);

    char url[512];
    snprintf(url, sizeof(url), "%s/%s/solve",
             "https://10.170.8.109:8447/maze", session_id);

    printf("--- Re-planning from (%d, %d) ---\n", px, py);
    fflush(stdout);

    struct response_buf resp = { .data = NULL, .size = 0 };

    CURL *curl = curl_easy_init();
    if (curl) {
        struct curl_slist *headers = NULL;
        headers = curl_slist_append(headers, "Content-Type: application/json");

        curl_easy_setopt(curl, CURLOPT_URL,            url);
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER,     headers);
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS,     json_str);
        curl_easy_setopt(curl, CURLOPT_SSLCERT,        mtls_client_cert);
        curl_easy_setopt(curl, CURLOPT_SSLCERTTYPE,    "PEM");
        curl_easy_setopt(curl, CURLOPT_SSLKEY,         mtls_client_key);
        curl_easy_setopt(curl, CURLOPT_SSLKEYTYPE,     "PEM");
        curl_easy_setopt(curl, CURLOPT_CAINFO,         mtls_ca_file);
        curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);
        curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 2L);
        curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 5L);
        curl_easy_setopt(curl, CURLOPT_TIMEOUT,        30L);
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION,  capture_response);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA,      &resp);

        CURLcode res = curl_easy_perform(curl);

        if (res == CURLE_OK && resp.data) {
            printf("-> Re-plan          [OK]\n");
            parse_plan_response(resp.data);
        } else {
            printf("-> Re-plan          [FAIL] %s\n", curl_easy_strerror(res));
        }
        fflush(stdout);

        curl_slist_free_all(headers);
        curl_easy_cleanup(curl);
    }

    free(resp.data);
    free(json_str);
    cJSON_Delete(root);
}

/** Map keyboard delta to plan step label. */
static const char *move_dir_name(int dx, int dy) {
    if (dx == 0 && dy == -1) return "UP";
    if (dx == 0 && dy ==  1) return "DOWN";
    if (dx == -1 && dy == 0) return "LEFT";
    if (dx ==  1 && dy == 0) return "RIGHT";
    return "";
}

/**
 * If the player's manual move matches the next AI plan step, advance plan index (no network).
 * Otherwise return false → caller should replan (plan mismatch or no plan left).
 */
static bool manual_move_matches_plan(int dx, int dy) {
    if (ai_plan_len <= 0 || ai_plan_index >= ai_plan_len)
        return false;
    const char *expect = ai_plan[ai_plan_index];
    const char *actual = move_dir_name(dx, dy);
    if (!actual[0] || strcmp(expect, actual) != 0)
        return false;
    ai_plan_index++;
    return true;
}

/* -------------------------------------------------------
   Utility helpers
------------------------------------------------------- */
static inline bool in_bounds(int x, int y) {
    return (x >= 0 && x < MAZE_W && y >= 0 && y < MAZE_H);
}

static void generate_session_id(char *out, size_t len) {
    const char *hex = "0123456789abcdef";
    char rand_part[17];
    for (int i = 0; i < 16; i++)
        rand_part[i] = hex[rand() % 16];
    rand_part[16] = '\0';

    time_t now = time(NULL);
    struct tm tm;
    gmtime_r(&now, &tm);

    snprintf(out, len, "team4-%04d%02d%02d-%02d%02d%02d-%s",
        tm.tm_year + 1900, tm.tm_mon + 1, tm.tm_mday,
        tm.tm_hour, tm.tm_min, tm.tm_sec,
        rand_part);
}

static void redis_connect(void) {
    struct timeval tv = { .tv_sec = 2, .tv_usec = 0 };
    redis_ctx = redisConnectWithTimeout("127.0.0.1", 6379, tv);
    if (!redis_ctx || redis_ctx->err) {
        fprintf(stderr, "Redis connection failed\n");
        if (redis_ctx) redisFree(redis_ctx);
        redis_ctx = NULL;
    } else {
        printf("Redis connected\n");
        fflush(stdout);
    }
}

/* -------------------------------------------------------
   Maze construction
------------------------------------------------------- */
static void knock_down(int x, int y, int nx, int ny) {
    if      (nx == x     && ny == y - 1) { g[y][x].walls &= ~WALL_N; g[ny][nx].walls &= ~WALL_S; }
    else if (nx == x + 1 && ny == y    ) { g[y][x].walls &= ~WALL_E; g[ny][nx].walls &= ~WALL_W; }
    else if (nx == x     && ny == y + 1) { g[y][x].walls &= ~WALL_S; g[ny][nx].walls &= ~WALL_N; }
    else if (nx == x - 1 && ny == y    ) { g[y][x].walls &= ~WALL_W; g[ny][nx].walls &= ~WALL_E; }
}

static void maze_init(void) {
    for (int y = 0; y < MAZE_H; y++)
        for (int x = 0; x < MAZE_W; x++) {
            g[y][x].walls   = WALL_N | WALL_E | WALL_S | WALL_W;
            g[y][x].visited = false;
        }
}

static void maze_generate(int sx, int sy) {
    typedef struct { int x, y; } P;
    P   stack[MAZE_W * MAZE_H];
    int top = 0;

    g[sy][sx].visited = true;
    stack[top++] = (P){ sx, sy };

    while (top > 0) {
        P   cur    = stack[top - 1];
        int x = cur.x, y = cur.y;

        P   neigh[4];
        int ncount = 0;

        const int dx[4] = {  0, 1, 0, -1 };
        const int dy[4] = { -1, 0, 1,  0 };

        for (int i = 0; i < 4; i++) {
            int nx = x + dx[i], ny = y + dy[i];
            if (in_bounds(nx, ny) && !g[ny][nx].visited)
                neigh[ncount++] = (P){ nx, ny };
        }

        if (ncount == 0) { top--; continue; }

        int pick = rand() % ncount;
        int nx = neigh[pick].x, ny = neigh[pick].y;
        knock_down(x, y, nx, ny);
        g[ny][nx].visited = true;
        stack[top++] = (P){ nx, ny };
    }

    for (int y = 0; y < MAZE_H; y++)
        for (int x = 0; x < MAZE_W; x++)
            g[y][x].visited = false;
}

/* -------------------------------------------------------
   Rendering
------------------------------------------------------- */
static void draw_maze(SDL_Renderer *r) {
    SDL_SetRenderDrawColor(r, 15, 15, 18, 255);
    SDL_RenderClear(r);

    SDL_SetRenderDrawColor(r, 230, 230, 230, 255);
    int ox = PAD, oy = PAD;

    for (int y = 0; y < MAZE_H; y++)
        for (int x = 0; x < MAZE_W; x++) {
            int     x0 = ox + x * CELL, y0 = oy + y * CELL;
            int     x1 = x0 + CELL,     y1 = y0 + CELL;
            uint8_t w  = g[y][x].walls;
            if (w & WALL_N) SDL_RenderDrawLine(r, x0, y0, x1, y0);
            if (w & WALL_E) SDL_RenderDrawLine(r, x1, y0, x1, y1);
            if (w & WALL_S) SDL_RenderDrawLine(r, x0, y1, x1, y1);
            if (w & WALL_W) SDL_RenderDrawLine(r, x0, y0, x0, y1);
        }
}

static void draw_player_goal(SDL_Renderer *r, int px, int py) {
    int ox = PAD, oy = PAD;

    SDL_Rect goal = {
        ox + (MAZE_W - 1) * CELL + 6,
        oy + (MAZE_H - 1) * CELL + 6,
        CELL - 12, CELL - 12
    };
    SDL_SetRenderDrawColor(r, 40, 160, 70, 255);
    SDL_RenderFillRect(r, &goal);

    SDL_Rect p = {
        ox + px * CELL + 8,
        oy + py * CELL + 8,
        CELL - 16, CELL - 16
    };
    SDL_SetRenderDrawColor(r, 213, 189, 64, 255);
    SDL_RenderFillRect(r, &p);
}

/* -------------------------------------------------------
   Movement
------------------------------------------------------- */
static bool try_move(int *px, int *py, int dx, int dy) {
    int x = *px, y = *py;
    int nx = x + dx, ny = y + dy;

    if (!in_bounds(nx, ny)) return false;

    uint8_t w = g[y][x].walls;
    if (dx ==  0 && dy == -1 && (w & WALL_N)) return false;
    if (dx ==  1 && dy ==  0 && (w & WALL_E)) return false;
    if (dx ==  0 && dy ==  1 && (w & WALL_S)) return false;
    if (dx == -1 && dy ==  0 && (w & WALL_W)) return false;

    *px = nx;
    *py = ny;
    move_sequence++;

    if      (dx == -1) moves_left_turn++;
    else if (dx ==  1) moves_right_turn++;
    else if (dy == -1) moves_straight++;
    else if (dy ==  1) moves_reverse++;

    send_json_telemetry("player_move", *px, *py, false);
    send_mission_to_ai_server();

    return true;
}

static void regenerate(int *px, int *py, SDL_Window *win) {
  maze_init();
  maze_generate(0, 0);
  generate_session_id(session_id, sizeof(session_id));
  printf("New mission session: %s\n", session_id);
  fflush(stdout);

  *px = 0;
  *py = 0;
  move_sequence = 0;
  moves_left_turn  = 0;
  moves_right_turn = 0;
  moves_straight   = 0;
  moves_reverse    = 0;
  mission_start_time = time(NULL);

  ai_autoplay   = false;
  ai_plan_len   = 0;
  ai_plan_index = 0;

  SDL_SetWindowTitle(win, "SDL2 Maze - A=AI solve, R=regen, L=dashboard");
  send_json_telemetry("maze_reset", *px, *py, false);
  send_maze_grid();
}

/* -------------------------------------------------------
   MAIN
------------------------------------------------------- */
int main(void) {
    srand((unsigned)time(NULL));
    generate_session_id(session_id, sizeof(session_id));
    mission_start_time = time(NULL);

    /* mTLS: load client cert paths from env or use defaults */
    mtls_client_cert = getenv("MTLS_CLIENT_CERT");
    mtls_client_key  = getenv("MTLS_CLIENT_KEY");
    mtls_ca_file     = getenv("MTLS_CA_FILE");
    if (!mtls_client_cert) mtls_client_cert = "infra/security/certs/client.crt";
    if (!mtls_client_key)  mtls_client_key  = "infra/security/certs/client.key";
    if (!mtls_ca_file)     mtls_ca_file     = "infra/security/certs/ca.crt";

    /* If default path missing and no env set, try maze-relative path */
    if (access(mtls_client_cert, R_OK) != 0 && !getenv("MTLS_CLIENT_CERT")) {
        mtls_client_cert = "../../infra/security/certs/client.crt";
        mtls_client_key  = "../../infra/security/certs/client.key";
        mtls_ca_file     = "../../infra/security/certs/ca.crt";
    }
    if (access(mtls_client_cert, R_OK) != 0 && !getenv("MTLS_CLIENT_CERT")) {
        mtls_client_cert = "../../../infra/security/certs/client.crt";
        mtls_client_key  = "../../../infra/security/certs/client.key";
        mtls_ca_file     = "../../../infra/security/certs/ca.crt";
    }

    /* Verify mTLS cert files exist */
    if (access(mtls_client_cert, R_OK) != 0 || access(mtls_client_key, R_OK) != 0 ||
        access(mtls_ca_file, R_OK) != 0) {
        fprintf(stderr, "mTLS cert files not found. Run from project root or maze/, or set:\n"
                "  MTLS_CLIENT_CERT MTLS_CLIENT_KEY MTLS_CA_FILE\n"
                "Generate certs: cd infra/security/certs && ./gen_mtls_certs.sh\n");
        return 1;
    }

    curl_global_init(CURL_GLOBAL_DEFAULT);
    redis_connect();

    /* FIX 4: Check SDL_Init return value */
    if (SDL_Init(SDL_INIT_VIDEO) != 0) {
        fprintf(stderr, "SDL_Init failed: %s\n", SDL_GetError());
        return 1;
    }

    SDL_Window *win = SDL_CreateWindow(
        "SDL2 Maze - A=AI solve, R=regen, L=dashboard",
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        PAD * 2 + MAZE_W * CELL,
        PAD * 2 + MAZE_H * CELL,
        SDL_WINDOW_SHOWN
    );
    /* FIX 4: Check window creation */
    if (!win) {
        fprintf(stderr, "SDL_CreateWindow failed: %s\n", SDL_GetError());
        SDL_Quit();
        return 1;
    }

    SDL_Renderer *r = SDL_CreateRenderer(win, -1, SDL_RENDERER_ACCELERATED);
    /* FIX 4: Check renderer creation */
    if (!r) {
        fprintf(stderr, "SDL_CreateRenderer failed: %s\n", SDL_GetError());
        SDL_DestroyWindow(win);
        SDL_Quit();
        return 1;
    }

    maze_init();
    maze_generate(0, 0);

    /* FIX 2: Startup connectivity probe.
       Prints status for all three servers immediately on launch,
       before the player presses any key. */
    printf("--- Startup connectivity test ---\n");
    fflush(stdout);
    send_json_telemetry("startup", 0, 0, false);
    send_mission_to_ai_server();
    send_maze_grid();

    int  px      = 0, py = 0;
    bool running = true;
    bool won     = false;

    while (running) {
        SDL_Event e;
        while (SDL_PollEvent(&e)) {

            if (e.type == SDL_QUIT) {
                flush_mission_on_game_exit();
                running = false;
            }

            if (e.type == SDL_KEYDOWN) {
                if (e.key.keysym.sym == SDLK_ESCAPE) {
                    flush_mission_on_game_exit();
                    running = false;
                }

            if (e.key.keysym.sym == SDLK_r) {
              if (move_sequence > 0 || mission_won)
                  flush_mission_summary(false, "user reset");
              won = false;
              mission_won = false;
              regenerate(&px, &py, win);
            }
                
            /* L key = Left Trigger on GameHat -> launch mission dashboard */
            if (e.key.keysym.sym == SDLK_l) {
                launch_mission_dashboard();
            }

            /* A key = toggle AI auto-play */
            if (e.key.keysym.sym == SDLK_a && !won) {
                if (ai_plan_len > 0 && ai_plan_index < ai_plan_len) {
                    ai_autoplay = !ai_autoplay;
                    ai_last_tick = SDL_GetTicks();
                    printf("AI auto-play %s (%d moves remaining)\n",
                           ai_autoplay ? "ON" : "OFF",
                           ai_plan_len - ai_plan_index);
                    fflush(stdout);
                    SDL_SetWindowTitle(win, ai_autoplay
                        ? "AI solving... (A=pause)"
                        : "SDL2 Maze - A=AI solve, R=regen, L=dashboard");
                } else {
                    printf("No AI plan available (server unreachable?)\n");
                    fflush(stdout);
                }
            }

                if (!won && !ai_autoplay && (
                    e.key.keysym.sym == SDLK_UP    ||
                    e.key.keysym.sym == SDLK_DOWN  ||
                    e.key.keysym.sym == SDLK_LEFT  ||
                    e.key.keysym.sym == SDLK_RIGHT
                )) {
                    int old_px = px, old_py = py;
                    int mdx = (e.key.keysym.sym == SDLK_RIGHT) - (e.key.keysym.sym == SDLK_LEFT);
                    int mdy = (e.key.keysym.sym == SDLK_DOWN)  - (e.key.keysym.sym == SDLK_UP);
                    try_move(&px, &py, mdx, mdy);

                    if (px == MAZE_W - 1 && py == MAZE_H - 1) {
                        won         = true;
                        mission_won = true;
                        SDL_SetWindowTitle(win, "You win!");
                        flush_mission_summary(true, "");
                        send_json_telemetry("player_won", px, py, true);
                        send_mission_to_ai_server();
                    } else if (px != old_px || py != old_py) {
                        /* Re-plan only on HTTPS when the move diverges from the stored plan
                           (or there is no remaining plan); following the plan advances index locally. */
                        if (!manual_move_matches_plan(mdx, mdy))
                            replan_from_position(px, py);
                    }
                }
            }
        }

        /* AI auto-play: execute one move per tick */
        if (ai_autoplay && !won && ai_plan_index < ai_plan_len) {
            Uint32 now_tick = SDL_GetTicks();
            if (now_tick - ai_last_tick >= AUTOPLAY_DELAY_MS) {
                ai_last_tick = now_tick;
                const char *move = ai_plan[ai_plan_index];
                int adx = 0, ady = 0;
                if (strcmp(move, "UP")    == 0) { adx =  0; ady = -1; }
                if (strcmp(move, "DOWN")  == 0) { adx =  0; ady =  1; }
                if (strcmp(move, "LEFT")  == 0) { adx = -1; ady =  0; }
                if (strcmp(move, "RIGHT") == 0) { adx =  1; ady =  0; }

                if (try_move(&px, &py, adx, ady)) {
                    ai_plan_index++;
                    if (px == MAZE_W - 1 && py == MAZE_H - 1) {
                        won         = true;
                        mission_won = true;
                        ai_autoplay = false;
                        SDL_SetWindowTitle(win, "AI solved the maze! R=regen");
                        flush_mission_summary(true, "");
                        send_json_telemetry("ai_won", px, py, true);
                        send_mission_to_ai_server();
                    }
                }
                if (ai_plan_index >= ai_plan_len && !won) {
                    ai_autoplay = false;
                    SDL_SetWindowTitle(win, "AI plan done (not at goal). A=retry");
                }
            }
        }

        draw_maze(r);
        draw_player_goal(r, px, py);
        SDL_RenderPresent(r);
    }

    if (redis_ctx) redisFree(redis_ctx);
    curl_global_cleanup();
    SDL_DestroyRenderer(r);
    SDL_DestroyWindow(win);
    SDL_Quit();
    return 0;
}
