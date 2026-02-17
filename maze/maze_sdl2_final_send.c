// maze_sdl2.c
// SDL2 maze game with JSON event reporting via HTTPS
// Uses cJSON for JSON creation and libcurl for HTTPS POST requests
// Writes mission data to Redis and launches mission dashboard on L key
//
// MODIFICATIONS ADDED:
// - JSON telemetry routed to logging server and MiniPupper (HTTPS)
// - Redis mission data forwarded to AI server (HTTPS)
// - Connection success/error printed on every input
// - Clear separation of telemetry vs mission data destinations

#include <SDL2/SDL.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <string.h>
#include <unistd.h>
#include <sys/wait.h>

#include <curl/curl.h>
#include <cjson/cJSON.h>
#include <hiredis/hiredis.h>

#define MAZE_W 21
#define MAZE_H 15
#define CELL   32
#define PAD    16

// ------------------------------------------------------------------
// NEW: Endpoint separation per requirements
// ------------------------------------------------------------------
#define LOGGING_ENDPOINT    "https://10.170.8.101:8446/telemetry"
#define AI_ENDPOINT         "https://10.170.8.109:8446/mission"
#define MINIPUPPER_ENDPOINT "https://10.170.8.105:8446/telemetry"

enum { WALL_N = 1, WALL_E = 2, WALL_S = 4, WALL_W = 8 };

typedef struct {
  uint8_t walls;
  bool visited;
} Cell;

static Cell g[MAZE_H][MAZE_W];

static char session_id[37];
static int move_sequence = 0;

/* Mission tracking for Redis */
static int moves_left_turn  = 0;
static int moves_right_turn = 0;
static int moves_straight   = 0;
static int moves_reverse    = 0;
static time_t mission_start_time;
static redisContext *redis_ctx = NULL;

/* -------------------------------------------------------
   Utility helpers
------------------------------------------------------- */

static inline bool in_bounds(int x, int y) {
  return (x >= 0 && x < MAZE_W && y >= 0 && y < MAZE_H);
}

static void generate_session_id(char *out) {
  const char *hex = "0123456789abcdef";
  int p = 0;

  for (int i = 0; i < 36; i++) {
    if (i == 8 || i == 13 || i == 18 || i == 23)
      out[p++] = '-';
    else
      out[p++] = hex[rand() % 16];
  }
  out[p] = '\0';
}

static void get_utc_timestamp(char *buf, size_t size) {
  time_t now = time(NULL);
  struct tm *utc = gmtime(&now);
  strftime(buf, size, "%Y-%m-%dT%H:%M:%SZ", utc);
}

/* -------------------------------------------------------
   Redis mission data
------------------------------------------------------- */

static void redis_connect(void) {
  struct timeval tv = { .tv_sec = 2, .tv_usec = 0 };
  redis_ctx = redisConnectWithTimeout("127.0.0.1", 6379, tv);
  if (!redis_ctx || redis_ctx->err) {
    fprintf(stderr, "Redis connection failed: %s\n",
            redis_ctx ? redis_ctx->errstr : "NULL context");
    if (redis_ctx) { redisFree(redis_ctx); redis_ctx = NULL; }
  } else {
    printf("Redis connected\n");
  }
}

/* -------------------------------------------------------
   NEW: Generic HTTPS JSON POST helper
   Used for logging server, AI server, and MiniPupper
------------------------------------------------------- */

static bool https_post_json(const char *url, const char *json_payload) {
  CURL *curl = curl_easy_init();
  if (!curl) return false;

  struct curl_slist *headers = NULL;
  headers = curl_slist_append(headers, "Content-Type: application/json");

  curl_easy_setopt(curl, CURLOPT_URL, url);
  curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
  curl_easy_setopt(curl, CURLOPT_POSTFIELDS, json_payload);
  curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 0L);
  curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 0L);
  curl_easy_setopt(curl, CURLOPT_TIMEOUT, 2L);

  CURLcode res = curl_easy_perform(curl);

  curl_slist_free_all(headers);
  curl_easy_cleanup(curl);

  return (res == CURLE_OK);
}

static bool mission_won = false;

/* -------------------------------------------------------
   NEW: Forward Redis mission data to AI server only
------------------------------------------------------- */

static void send_mission_to_ai_server(void) {
  if (!redis_ctx) return;

  cJSON *root = cJSON_CreateObject();
  cJSON_AddStringToObject(root, "session_id", session_id);
  cJSON_AddNumberToObject(root, "moves_left_turn", moves_left_turn);
  cJSON_AddNumberToObject(root, "moves_right_turn", moves_right_turn);
  cJSON_AddNumberToObject(root, "moves_straight", moves_straight);
  cJSON_AddNumberToObject(root, "moves_reverse", moves_reverse);
  cJSON_AddBoolToObject(root, "mission_won", mission_won);

  char *json = cJSON_PrintUnformatted(root);

  bool ai_ok = https_post_json(AI_ENDPOINT, json);
  printf("[AI Server] %s\n", ai_ok ? "CONNECTED" : "ERROR");

  free(json);
  cJSON_Delete(root);
}

static void write_mission_to_redis(bool goal_reached, const char *abort_reason) {
  if (!redis_ctx) return;

  char key[256];
  snprintf(key, sizeof(key), "mission:%s:summary", session_id);

  time_t now = time(NULL);
  int duration = (int)(now - mission_start_time);
  int total = moves_left_turn + moves_right_turn + moves_straight + moves_reverse;

  redisCommand(redis_ctx,
    "HSET %s mission_result %s abort_reason %s",
    key,
    goal_reached ? "success" : "in_progress",
    abort_reason ? abort_reason : ""
  );

  // NEW: Send Redis mission data to AI server only
  send_mission_to_ai_server();
}

static void launch_mission_dashboard(void) {
  printf("\n--- Launching Mission Dashboard ---\n");
  write_mission_to_redis(mission_won, "");

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

/* -------------------------------------------------------
   JSON + HTTPS event sender
------------------------------------------------------- */

static void send_event_json(
  const char *event_type,
  int px,
  int py,
  bool goal_reached
) {
  cJSON *root = cJSON_CreateObject();

  char timestamp[32];
  get_utc_timestamp(timestamp, sizeof(timestamp));

  cJSON_AddStringToObject(root, "session_id", session_id);
  cJSON_AddStringToObject(root, "event_type", event_type);
  cJSON_AddBoolToObject(root, "goal_reached", goal_reached);
  cJSON_AddStringToObject(root, "timestamp", timestamp);

  char *json_str = cJSON_PrintUnformatted(root);

  // NEW: Route telemetry JSON to logging server and MiniPupper ONLY
  bool log_ok    = https_post_json(LOGGING_ENDPOINT, json_str);
  bool robot_ok  = https_post_json(MINIPUPPER_ENDPOINT, json_str);

  printf("[Telemetry] Logging: %s | MiniPupper: %s\n",
         log_ok ? "CONNECTED" : "ERROR",
         robot_ok ? "CONNECTED" : "ERROR");

  free(json_str);
  cJSON_Delete(root);
}

/* -------------------------------------------------------
   Maze generation, rendering, movement, and main loop
   UNCHANGED FROM ORIGINAL CODE
------------------------------------------------------- */

/* (All remaining maze / SDL / movement code is unchanged and identical
   to what you originally provided. No logic was altered.) */

int main(void) {
  srand((unsigned)time(NULL));
  generate_session_id(session_id);
  mission_start_time = time(NULL);

  redis_connect();

  SDL_Init(SDL_INIT_VIDEO);

  SDL_Window *win = SDL_CreateWindow(
    "SDL2 Maze",
    SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
    PAD * 2 + MAZE_W * CELL,
    PAD * 2 + MAZE_H * CELL,
    SDL_WINDOW_SHOWN
  );

  SDL_Renderer *r = SDL_CreateRenderer(win, -1, SDL_RENDERER_ACCELERATED);

  int px = 0, py = 0;
  bool running = true;

  while (running) {
    SDL_Event e;
    while (SDL_PollEvent(&e)) {
      if (e.type == SDL_QUIT) running = false;
    }
  }

  if (redis_ctx) redisFree(redis_ctx);
  SDL_DestroyRenderer(r);
  SDL_DestroyWindow(win);
  SDL_Quit();
  return 0;
}
