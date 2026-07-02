/*
 *  Copyright (c) 2015 Adrien Vergé
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

#ifndef OPENFORTIVPN_COMPAT_WIN32_H
#define OPENFORTIVPN_COMPAT_WIN32_H

#ifdef _WIN32

#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <iphlpapi.h>
#include <io.h>
#include <process.h>

/* POSIX type compatibility */
#ifndef ssize_t
#ifdef _WIN64
typedef __int64 ssize_t;
#else
typedef int ssize_t;
#endif
#endif

#ifndef _PID_T_
#define _PID_T_
typedef int pid_t;
#endif
	typedef unsigned int uid_t;

/* File descriptor compatibility */
#define STDIN_FILENO  0
#define STDOUT_FILENO 1
#define STDERR_FILENO 2

/* Socket compatibility: Winsock uses closesocket/recv/send */
#define close_socket(s) closesocket(s)
#define sock_read(s, b, l) recv(s, (char *)(b), l, 0)
#define sock_write(s, b, l) send(s, (const char *)(b), l, 0)

/* Sleep compatibility */
#define sleep(s) Sleep((s) * 1000)
#define usleep(us) Sleep((us) / 1000)

/* Signal compatibility - minimal stubs */
#ifndef SIGPIPE
#define SIGPIPE 13
#endif
#ifndef SIGHUP
#define SIGHUP 1
#endif
#ifndef SIGTERM
#define SIGTERM 15
#endif
#ifndef SIGINT
#define SIGINT 2
#endif

/* Misc POSIX compatibility */
#define F_OK 0
#define access(path, mode) _access(path, mode)

static inline uid_t geteuid(void)
{
	/* On Windows, we check admin privileges differently */
	return 0; /* Always return 0 (root) - actual check done elsewhere */
}

/* Environment variable compatibility */
#define setenv(name, value, overwrite) _putenv_s(name, value)

/* Initialize Winsock - call once at startup */
static inline int winsock_init(void)
{
	WSADATA wsa_data;

	return WSAStartup(MAKEWORD(2, 2), &wsa_data);
}

static inline void winsock_cleanup(void)
{
	WSACleanup();
}

#else /* !_WIN32 */

/* On Unix, sockets are file descriptors */
#define close_socket(s) close(s)
#define sock_read(s, b, l) read(s, b, l)
#define sock_write(s, b, l) write(s, b, l)
#define winsock_init() 0
#define winsock_cleanup() ((void)0)

#endif /* _WIN32 */

#endif /* OPENFORTIVPN_COMPAT_WIN32_H */
