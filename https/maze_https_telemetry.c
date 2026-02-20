#define _GNU_SOURCE
// maze_https_telemetry.c
// Simple HTTPS server for Mini Pupper (10.170.8.105)
// Receives POST /telemetry JSON and prints it to stdout
//
// Build:
/*   gcc -O2 -Wall -Wextra -std=c11 maze_https_telemetry.c -o maze_https_telemetry \
       $(pkg-config --cflags --libs libmicrohttpd) */
//
// Run:
//   ./maze_https_telemetry
//
// Requires: certs/server.crt and certs/server.key

#include <errno.h>
#include <microhttpd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <signal.h>
#include <unistd.h>

#define DEFAULT_PORT 8446

static const char *cert_file = "certs/server.crt";
static const char *key_file  = "certs/server.key";
static volatile int keep_running = 1;
static int telemetry_count = 0;

struct connection_info {
    char  *data;
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

    if (strcmp(method, "POST") != 0 || strcmp(url, "/telemetry") != 0)
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

    telemetry_count++;

    char ts[64];
    time_t now = time(NULL);
    struct tm tm;
    gmtime_r(&now, &tm);
    strftime(ts, sizeof(ts), "%Y-%m-%dT%H:%M:%SZ", &tm);

    printf("[%s] #%d  %s\n", ts, telemetry_count, ci->data);
    fflush(stdout);

    const char *resp_body = "{\"status\":\"ok\"}";
    struct MHD_Response *resp =
        MHD_create_response_from_buffer(strlen(resp_body),
                                         (void *)resp_body,
                                         MHD_RESPMEM_PERSISTENT);

    int ret = MHD_queue_response(connection, MHD_HTTP_OK, resp);
    MHD_destroy_response(resp);

    free(ci->data);
    free(ci);
    *con_cls = NULL;

    return ret;
}

int main(void) {
    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);

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

    printf("=== Mini Pupper Telemetry Receiver ===\n");
    printf("HTTPS listening on https://0.0.0.0:%d  (POST /telemetry)\n",
           DEFAULT_PORT);
    printf("Press Ctrl+C to stop\n\n");
    fflush(stdout);

    while (keep_running) {
        sleep(1);
    }

    printf("\nShutting down... Total received: %d\n", telemetry_count);
    MHD_stop_daemon(daemon);
    free(cert_pem);
    free(key_pem);
    return 0;
}
