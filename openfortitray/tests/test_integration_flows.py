"""Integration tests: feed recorded real openfortivpn output sequences
through the state machine and assert correct transitions.

The recorded sequences come from actual openfortivpn 1.24.1/1.26.0
output on Windows (wintun) builds.
"""

from openfortitray.core.state_machine import ConnectionState, StateMachine


def _run(sm: StateMachine, lines: list[str]) -> None:
    for line in lines:
        sm.on_log_line(line)


# ── Recorded sequences ──────────────────────────────────────────

WINDOWS_SUCCESS_FLOW = [
    "DEBUG:  openfortivpn 1.24.1",
    "DEBUG:  revision 1.24.1",
    "DEBUG:  Loaded configuration file \"C:\\Users\\...\\conf.conf\".",
    "DEBUG:  Configuration host = \"ict-hq1.snapp.cab\"",
    "DEBUG:  Resolving gateway host ip",
    "INFO:   Gateway IP: 79.127.120.184",
    "DEBUG:  Establishing TLS connection",
    "INFO:   Connected to gateway.",
    "INFO:   Authenticated.",
    "INFO:   Remote gateway has allocated a VPN.",
    "DEBUG:  Retrieving configuration",
    "INFO:   Adding split route: 172.31.252.128/255.255.255.128 via 172.24.4.1",
    "DEBUG:  Creating wintun adapter",
    "INFO:   Loaded wintun.dll (driver version 0.14)",
    "INFO:   Wintun adapter created.",
    "DEBUG:  Switch to tunneling mode",
    "DEBUG:  Starting IO through the tunnel",
    "INFO:   Tunnel interface is UP.",
    "INFO:   Assigned IP: 172.24.4.1",
]

WINDOWS_DISCONNECT_FLOW = [
    "INFO:   Cancelling threads...",
    "INFO:   Destroyed wintun adapter.",
    "INFO:   Closed connection to gateway.",
    "INFO:   Logged out.",
]

AUTH_FAILURE_FLOW = [
    "DEBUG:  openfortivpn 1.24.1",
    "DEBUG:  Resolving gateway host ip",
    "INFO:   Gateway IP: 79.127.120.184",
    "DEBUG:  Establishing TLS connection",
    "INFO:   Connected to gateway.",
    "ERROR:  Authentication failed",
]

OTP_PROMPT_FLOW = [
    "INFO:   Gateway IP: 79.127.120.184",
    "INFO:   Connected to gateway.",
    "Please enter one-time password: ",
]

UNIX_SUCCESS_FLOW = [
    "INFO:   Connected to gateway.",
    "INFO:   Authenticated.",
    "INFO:   Remote gateway has allocated a VPN.",
    "INFO:   Tunnel is up and running.",
]


# ── Tests ───────────────────────────────────────────────────────

def test_windows_full_connect_flow():
    sm = StateMachine()
    sm.on_connect_requested()
    _run(sm, WINDOWS_SUCCESS_FLOW)
    assert sm.state == ConnectionState.CONNECTED


def test_unix_full_connect_flow():
    sm = StateMachine()
    sm.on_connect_requested()
    _run(sm, UNIX_SUCCESS_FLOW)
    assert sm.state == ConnectionState.CONNECTED


def test_disconnect_after_connect():
    sm = StateMachine()
    sm.on_connect_requested()
    _run(sm, WINDOWS_SUCCESS_FLOW)
    assert sm.state == ConnectionState.CONNECTED
    _run(sm, WINDOWS_DISCONNECT_FLOW)
    assert sm.state == ConnectionState.DISCONNECTED


def test_auth_failure_is_terminal():
    sm = StateMachine()
    sm.on_connect_requested()
    _run(sm, AUTH_FAILURE_FLOW)
    assert sm.state == ConnectionState.AUTH_ERROR
    assert sm.is_error
    assert not sm.should_retry


def test_otp_prompt_does_not_change_state():
    """OTP prompt lines should not break the connecting state."""
    sm = StateMachine()
    sm.on_connect_requested()
    _run(sm, OTP_PROMPT_FLOW)
    assert sm.state == ConnectionState.CONNECTING


def test_connected_then_process_dies():
    sm = StateMachine()
    sm.on_connect_requested()
    _run(sm, WINDOWS_SUCCESS_FLOW)
    sm.on_process_exit(1)
    assert sm.state == ConnectionState.ERROR
    assert sm.should_retry  # network-level, safe to retry next host


def test_auth_error_then_process_dies():
    sm = StateMachine()
    sm.on_connect_requested()
    _run(sm, AUTH_FAILURE_FLOW)
    sm.on_process_exit(1)
    assert sm.state == ConnectionState.AUTH_ERROR
    assert not sm.should_retry  # don't retry wrong password


def test_permission_error_windows():
    sm = StateMachine()
    sm.on_connect_requested()
    sm.on_log_line("ERROR: This process requires administrator privileges.")
    assert sm.state == ConnectionState.PERMISSION_ERROR
    assert not sm.should_retry


def test_permission_error_posix():
    sm = StateMachine()
    sm.on_connect_requested()
    sm.on_log_line(
        "This process was not spawned with root privileges, which are required."
    )
    assert sm.state == ConnectionState.PERMISSION_ERROR


def test_negotiation_complete_counts_as_connected():
    """Some gateway flows end with Negotiation complete instead of UP."""
    sm = StateMachine()
    sm.on_connect_requested()
    sm.on_log_line("INFO:   Negotiation complete.")
    assert sm.state == ConnectionState.CONNECTED


def test_multi_host_fallback_scenario():
    """Simulates host1 failing, then host2 succeeding."""
    sm = StateMachine()

    # Attempt 1: fails to even reach gateway
    sm.on_connect_requested()
    sm.on_log_line("ERROR:  Could not resolve host: bad-host.example.com")
    sm.on_process_exit(-1)
    assert sm.state == ConnectionState.ERROR

    # Attempt 2 (GUI calls on_connect_requested again for next host)
    sm.on_connect_requested()
    _run(sm, WINDOWS_SUCCESS_FLOW)
    assert sm.state == ConnectionState.CONNECTED


def test_progress_messages_keep_connecting_state():
    sm = StateMachine()
    sm.on_connect_requested()
    _run(sm, [
        "INFO:   Connected to gateway.",
        "INFO:   Authenticated.",
        "INFO:   Remote gateway has allocated a VPN.",
    ])
    assert sm.state == ConnectionState.CONNECTING
