/* DB-local observer source promoted for scoped PostgreSQL native build.
 * DB-local Linux only. No daemon, subprocess, network, clock adjustment or key.
 * Kernel NTP discipline is an observed source, not an automatically approved
 * trust root. Enrollment/profile/policy/host binding is enforced by SQL owner.
 */
#include "postgres.h"
#include "fmgr.h"
#include "utils/builtins.h"
#include "utils/jsonb.h"
#include "miscadmin.h"
#include <limits.h>
#ifdef __linux__
#include <time.h>
#include <sys/timex.h>
#include <unistd.h>
#include <fcntl.h>
#endif

PG_MODULE_MAGIC;
PG_FUNCTION_INFO_V1(r55_cp_clock_observe_local);

#ifdef __linux__
static int64
r55_ns(const struct timespec *t)
{
    if (t->tv_sec < 0 || t->tv_sec > LLONG_MAX / 1000000000LL ||
        t->tv_nsec < 0 || t->tv_nsec >= 1000000000L ||
        (int64)t->tv_sec * 1000000000LL > LLONG_MAX - t->tv_nsec)
        ereport(ERROR, (errmsg("R55_CLOCK_RANGE_INVALID")));
    return (int64)t->tv_sec * 1000000000LL + t->tv_nsec;
}
#endif

Datum
r55_cp_clock_observe_local(PG_FUNCTION_ARGS)
{
#ifndef __linux__
    ereport(ERROR, (errmsg("R55_CLOCK_PLATFORM_UNSUPPORTED")));
    PG_RETURN_NULL();
#else
    struct timespec before, utc, after;
    struct timex tx;
    int state, fd, i;
    ssize_t count;
    char boot[38];
    char *json;
    int64 bt0, bt1, wall;

    if (clock_gettime(CLOCK_BOOTTIME, &before) != 0 ||
        clock_gettime(CLOCK_REALTIME, &utc) != 0)
        ereport(ERROR, (errmsg("R55_CLOCK_OBSERVATION_FAILED")));
    memset(&tx, 0, sizeof(tx));
    tx.modes = 0; /* Query only. Never adjust kernel time. */
    state = adjtimex(&tx);
    if (state < 0 || tx.maxerror < 0 || tx.esterror < 0 || tx.tolerance < 0)
        ereport(ERROR, (errmsg("R55_CLOCK_DISCIPLINE_UNAVAILABLE")));
    fd = open("/proc/sys/kernel/random/boot_id", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0)
        ereport(ERROR, (errmsg("R55_CLOCK_BOOT_ID_UNAVAILABLE")));
    count = read(fd, boot, sizeof(boot));
    close(fd);
    if (count != 36 && count != 37)
        ereport(ERROR, (errmsg("R55_CLOCK_BOOT_ID_INVALID")));
    if (count == 37 && boot[36] != '\n')
        ereport(ERROR, (errmsg("R55_CLOCK_BOOT_ID_INVALID")));
    for (i = 0; i < 36; i++)
    {
        if (i == 8 || i == 13 || i == 18 || i == 23)
        {
            if (boot[i] != '-') ereport(ERROR, (errmsg("R55_CLOCK_BOOT_ID_INVALID")));
        }
        else if (!((boot[i] >= '0' && boot[i] <= '9') || (boot[i] >= 'a' && boot[i] <= 'f')))
            ereport(ERROR, (errmsg("R55_CLOCK_BOOT_ID_INVALID")));
    }
    boot[36] = '\0';
    if (clock_gettime(CLOCK_BOOTTIME, &after) != 0)
        ereport(ERROR, (errmsg("R55_CLOCK_OBSERVATION_FAILED")));
    bt0 = r55_ns(&before); bt1 = r55_ns(&after); wall = r55_ns(&utc);
    if (bt1 < bt0)
        ereport(ERROR, (errmsg("R55_CLOCK_BOOTTIME_REVERSED")));
    json = psprintf("{\"profile\":\"LINUX_ADJTIMEX_DB_LOCAL_V1\","
                    "\"host_boot_id\":\"%s\",\"backend_pid\":%d,"
                    "\"boottime_before_ns\":" INT64_FORMAT ","
                    "\"boottime_after_ns\":" INT64_FORMAT ","
                    "\"utc_ns\":" INT64_FORMAT ","
                    "\"maxerror_us\":%ld,\"esterror_us\":%ld,"
                    "\"tolerance_scaled_ppm\":%ld,\"kernel_status\":%d,"
                    "\"source_sync_state\":\"%s\"}",
                    boot, MyProcPid, bt0, bt1, wall,
                    tx.maxerror, tx.esterror, tx.tolerance, tx.status,
                    (state == TIME_OK && !(tx.status & STA_UNSYNC)) ? "SYNC" : "UNKNOWN");
    PG_RETURN_DATUM(DirectFunctionCall1(jsonb_in, CStringGetDatum(json)));
#endif
}
