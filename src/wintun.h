/*
 * Wintun API declarations for dynamic loading.
 * Based on the Wintun API (https://www.wintun.net/).
 * The actual wintun.dll is loaded at runtime via LoadLibrary.
 *
 * Wintun is licensed under the MIT license.
 */

#ifndef OPENFORTIVPN_WINTUN_H
#define OPENFORTIVPN_WINTUN_H

#ifdef _WIN32

#include <windows.h>
#include <ipexport.h>
#include <ifdef.h>

typedef void *WINTUN_ADAPTER_HANDLE;
typedef void *WINTUN_SESSION_HANDLE;

typedef WINTUN_ADAPTER_HANDLE (WINAPI *WINTUN_CREATE_ADAPTER_FUNC)(
        const WCHAR *Name, const WCHAR *TunnelType,
        const GUID *RequestedGUID);

typedef void (WINAPI *WINTUN_CLOSE_ADAPTER_FUNC)(
        WINTUN_ADAPTER_HANDLE Adapter);

typedef WINTUN_SESSION_HANDLE (WINAPI *WINTUN_START_SESSION_FUNC)(
        WINTUN_ADAPTER_HANDLE Adapter, DWORD Capacity);

typedef void (WINAPI *WINTUN_END_SESSION_FUNC)(
        WINTUN_SESSION_HANDLE Session);

typedef HANDLE (WINAPI *WINTUN_GET_READ_WAIT_EVENT_FUNC)(
        WINTUN_SESSION_HANDLE Session);

typedef BYTE *(WINAPI *WINTUN_RECEIVE_PACKET_FUNC)(
        WINTUN_SESSION_HANDLE Session, DWORD *PacketSize);

typedef void (WINAPI *WINTUN_RELEASE_RECEIVE_PACKET_FUNC)(
        WINTUN_SESSION_HANDLE Session, const BYTE *Packet);

typedef BYTE *(WINAPI *WINTUN_ALLOCATE_SEND_PACKET_FUNC)(
        WINTUN_SESSION_HANDLE Session, DWORD PacketSize);

typedef void (WINAPI *WINTUN_SEND_PACKET_FUNC)(
        WINTUN_SESSION_HANDLE Session, const BYTE *Packet);

typedef void (WINAPI *WINTUN_GET_ADAPTER_LUID_FUNC)(
        WINTUN_ADAPTER_HANDLE Adapter, NET_LUID *Luid);

typedef DWORD (WINAPI *WINTUN_GET_RUNNING_DRIVER_VERSION_FUNC)(void);

/* Function pointer table loaded from wintun.dll */
struct wintun_api {
	HMODULE module;
	WINTUN_CREATE_ADAPTER_FUNC CreateAdapter;
	WINTUN_CLOSE_ADAPTER_FUNC CloseAdapter;
	WINTUN_START_SESSION_FUNC StartSession;
	WINTUN_END_SESSION_FUNC EndSession;
	WINTUN_GET_READ_WAIT_EVENT_FUNC GetReadWaitEvent;
	WINTUN_RECEIVE_PACKET_FUNC ReceivePacket;
	WINTUN_RELEASE_RECEIVE_PACKET_FUNC ReleaseReceivePacket;
	WINTUN_ALLOCATE_SEND_PACKET_FUNC AllocateSendPacket;
	WINTUN_SEND_PACKET_FUNC SendPacket;
	WINTUN_GET_ADAPTER_LUID_FUNC GetAdapterLUID;
	WINTUN_GET_RUNNING_DRIVER_VERSION_FUNC GetRunningDriverVersion;
};

/*
 * Load wintun.dll and resolve all function pointers.
 * Returns 0 on success, -1 on failure.
 */
static inline int wintun_load(struct wintun_api *api)
{
	HMODULE mod = LoadLibraryW(L"wintun.dll");

	if (!mod)
		return -1;

	api->module = mod;

#define LOAD_FUNC(field, name) \
	do { \
		api->field = (WINTUN_##name##_FUNC) \
			GetProcAddress(mod, "Wintun" #field); \
		if (!api->field) { \
			FreeLibrary(mod); \
			return -1; \
		} \
	} while (0)

	LOAD_FUNC(CreateAdapter, CREATE_ADAPTER);
	LOAD_FUNC(CloseAdapter, CLOSE_ADAPTER);
	LOAD_FUNC(StartSession, START_SESSION);
	LOAD_FUNC(EndSession, END_SESSION);
	LOAD_FUNC(GetReadWaitEvent, GET_READ_WAIT_EVENT);
	LOAD_FUNC(ReceivePacket, RECEIVE_PACKET);
	LOAD_FUNC(ReleaseReceivePacket, RELEASE_RECEIVE_PACKET);
	LOAD_FUNC(AllocateSendPacket, ALLOCATE_SEND_PACKET);
	LOAD_FUNC(SendPacket, SEND_PACKET);
	LOAD_FUNC(GetAdapterLUID, GET_ADAPTER_LUID);
	LOAD_FUNC(GetRunningDriverVersion, GET_RUNNING_DRIVER_VERSION);

#undef LOAD_FUNC

	return 0;
}

static inline void wintun_unload(struct wintun_api *api)
{
	if (api->module) {
		FreeLibrary(api->module);
		api->module = NULL;
	}
}

#endif /* _WIN32 */

#endif /* OPENFORTIVPN_WINTUN_H */
