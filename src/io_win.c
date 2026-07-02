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
 *
 *  Windows I/O loop implementation.
 *  Replaces io.c for Windows builds, using wintun instead of pppd.
 */

#ifdef _WIN32

#include "tunnel.h"
#include "ppp.h"
#include "wintun.h"
#include "ssl.h"
#include "log.h"

#include <windows.h>
#include <pthread.h>

#include <assert.h>
#include <string.h>

#define PKT_BUF_SZ 0x1000

/* Windows semaphore abstraction (matching io.c pattern) */
typedef HANDLE os_semaphore_t;
#define SEM_INIT(sem, x, value) (*(sem) = CreateSemaphore(NULL, value, LONG_MAX, NULL))
#define SEM_WAIT(sem)           WaitForSingleObject(*(sem), INFINITE)
#define SEM_POST(sem)           ReleaseSemaphore(*(sem), 1, NULL)
#define SEM_DESTROY(sem)        CloseHandle(*(sem))

static os_semaphore_t sem_ppp_ready;
static os_semaphore_t sem_if_config;
static os_semaphore_t sem_stop_io;

/* Global variable to pass signal out of its handler */
volatile long sig_received;

int get_sig_received(void)
{
	return (int)sig_received;
}

/* Console ctrl handler replaces Unix signal handler */
static BOOL WINAPI win_ctrl_handler(DWORD ctrl_type)
{
	if (ctrl_type == CTRL_C_EVENT || ctrl_type == CTRL_BREAK_EVENT ||
	    ctrl_type == CTRL_CLOSE_EVENT) {
		InterlockedExchange(&sig_received, SIGTERM);
		SEM_POST(&sem_stop_io);
		return TRUE;
	}
	return FALSE;
}

/*
 * Packet pool operations (same as io.c).
 */
static void pool_push(struct ppp_packet_pool *pool, struct ppp_packet *new)
{
	struct ppp_packet *current;

	pthread_mutex_lock(&pool->mutex);

	new->next = NULL;
	current = pool->list_head;
	if (current == NULL) {
		pool->list_head = new;
	} else {
		while (current->next != NULL)
			current = current->next;
		current->next = new;
	}

	pthread_cond_signal(&pool->new_data);
	pthread_mutex_unlock(&pool->mutex);
}

static struct ppp_packet *pool_pop(struct ppp_packet_pool *pool)
{
	struct ppp_packet *packet;

	pthread_mutex_lock(&pool->mutex);
	while (pool->list_head == NULL)
		pthread_cond_wait(&pool->new_data, &pool->mutex);
	packet = pool->list_head;
	pool->list_head = packet->next;
	pthread_mutex_unlock(&pool->mutex);

	return packet;
}

/*
 * Thread: Read packets from TLS socket, process through PPP state machine.
 * During negotiation: generates PPP responses sent via ssl_write.
 * After negotiation: extracts IP packets pushed to ssl_to_pty_pool (reused as tun pool).
 */
static void *ssl_read_thread(void *arg)
{
	struct tunnel *tunnel = (struct tunnel *)arg;
	struct ppp_context *ppp_ctx = (struct ppp_context *)tunnel->ppp_ctx;

	log_debug("%s thread\n", __func__);

	while (1) {
		uint8_t header[6];
		uint16_t total, magic, size;
		int ret;
		struct ppp_packet *packet;
		uint8_t *response, *ip_payload;
		size_t resp_len, ip_len;
		int ppp_ret;

		ret = safe_ssl_read_all(tunnel->ssl_handle, header, 6);
		if (ret < 0) {
			log_debug("Error reading from TLS (%s).\n",
			          err_ssl_str(ret));
			break;
		}

		total = (header[0] << 8) | header[1];
		magic = (header[2] << 8) | header[3];
		size  = (header[4] << 8) | header[5];

		if (magic != 0x5050) {
			log_debug("Bad magic: 0x%04x\n", magic);
			break;
		}

		if (size == 0)
			continue;

		packet = malloc(sizeof(*packet) + 6 + size);
		if (!packet) {
			log_error("malloc failed\n");
			break;
		}
		packet->len = size;

		/* Read the PPP payload */
		ret = safe_ssl_read_all(tunnel->ssl_handle,
		                        pkt_data(packet), size);
		if (ret < 0) {
			log_debug("Error reading PPP data (%s).\n",
			          err_ssl_str(ret));
			free(packet);
			break;
		}

		log_debug("gateway ---> tun (%u bytes)\n", size);

		/* Process through PPP state machine */
		ppp_ret = ppp_process_incoming(ppp_ctx,
		                               pkt_data(packet), size,
		                               &response, &resp_len,
		                               &ip_payload, &ip_len);

		if (ppp_ret == PPP_RET_IP_PACKET) {
			/*
			 * IP data packet: push to ssl_to_pty_pool
			 * (reused as TUN write pool on Windows).
			 * Repackage ip_payload into a ppp_packet.
			 */
			struct ppp_packet *ip_pkt;

			ip_pkt = malloc(sizeof(*ip_pkt) + 6 + ip_len);
			if (ip_pkt) {
				ip_pkt->len = ip_len;
				memcpy(pkt_data(ip_pkt), ip_payload, ip_len);
				pool_push(&tunnel->ssl_to_pty_pool, ip_pkt);
			}
			free(ip_payload);
		} else if (ppp_ret == PPP_RET_NEGOTIATE) {
			/* IPCP negotiation complete - signal if_config thread */
			SEM_POST(&sem_if_config);
		} else if (ppp_ret == PPP_RET_TERMINATED) {
			free(response);
			free(packet);
			break;
		}

		/* If there's a PPP response, send it via the ssl_write path */
		if (response) {
			struct ppp_packet *resp_pkt;

			resp_pkt = malloc(sizeof(*resp_pkt) + 6 + resp_len);
			if (resp_pkt) {
				resp_pkt->len = resp_len;
				memcpy(pkt_data(resp_pkt), response, resp_len);
				pool_push(&tunnel->pty_to_ssl_pool, resp_pkt);
			}
			free(response);
		}

		free(packet);
	}

	SEM_POST(&sem_stop_io);
	return NULL;
}

/*
 * Thread: Pop PPP packets from pty_to_ssl_pool and write them to the TLS socket.
 * Same as Unix ssl_write thread.
 */
static void *ssl_write_thread(void *arg)
{
	struct tunnel *tunnel = (struct tunnel *)arg;

	log_debug("%s thread\n", __func__);

	while (1) {
		struct ppp_packet *packet;
		int ret;

		packet = pool_pop(&tunnel->pty_to_ssl_pool);

		/* Build the 6-byte Fortinet header */
		pkt_header(packet)[0] = (6 + packet->len) >> 8;
		pkt_header(packet)[1] = (6 + packet->len) & 0xff;
		pkt_header(packet)[2] = 0x50;
		pkt_header(packet)[3] = 0x50;
		pkt_header(packet)[4] = packet->len >> 8;
		pkt_header(packet)[5] = packet->len & 0xff;

		do {
			ret = safe_ssl_write(tunnel->ssl_handle,
			                     packet->content, 6 + packet->len);
		} while (ret == 0);

		if (ret < 0) {
			log_debug("Error writing to TLS (%s).\n",
			          err_ssl_str(ret));
			free(packet);
			break;
		}
		free(packet);
	}

	SEM_POST(&sem_stop_io);
	return NULL;
}

/*
 * Thread: Read IP packets from the wintun TUN adapter,
 * encapsulate in PPP, and push to pty_to_ssl_pool.
 */
static void *tun_read_thread(void *arg)
{
	struct tunnel *tunnel = (struct tunnel *)arg;
	WINTUN_SESSION_HANDLE session = (WINTUN_SESSION_HANDLE)tunnel->tun_session;
	struct wintun_api *api = (struct wintun_api *)tunnel->tun_adapter;

	/* Wait for PPP negotiation to complete */
	SEM_WAIT(&sem_ppp_ready);

	log_debug("%s thread\n", __func__);

	HANDLE read_event = api->GetReadWaitEvent(session);

	while (1) {
		DWORD pkt_size;
		BYTE *pkt;

		/* Wait for a packet to be available */
		WaitForSingleObject(read_event, INFINITE);

		while ((pkt = api->ReceivePacket(session, &pkt_size)) != NULL) {
			uint8_t *ppp_data;
			size_t ppp_len;
			struct ppp_packet *packet;

			/* Encapsulate IP in PPP */
			if (ppp_encapsulate_ip(pkt, pkt_size,
			                       &ppp_data, &ppp_len) == 0) {
				packet = malloc(sizeof(*packet) + 6 + ppp_len);
				if (packet) {
					packet->len = ppp_len;
					memcpy(pkt_data(packet), ppp_data, ppp_len);
					pool_push(&tunnel->pty_to_ssl_pool, packet);
					log_debug("tun ---> gateway (%lu bytes)\n",
					          (unsigned long)ppp_len);
				}
				free(ppp_data);
			}

			api->ReleaseReceivePacket(session, pkt);
		}
	}

	SEM_POST(&sem_stop_io);
	return NULL;
}

/*
 * Thread: Pop IP packets from ssl_to_pty_pool and write to wintun adapter.
 */
static void *tun_write_thread(void *arg)
{
	struct tunnel *tunnel = (struct tunnel *)arg;
	WINTUN_SESSION_HANDLE session = (WINTUN_SESSION_HANDLE)tunnel->tun_session;
	struct wintun_api *api = (struct wintun_api *)tunnel->tun_adapter;

	/* Wait for PPP negotiation to complete */
	SEM_WAIT(&sem_ppp_ready);

	log_debug("%s thread\n", __func__);

	while (1) {
		struct ppp_packet *packet;
		BYTE *buf;

		packet = pool_pop(&tunnel->ssl_to_pty_pool);

		buf = api->AllocateSendPacket(session, (DWORD)packet->len);
		if (buf) {
			memcpy(buf, pkt_data(packet), packet->len);
			api->SendPacket(session, buf);
			log_debug("gateway ---> tun write (%lu bytes)\n",
			          (unsigned long)packet->len);
		} else {
			log_error("Failed to allocate wintun send packet\n");
		}

		free(packet);
	}

	SEM_POST(&sem_stop_io);
	return NULL;
}

/*
 * Thread: Wait for PPP negotiation to complete, then configure the interface.
 */
static void *if_config_thread(void *arg)
{
	struct tunnel *tunnel = (struct tunnel *)arg;
	int timeout = 60000; /* 60 seconds in ms */

	log_debug("%s thread\n", __func__);

	/* Wait for IPCP negotiation to complete */
	SEM_WAIT(&sem_if_config);

	/* Signal tun_read and tun_write that PPP is ready */
	SEM_POST(&sem_ppp_ready);
	SEM_POST(&sem_ppp_ready); /* Post twice for two waiting threads */

	/* Wait for the TUN interface to be up */
	while (timeout > 0) {
		if (ppp_interface_is_up(tunnel)) {
			if (tunnel->on_ppp_if_up != NULL)
				if (tunnel->on_ppp_if_up(tunnel))
					goto error;
			tunnel->state = STATE_UP;
			break;
		}
		Sleep(200);
		timeout -= 200;
	}

	if (tunnel->state != STATE_UP) {
		log_error("Timed out waiting for TUN interface to be UP.\n");
		goto error;
	}

	return NULL;
error:
	SEM_POST(&sem_stop_io);
	return NULL;
}

int io_loop(struct tunnel *tunnel)
{
	int tcp_nodelay_flag = 1;
	int ret = 0;
	int fatal = 0;

	pthread_t tun_read_thr;
	pthread_t tun_write_thr;
	pthread_t ssl_read_thr;
	pthread_t ssl_write_thr;
	pthread_t if_config_thr;

	SEM_INIT(&sem_ppp_ready, 0, 0);
	SEM_INIT(&sem_if_config, 0, 0);
	SEM_INIT(&sem_stop_io, 0, 0);

	init_ppp_packet_pool(&tunnel->ssl_to_pty_pool);
	init_ppp_packet_pool(&tunnel->pty_to_ssl_pool);

	/* Set TCP_NODELAY for better performance */
	if (setsockopt(tunnel->ssl_socket, IPPROTO_TCP, TCP_NODELAY,
	               (const char *)&tcp_nodelay_flag, sizeof(int))) {
		log_error("setsockopt TCP_NODELAY: %d\n", WSAGetLastError());
		goto err_sockopt;
	}

	/* Set console ctrl handler */
	SetConsoleCtrlHandler(win_ctrl_handler, TRUE);

	/* Start PPP negotiation */
	{
		struct ppp_context *ppp_ctx =
		        (struct ppp_context *)tunnel->ppp_ctx;
		uint8_t *start_pkt;
		size_t start_len;

		if (ppp_start_negotiation(ppp_ctx, &start_pkt, &start_len) == 0) {
			struct ppp_packet *pkt;

			pkt = malloc(sizeof(*pkt) + 6 + start_len);
			if (pkt) {
				pkt->len = start_len;
				memcpy(pkt_data(pkt), start_pkt, start_len);
				pool_push(&tunnel->pty_to_ssl_pool, pkt);
			}
			free(start_pkt);
		}
	}

	/* Create all worker threads */
	ret = pthread_create(&ssl_read_thr, NULL, ssl_read_thread, tunnel);
	if (ret != 0) {
		log_debug("Error creating ssl_read thread: %d\n", ret);
		goto err_thread;
	}

	ret = pthread_create(&ssl_write_thr, NULL, ssl_write_thread, tunnel);
	if (ret != 0) {
		log_debug("Error creating ssl_write thread: %d\n", ret);
		goto err_thread;
	}

	ret = pthread_create(&tun_read_thr, NULL, tun_read_thread, tunnel);
	if (ret != 0) {
		log_debug("Error creating tun_read thread: %d\n", ret);
		goto err_thread;
	}

	ret = pthread_create(&tun_write_thr, NULL, tun_write_thread, tunnel);
	if (ret != 0) {
		log_debug("Error creating tun_write thread: %d\n", ret);
		goto err_thread;
	}

	ret = pthread_create(&if_config_thr, NULL, if_config_thread, tunnel);
	if (ret != 0) {
		log_debug("Error creating if_config thread: %d\n", ret);
		goto err_thread;
	}

	/* Wait for termination signal */
	SEM_WAIT(&sem_stop_io);

	log_info("Cancelling threads...\n");
	pthread_cancel(tun_read_thr);
	pthread_cancel(tun_write_thr);
	pthread_cancel(ssl_read_thr);
	pthread_cancel(ssl_write_thr);
	pthread_cancel(if_config_thr);

	pthread_join(tun_read_thr, NULL);
	pthread_join(tun_write_thr, NULL);
	pthread_join(ssl_read_thr, NULL);
	pthread_join(ssl_write_thr, NULL);
	pthread_join(if_config_thr, NULL);

err_thread:
err_signal:
err_sockopt:
	destroy_ppp_packet_pool(&tunnel->ssl_to_pty_pool);
	destroy_ppp_packet_pool(&tunnel->pty_to_ssl_pool);

	SEM_DESTROY(&sem_ppp_ready);
	SEM_DESTROY(&sem_if_config);
	SEM_DESTROY(&sem_stop_io);

	SetConsoleCtrlHandler(win_ctrl_handler, FALSE);

	return fatal ? 1 : 0;
}

#endif /* _WIN32 */
