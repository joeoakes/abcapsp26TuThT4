#define _GNU_SOURCE
// maze_https_mongo.c — HTTPS server with mTLS, stores JSON in MongoDB
//
// Build (run from https/):
/*
gcc -O2 -Wall -Wextra -std=c11 maze_https_mongo.c -o maze_https_mongo \
      $(pkg-config --cflags --libs libmicrohttpd libmongoc-1.0 gnutls)
*/
//
// Requires: certs/server.crt, certs/server.key, certs/ca.crt (mTLS)

#include <errno.h>
#include <microhttpd.h>
#include <gnutls/gnutls.h>
#include <gnutls/x509.h>
#include <mongoc/mongoc.h>
#include <bson/bson.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define DEFAULT_PORT 8446
#define POSTBUFFERSIZE  4096
#define MAXNAMESIZE     64
#define MAXANSWERSIZE   512
#define DEFAULT_MONGO_URI "mongodb://localhost:27017"
#define DEFAULT_MONGO_DB  "maze"
#define DEFAULT_MONGO_COL "team4ttmoves"

static const char *cert_file = "certs/server.crt";
static const char *key_file  = "certs/server.key";
static const char *ca_file   = "certs/ca.crt";   /* CA for verifying client certs (mTLS) */
static mongoc_client_pool_t *mongo_pool;

struct connection_info {
    char *data;
    size_t size;
};

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

static gnutls_x509_crt_t get_client_certificate(gnutls_session_t tls_session) {
    unsigned int listsize;
    const gnutls_datum_t *pcert;
    gnutls_certificate_status_t client_cert_status;
    gnutls_x509_crt_t client_cert;

    if (tls_session == NULL) return NULL;
    if (gnutls_certificate_verify_peers2(tls_session, &client_cert_status)) return NULL;
    if (0 != client_cert_status) {
        fprintf(stderr, "Failed: Client certificate invalid: %u\n", (unsigned)client_cert_status);
        return NULL;
    }
    pcert = gnutls_certificate_get_peers(tls_session, &listsize);
    if ((pcert == NULL) || (listsize == 0)) {
        fprintf(stderr, "Failed to retrieve client certificate chain\n");
        return NULL;
    }
    if (gnutls_x509_crt_init(&client_cert)) {
        fprintf(stderr, "Failed to initialize client certificate\n");
        return NULL;
    }
    if (gnutls_x509_crt_import(client_cert, &pcert[0], GNUTLS_X509_FMT_DER)) {
        fprintf(stderr, "Failed to import client certificate\n");
        gnutls_x509_crt_deinit(client_cert);
        return NULL;
    }
    return client_cert;
}

static void get_utc_iso8601(char *buf, size_t len) {
    time_t now = time(NULL);
    struct tm tm;
    gmtime_r(&now, &tm);
    strftime(buf, len, "%Y-%m-%dT%H:%M:%SZ", &tm);
}

struct app_config {
    const char *mongo_uri;
    const char *mongo_db;
    const char *mongo_col;
};

static struct app_config config;

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

    /* mTLS: verify client certificate (professor's approach) */
    const union MHD_ConnectionInfo *ci_info = MHD_get_connection_info(connection, MHD_CONNECTION_INFO_GNUTLS_SESSION);
    if (ci_info == NULL) {
        fprintf(stderr, "Not a TLS connection\n");
        return MHD_NO;
    }
    gnutls_session_t tls_session = (gnutls_session_t)ci_info->tls_session;
    gnutls_x509_crt_t client_cert = get_client_certificate(tls_session);
    if (client_cert == NULL) {
        const char *error_msg = "Client certificate required";
        struct MHD_Response *resp = MHD_create_response_from_buffer(strlen(error_msg), (void *)error_msg, MHD_RESPMEM_MUST_COPY);
        int ret = MHD_queue_response(connection, MHD_HTTP_UNAUTHORIZED, resp);
        MHD_destroy_response(resp);
        return (enum MHD_Result)ret;
    }
    char dn[256];
    size_t dn_size = sizeof(dn);
    if (gnutls_x509_crt_get_dn(client_cert, dn, &dn_size) == GNUTLS_E_SUCCESS) {
        printf("Client DN: %s\n", dn);
    }
    gnutls_x509_crt_deinit(client_cert);

    if (strcmp(method, "POST") != 0 ||
        (strcmp(url, "/move") != 0 && strcmp(url, "/telemetry") != 0))
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

    /* MongoDB insert */
    bson_error_t error;
    bson_t *doc = bson_new_from_json((uint8_t *)ci->data, -1, &error);
    if (!doc) {
        fprintf(stderr, "JSON error: %s\n", error.message);
        return MHD_NO;
    }

    char ts[64];
    get_utc_iso8601(ts, sizeof(ts));
    BSON_APPEND_UTF8(doc, "received_at", ts);

    /* Use client from pool (thread-safe; mongoc_client_t is NOT safe across threads) */
    mongoc_client_t *client = mongoc_client_pool_pop(mongo_pool);
    mongoc_collection_t *col =
        mongoc_client_get_collection(client, config.mongo_db, config.mongo_col);

    mongoc_collection_insert_one(col, doc, NULL, NULL, &error);
    mongoc_collection_destroy(col);
    mongoc_client_pool_push(mongo_pool, client);
    bson_destroy(doc);

    const char *response = "{\"status\":\"ok\"}";
    struct MHD_Response *resp =
        MHD_create_response_from_buffer(strlen(response),
                                         (void *)response,
                                         MHD_RESPMEM_PERSISTENT);

    int ret = MHD_queue_response(connection, MHD_HTTP_OK, resp);
    MHD_destroy_response(resp);

    free(ci->data);
    free(ci);
    *con_cls = NULL;

    return ret;
}

int main(void) {
    config.mongo_uri = getenv("MONGO_URI");
    if (!config.mongo_uri || !*config.mongo_uri)
        config.mongo_uri = DEFAULT_MONGO_URI;

    config.mongo_db = getenv("MONGO_DB");
    if (!config.mongo_db || !*config.mongo_db)
        config.mongo_db = DEFAULT_MONGO_DB;

    config.mongo_col = getenv("MONGO_COL");
    if (!config.mongo_col || !*config.mongo_col)
        config.mongo_col = DEFAULT_MONGO_COL;


    mongoc_init();
    mongoc_uri_t *uri = mongoc_uri_new(config.mongo_uri);
    if (!uri) {
        fprintf(stderr, "Invalid MongoDB URI: %s\n", config.mongo_uri);
        mongoc_cleanup();
        return 1;
    }
    mongo_pool = mongoc_client_pool_new(uri);
    mongoc_uri_destroy(uri);
    if (!mongo_pool) {
        fprintf(stderr, "Failed to create MongoDB client pool\n");
        mongoc_cleanup();
        return 1;
    }

	char *cert_pem = read_file(cert_file);
	char *key_pem  = read_file(key_file);
	char *ca_pem   = read_file(ca_file);
	if (!cert_pem || !key_pem) {
    	fprintf(stderr, "Failed to read cert/key files\n");
    	return 1;
	}
	if (!ca_pem) {
		fprintf(stderr, "Failed to read CA file (%s). Run: cd https/certs && ./gen_mtls_certs.sh\n", ca_file);
		free(cert_pem);
		free(key_pem);
		return 1;
	}

    /* mTLS: server proves identity (cert/key), server verifies client (CA) */
    struct MHD_Daemon *daemon = MHD_start_daemon(
        MHD_USE_THREAD_PER_CONNECTION | MHD_USE_TLS,
        DEFAULT_PORT,
        NULL, NULL,
        &handle_post, NULL,
        MHD_OPTION_HTTPS_MEM_CERT,
        cert_pem,
        MHD_OPTION_HTTPS_MEM_KEY,
        key_pem,
        MHD_OPTION_HTTPS_MEM_TRUST,
        ca_pem,
        MHD_OPTION_END);

    if (!daemon) {
        fprintf(stderr, "Failed to start HTTPS server\n");
        return 1;
    }

    printf("Listening on https://0.0.0.0:%d\n", DEFAULT_PORT);
    printf("Database backend: MongoDB\n");
    printf("MongoDB URI: %s\n", config.mongo_uri);
    printf("Database name: %s\n", config.mongo_db);
    printf("Collection: %s\n", config.mongo_col);
    printf("POST JSON to /move\n");
    getchar();

    MHD_stop_daemon(daemon);
    free(cert_pem);
    free(key_pem);
    free(ca_pem);
    mongoc_client_pool_destroy(mongo_pool);
    mongoc_cleanup();
    return 0;
}
