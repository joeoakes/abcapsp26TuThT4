// maze_https_redis.c
// HTTPS server for the AI Server (10.170.8.109)
// Receives POST /mission JSON from the maze app and stores it in Redis
// Uses redis-cli (no hiredis library needed)
//
// Build:
/*  gcc -O2 -Wall -Wextra -std=c11 maze_https_redis.c -o maze_https_redis \ 
       $(pkg-config --cflags --libs libmicrohttpd)
*/
//
// Run:
//   ./maze_https_redis
//
// Requires: certs/server.crt, certs/server.key, and redis-cli in PATH

#define _GNU_SOURCE
#include <errno.h>
#include <microhttpd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <signal.h>
#include <unistd.h>

#define DEFAULT_PORT      8446

static const char *cert_file = "certs/server.crt";
static const char *key_file  = "certs/server.key";
static volatile int keep_running = 1;

struct connection_info {
    char *data;
    size_t size;
};

static void handle_signal(int sig) {
    (void)sig;
    keep_running = 0;
}

static char *read_file(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *buf = malloc(n + 1);
    if (!buf) { fclose(f); return NULL; }
    if (fread(buf, 1, n, f) != (size_t)n) { fclose(f); free(buf); return NULL; }
    buf[n] = '\0';
    fclose(f);
    return buf;
}

static void get_utc_iso8601(char *buf, size_t len) {
    time_t now = time(NULL);
    struct tm tm;
    gmtime_r(&now, &tm);
    strftime(buf, len, "%Y-%m-%dT%H:%M:%SZ", &tm);
}

/* Run a redis-cli command and return 0 on success */
static int redis_cmd(const char *cmd) {
    char full[4096];
    snprintf(full, sizeof(full), "redis-cli %s", cmd);
    FILE *fp = popen(full, "r");
    if (!fp) return -1;
    char line[256];
    int ok = 0;
    while (fgets(line, sizeof(line), fp)) {
        /* Check for error responses */
        if (strstr(line, "ERR") || strstr(line, "error")) ok = -1;
    }
    int status = pclose(fp);
    return (status == 0 && ok == 0) ? 0 : -1;
}

/* Store mission JSON in Redis using redis-cli */
static int store_in_redis(const char *json) {
    char ts[64];
    get_utc_iso8601(ts, sizeof(ts));

    /* Escape single quotes in JSON for shell safety */
    /* Use a temp file approach to avoid shell escaping issues */
    FILE *tmp = fopen("/tmp/maze_mission_payload.json", "w");
    if (!tmp) return -1;
    fputs(json, tmp);
    fclose(tmp);

    /* RPUSH mission:queue <json> */
    char cmd[512];
    snprintf(cmd, sizeof(cmd),
        "-x RPUSH mission:queue < /tmp/maze_mission_payload.json");
    int r1 = redis_cmd(cmd);

    /* SET mission:latest <json> */
    snprintf(cmd, sizeof(cmd),
        "-x SET mission:latest < /tmp/maze_mission_payload.json");
    int r2 = redis_cmd(cmd);

    /* SET mission:last_received_at <timestamp> */
    snprintf(cmd, sizeof(cmd),
        "SET mission:last_received_at %s", ts);
    int r3 = redis_cmd(cmd);

    return (r1 == 0 && r2 == 0 && r3 == 0) ? 0 : -1;
}

static enum MHD_Result handle_post(void *cls,
                       struct MHD_Connection *connection,
                       const char *url,
                       const char *method,
                       const char *version,
                       const char *upload_data,
                       size_t *upload_data_size,
                       void **con_cls)
{
    (void)version;
    (void)cls;

    if (strcmp(method, "POST") != 0 || strcmp(url, "/mission") != 0)
        return MHD_NO;

    if (*con_cls == NULL) {
        struct connection_info *ci = calloc(1, sizeof(*ci));
        *con_cls = ci;
        return MHD_YES;
    }

    struct connection_info *ci = *con_cls;

    if (*upload_data_size != 0) {
        ci->data = realloc(ci->data, ci->size + *upload_data_size + 1);
        memcpy(ci->data + ci->size, upload_data, *upload_data_size);
        ci->size += *upload_data_size;
        ci->data[ci->size] = '\0';
        *upload_data_size = 0;
        return MHD_YES;
    }

    const char *resp_body;
    int http_status;

    if (store_in_redis(ci->data) == 0) {
        printf("[OK] Mission data stored in Redis\n");
        resp_body = "{\"status\":\"ok\"}";
        http_status = MHD_HTTP_OK;
    } else {
        fprintf(stderr, "[ERROR] Failed to store in Redis\n");
        resp_body = "{\"status\":\"error\",\"message\":\"Redis insert failed\"}";
        http_status = MHD_HTTP_INTERNAL_SERVER_ERROR;
    }

    struct MHD_Response *resp =
        MHD_create_response_from_buffer(strlen(resp_body),
                                         (void *)resp_body,
                                         MHD_RESPMEM_PERSISTENT);

    int ret = MHD_queue_response(connection, http_status, resp);
    MHD_destroy_response(resp);

    free(ci->data);
    free(ci);
    *con_cls = NULL;

    return ret;
}

int main(void) {
    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);

    /* Verify redis-cli works */
    if (system("redis-cli ping > /dev/null 2>&1") != 0) {
        fprintf(stderr, "ERROR: redis-cli ping failed. Is Redis running?\n");
        return 1;
    }
    printf("Redis connection verified (redis-cli ping OK)\n");

    char *cert_pem = read_file(cert_file);
    char *key_pem  = read_file(key_file);
    if (!cert_pem || !key_pem) {
        fprintf(stderr, "Failed to read cert/key files from %s / %s\n",
                cert_file, key_file);
        return 1;
    }

    struct MHD_Daemon *daemon = MHD_start_daemon(
        MHD_USE_THREAD_PER_CONNECTION | MHD_USE_TLS,
        DEFAULT_PORT,
        NULL, NULL,
        &handle_post, NULL,
        MHD_OPTION_HTTPS_MEM_CERT, cert_pem,
        MHD_OPTION_HTTPS_MEM_KEY,  key_pem,
        MHD_OPTION_END);

    if (!daemon) {
        fprintf(stderr, "Failed to start HTTPS server on port %d\n",
                DEFAULT_PORT);
        return 1;
    }

    printf("========================================\n");
    printf("Database backend: Redis\n");
    printf("Redis host: localhost\n");
    printf("Redis port: 6379\n");
    printf("Key namespace example: team4ttmission:TEST_MISSION\n");
    printf("========================================\n");
    printf("HTTPS Redis mission server running on port %d\n", DEFAULT_PORT);

    while (keep_running) {
        sleep(1);
    }

    printf("\nShutting down...\n");
    MHD_stop_daemon(daemon);
    free(cert_pem);
    free(key_pem);
    return 0;
}
