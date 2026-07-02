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

#ifndef OPENFORTIVPN_TOTP_H
#define OPENFORTIVPN_TOTP_H

#include <stddef.h>
#include <stdint.h>

/*
 * Decode an RFC 4648 Base32 string into a byte buffer.
 *
 * Accepts upper- and lower-case letters, digits 2-7, and ignores spaces,
 * hyphens, and '=' padding characters. Any other character makes the input
 * invalid and -1 is returned.
 *
 * Returns the number of bytes written on success, or -1 on error (invalid
 * character or output buffer too small).
 */
int base32_decode(const char *in, uint8_t *out, size_t outlen);

/*
 * Generate a 6-digit TOTP value (RFC 6238) at the current time.
 *
 * Parameters are fixed to the values used by FortiToken Mobile and other
 * common authenticator apps: HMAC-SHA1, 30-second time step, T0 = 0,
 * 6 digits.
 *
 * @param base32_seed  NUL-terminated Base32-encoded secret.
 * @param out          Destination buffer; at least 7 bytes.
 * @param outlen       Size of the destination buffer.
 *
 * Returns 0 on success, -1 on error (invalid seed or buffer too small).
 * The output is a NUL-terminated string of 6 ASCII digits.
 */
int totp_generate(const char *base32_seed, char *out, size_t outlen);

/*
 * Like totp_generate(), but for an explicit time (mainly for testing).
 */
int totp_generate_at(const char *base32_seed, int64_t now,
                     char *out, size_t outlen);

/*
 * Resolve a seed specification into a heap-allocated Base32 string.
 *
 * If @spec starts with "env:", the remainder is interpreted as the name of
 * an environment variable whose value holds the Base32 seed. Otherwise @spec
 * is taken literally as the Base32 seed.
 *
 * Returns a newly malloc()'d string on success (caller frees), or NULL on
 * error.
 */
char *resolve_otp_seed(const char *spec);

/*
 * Read the first non-empty line of a file and return it as a heap-allocated
 * string with leading/trailing whitespace (including the newline) removed.
 *
 * Returns NULL on error or if the file contains no non-whitespace content.
 */
char *read_otp_seed_file(const char *path);

#endif
