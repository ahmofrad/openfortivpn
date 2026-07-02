/*
 *  Unit tests for the TOTP / Base32 helpers.
 *
 *  Test vectors come from RFC 6238 Appendix B. The shared secret used there
 *  is the ASCII string "12345678901234567890", whose Base32 encoding is
 *  "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ".
 */

#include "totp.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

static int failures = 0;

static void check_str(const char *label, const char *got, const char *want)
{
	if (strcmp(got, want) == 0) {
		printf("ok   - %s: %s\n", label, got);
	} else {
		printf("FAIL - %s: got \"%s\", want \"%s\"\n", label, got, want);
		failures++;
	}
}

static void check_int(const char *label, int got, int want)
{
	if (got == want) {
		printf("ok   - %s: %d\n", label, got);
	} else {
		printf("FAIL - %s: got %d, want %d\n", label, got, want);
		failures++;
	}
}

static void test_base32_decode(void)
{
	uint8_t out[32];
	int n;

	/* ASCII "12345678901234567890" -> 20 bytes */
	n = base32_decode("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", out, sizeof(out));
	check_int("base32_decode(rfc secret) length", n, 20);
	if (n == 20)
		check_int("base32_decode(rfc secret) first byte", out[0], '1');

	/* lowercase + spaces + padding should be accepted */
	n = base32_decode("gezd gnbvgy3tqojq ==== ", out, sizeof(out));
	check_int("base32_decode(lowercase/spaces) length", n, 10);

	/* invalid character -> -1 */
	n = base32_decode("GEZD!GNBV", out, sizeof(out));
	check_int("base32_decode(invalid char) returns -1", n, -1);

	/* buffer too small -> -1 */
	n = base32_decode("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", out, 8);
	check_int("base32_decode(buf too small) returns -1", n, -1);

	/* empty string -> 0 bytes */
	n = base32_decode("", out, sizeof(out));
	check_int("base32_decode(empty) returns 0", n, 0);
}

static void test_totp_rfc6238(void)
{
	/*
	 * RFC 6238 Appendix B test vectors (6-digit truncation).
	 * Secret: ASCII "12345678901234567890"
	 *         Base32:  GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ
	 *
	 * Time (s)   Expected (8-digit)   Expected (6-digit)
	 * 59         94287082             287082
	 * 1111111109 07081804             081804
	 * 1111111111 14050471             050471
	 * 1234567890 89005924             005924
	 * 2000000000 69279037             279037
	 * 2000000000048156530             156530  (skipped: needs 64-bit)
	 */
	const char *seed = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ";
	char out[8];

	totp_generate_at(seed, 59, out, sizeof(out));
	check_str("totp(t=59)", out, "287082");

	totp_generate_at(seed, 1111111109, out, sizeof(out));
	check_str("totp(t=1111111109)", out, "081804");

	totp_generate_at(seed, 1111111111, out, sizeof(out));
	check_str("totp(t=1111111111)", out, "050471");

	totp_generate_at(seed, 1234567890, out, sizeof(out));
	check_str("totp(t=1234567890)", out, "005924");

	totp_generate_at(seed, 2000000000, out, sizeof(out));
	check_str("totp(t=2000000000)", out, "279037");
}

static void test_totp_errors(void)
{
	char out[8];

	/* invalid base32 seed */
	check_int("totp(bad seed) returns -1",
	          totp_generate_at("!!!notbase32!!!", 59, out, sizeof(out)), -1);

	/* buffer too small */
	check_int("totp(buf too small) returns -1",
	          totp_generate_at("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ",
	                           59, out, 3), -1);
}

int main(void)
{
	test_base32_decode();
	test_totp_rfc6238();
	test_totp_errors();

	if (failures == 0) {
		printf("\nAll TOTP tests passed.\n");
		return 0;
	}
	printf("\n%d TOTP test(s) FAILED.\n", failures);
	return 1;
}
