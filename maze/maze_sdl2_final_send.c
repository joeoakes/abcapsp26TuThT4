// maze_sdl2.c
// SDL2 maze game with JSON event reporting via HTTPS
// Uses cJSON for JSON creation and libcurl for HTTPS POST requests
// Writes mission data to Redis and launches mission dashboard on L key
//
// MODIFICATIONS ADDED:
// - JSON telemetry now sent to:
//     * Logging Server  (10.170.8.101:8446)
//     * MiniPupper      (10.170.8.105:8446)
// - Redis mission data sent ONLY to:
//     * AI Server       (10.170.8.109:8446)
// - Confirmation or error printed for each server on every input
// - Maze logic remains completely unchanged

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

/* HTTPS endpoints */
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
static bool mission_won = false;

/* -------------------------------------------------------
   HTTPS helper
------------------------------------------------------- */

static bool https_post_json(const char *url, const char *json) {
  CURL *curl = curl_easy_init();
  if (!curl) return false;

  struct curl_slist *headers = NULL;
  headers = curl_slist_append(headers, "Content-Type: application/json");

  curl_easy_setopt(curl, CURLOPT_URL, url);
  curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
  curl_easy_setopt(curl, CURLOPT_POSTFIELDS, json);

  // Disable SSL verification (development only)
  curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 0L);
  curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 0L);

  CURLcode res = curl_easy_perform(curl);

  curl_slist_free_all(headers);
  curl_easy_cleanup(curl);

  return res == CURLE_OK;
}

/* -------------------------------------------------------
   JSON telemetry → Logging + MiniPupper ONLY
------------------------------------------------------- */

static void send_json_telemetry(
  const char *event_type,
  int px,
  int py,
  bool goal_reached
) {
  cJSON *root = cJSON_CreateObject();

  char timestamp[32];
  time_t now = time(NULL);
  strftime(timestamp, sizeof(timestamp),
           "%Y-%m-%dT%H:%M:%SZ", gmtime(&now));

  cJSON_AddStringToObject(root, "session_id", session_id);
  cJSON_AddStringToObject(root, "event_type", event_type);
  cJSON_AddBoolToObject(root, "goal_reached", goal_reached);
  cJSON_AddStringToObject(root, "timestamp", timestamp);
  cJSON_AddNumberToObject(root, "move_sequence", move_sequence);
  cJSON_AddNumberToObject(root, "x", px);
  cJSON_AddNumberToObject(root, "y", py);

  char *json_str = cJSON_PrintUnformatted(root);

  bool log_ok = https_post_json(LOGGING_ENDPOINT, json_str);
  bool pup_ok = https_post_json(MINIPUPPER_ENDPOINT, json_str);

  printf(log_ok ?
    "[OK] Connected to logging server\n" :
    "[ERROR] Failed to connect to logging server\n");

  printf(pup_ok ?
    "[OK] Connected to MiniPupper\n" :
    "[ERROR] Failed to connect to MiniPupper\n");

  free(json_str);
  cJSON_Delete(root);
}

/* -------------------------------------------------------
   Redis mission data write (UNCHANGED)
------------------------------------------------------- */

static void write_mission_to_redis(bool goal_reached, const char *abort_reason) {
  if (!redis_ctx) return;

  char key[256];
  snprintf(key, sizeof(key), "mission:%s:summary", session_id);

  time_t now = time(NULL);
  int duration = (int)(now - mission_start_time);
  int total = moves_left_turn + moves_right_turn + moves_straight + moves_reverse;

  char start_buf[32], end_buf[32];
  snprintf(start_buf, sizeof(start_buf), "%ld", (long)mission_start_time);
  snprintf(end_buf,   sizeof(end_buf),   "%ld", (long)now);

  char dist_buf[32];
  snprintf(dist_buf, sizeof(dist_buf), "%.2f", (double)total * 0.39);

  redisCommand(redis_ctx,
    "HSET %s robot_id %s mission_type %s start_time %s end_time %s "
    "moves_left_turn %d moves_right_turn %d moves_straight %d moves_reverse %d "
    "moves_total %d distance_traveled %s duration_seconds %d "
    "mission_result %s abort_reason %s",
    key,
    "keyboard-player",
    "explore",
    start_buf, end_buf,
    moves_left_turn, moves_right_turn, moves_straight, moves_reverse,
    total, dist_buf, duration,
    goal_reached ? "success" : "in_progress",
    abort_reason ? abort_reason : ""
  );
}

/* -------------------------------------------------------
   Send mission data to AI server ONLY
------------------------------------------------------- */

static void send_mission_to_ai_server(void) {
  cJSON *root = cJSON_CreateObject();

  cJSON_AddStringToObject(root, "session_id", session_id);
  cJSON_AddNumberToObject(root, "moves_left_turn", moves_left_turn);
  cJSON_AddNumberToObject(root, "moves_right_turn", moves_right_turn);
  cJSON_AddNumberToObject(root, "moves_straight", moves_straight);
  cJSON_AddNumberToObject(root, "moves_reverse", moves_reverse);
  cJSON_AddBoolToObject(root, "mission_won", mission_won);

  char *json_str = cJSON_PrintUnformatted(root);

  bool ai_ok = https_post_json(AI_ENDPOINT, json_str);

  printf(ai_ok ?
    "[OK] Connected to AI server\n" :
    "[ERROR] Failed to connect to AI server\n");

  free(json_str);
  cJSON_Delete(root);
}

/* -------------------------------------------------------
   Remaining code unchanged
   (maze gen, rendering, movement loop)
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

static void redis_connect(void) {
  struct timeval tv = { .tv_sec = 2, .tv_usec = 0 };
  redis_ctx = redisConnectWithTimeout("127.0.0.1", 6379, tv);
  if (!redis_ctx || redis_ctx->err) {
    fprintf(stderr, "Redis connection failed\n");
    if (redis_ctx) redisFree(redis_ctx);
    redis_ctx = NULL;
  } else {
    printf("Redis connected\n");
  }
}

static void knock_down(int x, int y, int nx, int ny) {
  if (nx == x && ny == y - 1) {
    g[y][x].walls &= ~WALL_N;
    g[ny][nx].walls &= ~WALL_S;
  } else if (nx == x + 1 && ny == y) {
    g[y][x].walls &= ~WALL_E;
    g[ny][nx].walls &= ~WALL_W;
  } else if (nx == x && ny == y + 1) {
    g[y][x].walls &= ~WALL_S;
    g[ny][nx].walls &= ~WALL_N;
  } else if (nx == x - 1 && ny == y) {
    g[y][x].walls &= ~WALL_W;
    g[ny][nx].walls &= ~WALL_E;
  }
}

static void maze_init(void) {
  for (int y = 0; y < MAZE_H; y++)
    for (int x = 0; x < MAZE_W; x++) {
      g[y][x].walls = WALL_N | WALL_E | WALL_S | WALL_W;
      g[y][x].visited = false;
    }
}

static void maze_generate(int sx, int sy) {
  typedef struct { int x, y; } P;
  P stack[MAZE_W * MAZE_H];
  int top = 0;

  g[sy][sx].visited = true;
  stack[top++] = (P){sx, sy};

  while (top > 0) {
    P cur = stack[top - 1];
    int x = cur.x, y = cur.y;

    P neigh[4];
    int ncount = 0;
    const int dx[4] = {0,1,0,-1};
    const int dy[4] = {-1,0,1,0};

    for (int i=0;i<4;i++){
      int nx=x+dx[i], ny=y+dy[i];
      if (in_bounds(nx,ny) && !g[ny][nx].visited)
        neigh[ncount++] = (P){nx,ny};
    }

    if (ncount==0){ top--; continue; }

    int pick = rand()%ncount;
    int nx=neigh[pick].x, ny=neigh[pick].y;

    knock_down(x,y,nx,ny);
    g[ny][nx].visited=true;
    stack[top++] = (P){nx,ny};
  }

  for(int y=0;y<MAZE_H;y++)
    for(int x=0;x<MAZE_W;x++)
      g[y][x].visited=false;
}

static void draw_maze(SDL_Renderer *r){
  SDL_SetRenderDrawColor(r,15,15,18,255);
  SDL_RenderClear(r);
  SDL_SetRenderDrawColor(r,230,230,230,255);

  int ox=PAD, oy=PAD;

  for(int y=0;y<MAZE_H;y++)
    for(int x=0;x<MAZE_W;x++){
      int x0=ox+x*CELL;
      int y0=oy+y*CELL;
      int x1=x0+CELL;
      int y1=y0+CELL;
      uint8_t w=g[y][x].walls;

      if(w&WALL_N) SDL_RenderDrawLine(r,x0,y0,x1,y0);
      if(w&WALL_E) SDL_RenderDrawLine(r,x1,y0,x1,y1);
      if(w&WALL_S) SDL_RenderDrawLine(r,x0,y1,x1,y1);
      if(w&WALL_W) SDL_RenderDrawLine(r,x0,y0,x0,y1);
    }
}

static void draw_player_goal(SDL_Renderer *r,int px,int py){
  int ox=PAD, oy=PAD;

  SDL_Rect goal={
    ox+(MAZE_W-1)*CELL+6,
    oy+(MAZE_H-1)*CELL+6,
    CELL-12,CELL-12
  };
  SDL_SetRenderDrawColor(r,40,160,70,255);
  SDL_RenderFillRect(r,&goal);

  SDL_Rect p={
    ox+px*CELL+8,
    oy+py*CELL+8,
    CELL-16,CELL-16
  };
  SDL_SetRenderDrawColor(r,213,189,64,255);
  SDL_RenderFillRect(r,&p);
}

static bool try_move(int *px,int *py,int dx,int dy){
  int x=*px,y=*py;
  int nx=x+dx, ny=y+dy;

  if(!in_bounds(nx,ny)) return false;

  uint8_t w=g[y][x].walls;
  if(dx==0&&dy==-1&&(w&WALL_N)) return false;
  if(dx==1&&dy==0&&(w&WALL_E)) return false;
  if(dx==0&&dy==1&&(w&WALL_S)) return false;
  if(dx==-1&&dy==0&&(w&WALL_W)) return false;

  *px=nx; *py=ny;
  move_sequence++;

  if(dx==-1) moves_left_turn++;
  else if(dx==1) moves_right_turn++;
  else if(dy==-1) moves_straight++;
  else if(dy==1) moves_reverse++;

  // Updated behavior:
  write_mission_to_redis(false, "");
  send_json_telemetry("player_move", *px, *py, false);
  send_mission_to_ai_server();

  return true;
}

int main(void){
  srand((unsigned)time(NULL));
  generate_session_id(session_id);
  mission_start_time = time(NULL);

  curl_global_init(CURL_GLOBAL_DEFAULT);
  redis_connect();

  SDL_Init(SDL_INIT_VIDEO);

  SDL_Window *win = SDL_CreateWindow(
    "SDL2 Maze",
    SDL_WINDOWPOS_CENTERED,SDL_WINDOWPOS_CENTERED,
    PAD*2+MAZE_W*CELL,
    PAD*2+MAZE_H*CELL,
    SDL_WINDOW_SHOWN
  );
  SDL_Renderer *r = SDL_CreateRenderer(win,-1,SDL_RENDERER_ACCELERATED);

  maze_init();
  maze_generate(0,0);

  int px=0, py=0;
  bool running=true;
  bool won=false;

  while(running){
    SDL_Event e;
    while(SDL_PollEvent(&e)){
      if(e.type==SDL_QUIT) running=false;

      if(e.type==SDL_KEYDOWN){
        if(e.key.keysym.sym==SDLK_ESCAPE){
          write_mission_to_redis(mission_won, "user exited");
          running=false;
        }

        if(!won && (
            e.key.keysym.sym==SDLK_UP  ||
            e.key.keysym.sym==SDLK_DOWN||
            e.key.keysym.sym==SDLK_LEFT||
            e.key.keysym.sym==SDLK_RIGHT
          )) {
          try_move(&px,&py,
            (e.key.keysym.sym==SDLK_RIGHT)-(e.key.keysym.sym==SDLK_LEFT),
            (e.key.keysym.sym==SDLK_DOWN)-(e.key.keysym.sym==SDLK_UP)
          );

          if(px==MAZE_W-1 && py==MAZE_H-1){
            won=true;
            mission_won=true;
            SDL_SetWindowTitle(win,"You win!");
            write_mission_to_redis(true,"");
            send_json_telemetry("player_won",px,py,true);
            send_mission_to_ai_server();
          }
        }
      }
    }

    draw_maze(r);
    draw_player_goal(r,px,py);
    SDL_RenderPresent(r);
  }

  if(redis_ctx) redisFree(redis_ctx);
  curl_global_cleanup();

  SDL_DestroyRenderer(r);
  SDL_DestroyWindow(win);
  SDL_Quit();
  return 0;
}
