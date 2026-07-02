/*
 *  TOTP (RFC 6238) and Base32 (RFC 4648) helpers.
 *
 *  This program is free software: you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License as published by
 *  the Free Software Foundation, either version 3 of the License, or
 *  (at your option) any later version.
 *
 *  This program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License
 *  along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

#include "totp.h"
#include "log.h"

#include <openssl/hmac.h>
#include <openssl/crypto.h>

#include <ctype.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifdef _WIN32
#include "compat_win32.h"
#else
#include <unistd.h>
#endif

static const int8_t b32tab[256] = {
	['A'] = 0,  ['B'] = 1,  ['C'] = 2,  ['D'] = 3,
	['E'] = 4,  ['F'] = 5,  ['G'] = 6,  ['H'] = 7,
	['I'] = 8,  ['J'] = 9,  ['K'] = 10, ['L'] = 11,
	['M'] = 12, ['N'] = 13, ['O'] = 14, ['P'] = 15,
	['Q'] = 16, ['R'] = 17, ['S'] = 18, ['T'] = 19,
	['U'] = 20, ['V'] = 21, ['W'] = 22, ['X'] = 23,
	['Y'] = 24, ['Z'] = 25,
	['2'] = 26, ['3'] = 27, ['4'] = 28, ['5'] = 29,
	['6'] = 30, ['7'] = 31,
	/* lowercase aliases */
	['a'] = 0,  ['b'] = 1,  ['c'] = 2,  ['d'] = 3,
	['e'] = 4,  ['f'] = 5,  ['g'] = 6,  ['h'] = 7,
	['i'] = 8,  ['j'] = 9,  ['k'] = 10, ['l'] = 11,
	['m'] = 12, ['n'] = 13, ['o'] = 14, ['p'] = 15,
	['q'] = 16, ['r'] = 17, ['s'] = 18, ['t'] = 19,
	['u'] = 20, ['v'] = 21, ['w'] = 22, ['x'] = 23,
	['y'] = 24, ['z'] = 25,
};

int base32_decode(const char *in, uint8_t *out, size_t outlen)
{
	uint32_t buffer = 0;
	int bits = 0;
	size_t written = 0;

	if (in == NULL || out == NULL)
		return -1;

	for (; *in != '\0'; in++) {
		unsigned char c = (unsigned char)*in;

		/* skip whitespace, hyphens and padding */
		if (c == ' ' || c == '\t' || c == '\r' || c == '\n' ||
		    c == '-' || c == '=')
			continue;

		if (b32tab[c] == 0 && c != 'A' && c != 'a')
			return -1;

		buffer = (buffer << 5) | (uint32_t)b32tab[c];
		bits += 5;

		if (bits >= 8) {
			bits -= 8;
			if (written >= outlen)
				return -1;
			out[written++] = (uint8_t)((buffer >> bits) & 0xff);
		}
	}

	return (int)written;
}

static int totp_generate_at_impl(const char *base32_seed, int64_t now,
                                 char *out, size_t outlen)
{
	uint8_t key[64];
	int keylen;
	uint64_t counter;
	uint8_t counter_be[8];
	unsigned char md[EVP_MAX_MD_SIZE];
	unsigned int md_len = 0;
	uint32_t offset, code;

	if (base32_seed == NULL || out == NULL)
		return -1;
	if (outlen < 7)
		return -1;

	keylen = base32_decode(base32_seed, key, sizeof(key));
	if (keylen <= 0) {
		log_error("otp-seed is not valid Base32.\n");
		return -1;
	}

	counter = (uint64_t)(now / 30);
	for (int i = 7; i >= 0; i--) {
		counter_be[i] = (uint8_t)(counter & 0xff);
		counter >>= 8;
	}

	if (HMAC(EVP_sha1(), key, keylen, counter_be, 8, md, &md_len) == NULL
	    || md_len < 20) {
		OPENSSL_cleanse(key, (size_t)keylen);
		log_error("HMAC-SHA1 failed while generating TOTP.\n");
		return -1;
	}

	OPENSSL_cleanse(key, (size_t)keylen);

	offset = md[19] & 0x0f;
	code = ((uint32_t)(md[offset] & 0x7f) << 24) |
	       ((uint32_t)md[offset + 1] << 16) |
	       ((uint32_t)md[offset + 2] << 8) |
	       ((uint32_t)md[offset + 3]);
	code %= 1000000;

	snprintf(out, outlen, "%06u", code);
	return 0;
}

int totp_generate_at(const char *base32_seed, int64_t now,
                     char *out, size_t outlen)
{
	return totp_generate_at_impl(base32_seed, now, out, outlen);
}

int totp_generate(const char *base32_seed, char *out, size_t outlen)
{
	return totp_generate_at_impl(base32_seed, (int64_t)time(NULL),
	                             out, outlen);
}

char *resolve_otp_seed(const char *spec)
{
	const char *prefix = "env:";
	size_t plen = strlen(prefix);

	if (spec == NULL)
		return NULL;

	if (strncmp(spec, prefix, plen) == 0) {
		const char *var = spec + plen;
		char *val;

		if (var[0] == '\0') {
			log_error("otp-seed: missing variable name after 'env:'.\n");
			return NULL;
		}
		val = getenv(var);
		if (val == NULL || val[0] == '\0') {
			log_error("otp-seed: environment variable '%s' is not set or empty.\n",
			          var);
			return NULL;
		}
		return strdup(val);
	}

	return strdup(spec);
}

char *read_otp_seed_file(const char *path)
{
	FILE *f;
	char line[256];
	char *p, *end;
	char *result;

	if (path == NULL)
		return NULL;

	f = fopen(path, "r");
	if (f == NULL) {
		log_error("otp-seed-file: cannot open '%s': %s\n",
		          path, strerror(errno));
		return NULL;
	}

	result = NULL;
	while (fgets(line, sizeof(line), f) != NULL) {
		/* trim leading whitespace */
		p = line;
		while (*p == ' ' || *p == '\t')
			p++;
		if (*p == '\0' || *p == '\n' || *p == '\r')
			continue;
		/* trim trailing whitespace */
		end = p + strlen(p);
		while (end > p && (end[-1] == '\n' || end[-1] == '\r' ||
		                   end[-1] == ' ' || end[-1] == '\t'))
			*--end = '\0';
		if (*p == '\0')
			continue;
		result = strdup(p);
		break;
	}

	fclose(f);
	if (result == NULL)
		log_error("otp-seed-file: '%s' contains no seed.\n", path);
	return result;
}
