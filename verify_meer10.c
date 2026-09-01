/* Checks that meer10.h is the function the measurements were made with.
 *
 *   cc -O2 -o verify_meer10 verify_meer10.c && ./verify_meer10
 *
 * Three things are checked, and the third is the one that matters:
 *
 *   1. The known-answer vectors in meer10.h, which were read off the rig's
 *      feeder binary rather than computed by this header.
 *   2. That both mixers are bijective on a large sample. A fold is not
 *      guaranteed to be, and a collision here would be a real finding.
 *   3. That the header agrees with the rig, if the rig is there: run
 *        rrc/feeder.exe chain 0 0 0 3 8 5846dfed2f0e1d49 10 706 8 781f94b96e8edb3b > s.bin
 *      and pass s.bin as an argument. Every 64-bit little-endian word in
 *      that file must equal meer10(0), meer10(1), ... in order.
 *
 * Exit code 0 means every check that ran, passed. A skipped check is
 * reported as skipped and never counted as a pass.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "meer10.h"

static int kat(void) {
    int bad = 0;
    for (int i = 0; i < MEER10_KAT_COUNT; i++) {
        uint64_t got = meer10(meer10_kat_in[i]);
        if (got != meer10_kat_out[i]) {
            printf("  FAIL meer10(%016llx) = %016llx, expected %016llx\n",
                   (unsigned long long)meer10_kat_in[i],
                   (unsigned long long)got,
                   (unsigned long long)meer10_kat_out[i]);
            bad++;
        }
    }
    for (int i = 0; i < LU9_KAT_COUNT; i++) {
        uint64_t got = lu9(lu9_kat_in[i]);
        if (got != lu9_kat_out[i]) {
            printf("  FAIL lu9(%016llx) = %016llx, expected %016llx\n",
                   (unsigned long long)lu9_kat_in[i],
                   (unsigned long long)got,
                   (unsigned long long)lu9_kat_out[i]);
            bad++;
        }
    }
    printf("  known-answer vectors : %s (%d + %d checked)\n",
           bad ? "FAIL" : "ok", MEER10_KAT_COUNT, LU9_KAT_COUNT);
    return bad;
}

/* Birthday-style collision probe: hash a run of counters, sort, look for
   duplicates. 2^22 values is enough to catch a badly non-injective mixer
   and small enough to run in a second. */
static int cmp64(const void *a, const void *b) {
    uint64_t x = *(const uint64_t *)a, y = *(const uint64_t *)b;
    return (x > y) - (x < y);
}

static int injective_probe(uint64_t (*f)(uint64_t), const char *name) {
    const size_t n = 1u << 22;
    uint64_t *v = (uint64_t *)malloc(n * sizeof(uint64_t));
    if (!v) { printf("  %-20s : SKIPPED (out of memory)\n", name); return 0; }
    for (size_t i = 0; i < n; i++) v[i] = f((uint64_t)i);
    qsort(v, n, sizeof(uint64_t), cmp64);
    size_t dup = 0;
    for (size_t i = 1; i < n; i++) if (v[i] == v[i - 1]) dup++;
    free(v);
    printf("  %-20s : %s (%zu duplicates in 2^22 counter inputs)\n",
           name, dup ? "COLLISION" : "ok", dup);
    return dup != 0;
}

/* Compare against a raw stream written by the rig's feeder. */
static int against_stream(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) { printf("  against the rig      : SKIPPED (cannot open %s)\n", path); return 0; }
    uint64_t w; uint64_t i = 0; int bad = 0;
    while (fread(&w, 8, 1, f) == 1) {
        /* little-endian read; on a big-endian host this would need a swap,
           and the ladder has never run on one, so say so rather than guess */
        uint64_t want = meer10(i);
        if (w != want) {
            printf("  FAIL at word %llu: file %016llx, header %016llx\n",
                   (unsigned long long)i, (unsigned long long)w,
                   (unsigned long long)want);
            bad = 1; break;
        }
        i++;
    }
    fclose(f);
    if (!bad) printf("  against the rig      : ok (%llu words from %s)\n",
                     (unsigned long long)i, path);
    return bad;
}

int main(int argc, char **argv) {
    int bad = 0;
    printf("meer10.h -- verification\n");
    bad += kat();
    bad += injective_probe(meer10, "meer10 injective");
    bad += injective_probe(lu9, "lu9 injective");
    if (argc > 1) bad += against_stream(argv[1]);
    else printf("  against the rig      : SKIPPED (no stream file given)\n");
    printf("%s\n", bad ? "FAILED" : "all checks that ran, passed");
    return bad ? 1 : 0;
}
