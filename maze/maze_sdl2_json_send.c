// maze_sdl2.c
// SDL2 maze game with JSON event reporting via HTTP
// Uses cJSON for JSON creation and libcurl for HTTP POST requests

#include <SDL2/SDL.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <string.h>

#include <curl/curl.h>   // Used for HTTP communication
#include <cjson/cJSON.h> // Used for building JSON safely

#define MAZE_W 21
#define MAZE_H 15
#define CELL   32
#define PAD    16

// Local HTTP endpoint where events are sent
#define EVENT_ENDPOINT "http://localhost:8080/events"

// Wall bitmask for each cell
enum { WALL_N = 1, WALL_E = 2, WALL_S = 4, WALL_W = 8 };

// Structure representing a single maze cell
typedef struct {
  uint8_t walls;
  bool visited;
} Cell;

// The maze grid
static Cell g[MAZE_H][MAZE_W];

// Unique session identifier (generated once per run)
static char session_id[37];

// Counts total player moves
static int move_sequence = 0;

/* -------------------------------------------------------
   Utility Functions
   ------------------------------------------------------- */

// Check if coordinates are inside the maze bounds
static inline bool in_bounds(int x, int y) {
  return (x >= 0 && x < MAZE_W && y >= 0 && y < MAZE_H);
}

// Generate a simple UUID-like string for session_id
// NOTE: This is NOT cryptographically secure, but is fine for logging/demo
static void generate_session_id(char *out) {
  const char *hex = "0123456789abcdef";
  int i, p = 0;

  srand((unsigned)time(NULL));

  for (i = 0; i < 36; i++) {
    if (i == 8 || i == 13 || i == 18 || i == 23) {
      out[p++] = '-';
    } else {
      out[p++] = hex[rand() % 16];
    }
  }
  out[p] = '\0';
}

// Create a UTC timestamp in ISO-8601 format
// Example: 2026-01-25T11:44:03Z
static void get_utc_timestamp(char *buf, size_t size) {
  time_t now = time(NULL);
  struct tm *utc = gmtime(&now);
  strftime(buf, size, "%Y-%m-%dT%H:%M:%SZ", utc);
}

/* -------------------------------------------------------
   HTTP + JSON Reporting
   ------------------------------------------------------- */

// Send a JSON payload to the local HTTP service
static void send_event_json(
  const char *event_type,
  int px,
  int py,
  bool goal_reached
) {
  // Create the root JSON object
  cJSON *root = cJSON_CreateObject();

  // Timestamp buffer
  char timestamp[32];
  get_utc_timestamp(timestamp, sizeof(timestamp));

  // Add top-level JSON fields
  cJSON_AddStringToObject(root, "session_id", session_id);
  cJSON_AddStringToObject(root, "event_type", event_type);
  cJSON_AddBoolToObject(root, "goal_reached", goal_reached);
  cJSON_AddStringToObject(root, "timestamp", timestamp);

  // Create "input" object
  cJSON *input = cJSON_AddObjectToObject(root, "input");
  cJSON_AddStringToObject(input, "device", "keyboard");
  cJSON_AddNumberToObject(input, "move_sequence", move_sequence);

  // Create "player" object
  cJSON *player = cJSON_AddObjectToObject(root, "player");
  cJSON *position = cJSON_AddObjectToObject(player, "position");
  cJSON_AddNumberToObject(position, "x", px);
  cJSON_AddNumberToObject(position, "y", py);

  // Convert JSON object to formatted string
  char *json_str = cJSON_Print(root);

  // Print JSON payload to console for verification
  printf("\n--- JSON Payload ---\n%s\n", json_str);

  // Initialize libcurl
  CURL *curl = curl_easy_init();
  if (curl) {
    struct curl_slist *headers = NULL;

    // Tell server we're sending JSON
    headers = curl_slist_append(headers, "Content-Type: application/json");

    // Configure curl options
    curl_easy_setopt(curl, CURLOPT_URL, EVENT_ENDPOINT);
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, json_str);

    // Perform HTTP request
    CURLcode res = curl_easy_perform(curl);

    // Check if request succeeded
    if (res == CURLE_OK) {
      printf("HTTP POST successful ✔\n");
    } else {
      printf("HTTP POST failed ✘: %s\n", curl_easy_strerror(res));
    }

    // Cleanup curl
    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);
  }

  // Free allocated memory
  free(json_str);
  cJSON_Delete(root);
}

/* -------------------------------------------------------
   Maze Generation Logic (unchanged)
   ------------------------------------------------------- */

// Remove wall between two adjacent cells
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

// Initialize maze with all walls intact
static void maze_init(void) {
  for (int y = 0; y < MAZE_H; y++) {
    for (int x = 0; x < MAZE_W; x++) {
      g[y][x].walls = WALL_N | WALL_E | WALL_S | WALL_W;
      g[y][x].visited = false;
    }
  }
}

// Generate maze using DFS backtracker
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

    const int dx[4] = { 0, 1, 0, -1 };
    const int dy[4] = { -1, 0, 1, 0 };

    for (int i = 0; i < 4; i++) {
      int nx = x + dx[i], ny = y + dy[i];
      if (in_bounds(nx, ny) && !g[ny][nx].visited) {
        neigh[ncount++] = (P){nx, ny};
      }
    }

    if (ncount == 0) {
      top--;
      continue;
    }

    int pick = rand() % ncount;
    int nx = neigh[pick].x, ny = neigh[pick].y;

    knock_down(x, y, nx, ny);
    g[ny][nx].visited = true;
    stack[top++] = (P){nx, ny};
  }

  for (int y = 0; y < MAZE_H; y++)
    for (int x = 0; x < MAZE_W; x++)
      g[y][x].visited = false;
}

/* -------------------------------------------------------
   Player Movement
   ------------------------------------------------------- */

static bool try_move(int *px, int *py, int dx, int dy) {
  int x = *px, y = *py;
  int nx = x + dx, ny = y + dy;

  if (!in_bounds(nx, ny)) return false;

  uint8_t w = g[y][x].walls;

  if (dx == 0 && dy == -1 && (w & WALL_N)) return false;
  if (dx == 1 && dy == 0  && (w & WALL_E)) return false;
  if (dx == 0 && dy == 1  && (w & WALL_S)) return false;
  if (dx == -1 && dy == 0 && (w & WALL_W)) return false;

  *px = nx;
  *py = ny;

  // Count the move
  move_sequence++;

  // Send player_move event
  send_event_json("player_move", *px, *py, false);

  return true;
}

/* -------------------------------------------------------
   Game Reset
   ------------------------------------------------------- */

static void regenerate(int *px, int *py, SDL_Window *win) {
  maze_init();
  maze_generate(0, 0);

  *px = 0;
  *py = 0;
  move_sequence = 0;

  SDL_SetWindowTitle(win, "SDL2 Maze - Reach the green goal");

  // Send maze_reset event
  send_event_json("maze_reset", *px, *py, false);
}

/* -------------------------------------------------------
   Main Program
   ------------------------------------------------------- */

int main(int argc, char **argv) {
  (void)argc;
  (void)argv;

  // Generate session ID once
  generate_session_id(session_id);

  // Initialize SDL
  if (SDL_Init(SDL_INIT_VIDEO) != 0) {
    fprintf(stderr, "SDL_Init failed\n");
    return 1;
  }

  int win_w = PAD * 2 + MAZE_W * CELL;
  int win_h = PAD * 2 + MAZE_H * CELL;

  SDL_Window *win = SDL_CreateWindow(
    "SDL2 Maze",
    SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
    win_w, win_h,
    SDL_WINDOW_SHOWN
  );

  SDL_Renderer *r = SDL_CreateRenderer(win, -1, SDL_RENDERER_ACCELERATED);

  int px = 0, py = 0;
  bool running = true;
  bool won = false;

  regenerate(&px, &py, win);

  while (running) {
    SDL_Event e;
    while (SDL_PollEvent(&e)) {
      if (e.type == SDL_QUIT) running = false;

      if (e.type == SDL_KEYDOWN) {
        SDL_Keycode k = e.key.keysym.sym;

        if (k == SDLK_ESCAPE) running = false;

        if (k == SDLK_r) {
          won = false;
          regenerate(&px, &py, win);
        }

        if (!won) {
          if (k == SDLK_UP || k == SDLK_w)    try_move(&px, &py, 0, -1);
          if (k == SDLK_RIGHT || k == SDLK_d) try_move(&px, &py, 1, 0);
          if (k == SDLK_DOWN || k == SDLK_s)  try_move(&px, &py, 0, 1);
          if (k == SDLK_LEFT || k == SDLK_a)  try_move(&px, &py, -1, 0);

          if (px == MAZE_W - 1 && py == MAZE_H - 1) {
            won = true;
            SDL_SetWindowTitle(win, "You win!");

            // Send player_won event
            send_event_json("player_won", px, py, true);
          }
        }
      }
    }

    SDL_SetRenderDrawColor(r, 20, 20, 25, 255);
    SDL_RenderClear(r);
    SDL_RenderPresent(r);
  }

  SDL_DestroyRenderer(r);
  SDL_DestroyWindow(win);
  SDL_Quit();
  return 0;
}
