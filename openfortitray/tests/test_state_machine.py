"""Unit tests for the connection state machine (SPEC.md §8)."""

from openfortitray.core.state_machine import (
    ConnectionState,
    StateMachine,
)


def test_initial_state():
    sm = StateMachine()
    assert sm.state == ConnectionState.DISCONNECTED


def test_connect_request_transitions_to_connecting():
    sm = StateMachine()
    sm.on_connect_requested()
    assert sm.state == ConnectionState.CONNECTING


def test_tunnel_up_transitions_to_connected():
    sm = StateMachine()
    sm.on_connect_requested()
    sm.on_log_line("INFO: Tunnel is up and running.")
    assert sm.state == ConnectionState.CONNECTED


def test_windows_tunnel_up_transitions_to_connected():
    sm = StateMachine()
    sm.on_connect_requested()
    sm.on_log_line("INFO: Tunnel interface is UP.")
    assert sm.state == ConnectionState.CONNECTED


def test_auth_failure_transitions_to_error():
    sm = StateMachine()
    sm.on_connect_requested()
    sm.on_log_line("ERROR: Authentication failed")
    assert sm.state == ConnectionState.AUTH_ERROR
    assert sm.is_error


def test_permission_error():
    sm = StateMachine()
    sm.on_connect_requested()
    sm.on_log_line("This process requires administrator privileges.")
    assert sm.state == ConnectionState.PERMISSION_ERROR


def test_disconnect_transitions_back():
    sm = StateMachine()
    sm.on_connect_requested()
    sm.on_log_line("Tunnel is up and running.")
    assert sm.state == ConnectionState.CONNECTED
    sm.on_log_line("Closed connection to gateway.")
    assert sm.state == ConnectionState.DISCONNECTED


def test_process_exit_while_connecting():
    sm = StateMachine()
    sm.on_connect_requested()
    sm.on_process_exit(1)
    assert sm.state == ConnectionState.ERROR


def test_process_exit_while_connected():
    sm = StateMachine()
    sm.on_connect_requested()
    sm.on_log_line("Tunnel is up and running.")
    sm.on_process_exit(1)
    assert sm.state == ConnectionState.ERROR


def test_process_exit_after_clean_disconnect():
    sm = StateMachine()
    sm.on_connect_requested()
    sm.on_disconnect_requested()
    sm.on_process_exit(0)
    assert sm.state == ConnectionState.DISCONNECTED


def test_listener_called_on_transition():
    calls: list[ConnectionState] = []
    sm = StateMachine()
    sm.add_listener(calls.append)
    sm.on_connect_requested()
    sm.on_log_line("Tunnel is up and running.")
    assert calls == [ConnectionState.CONNECTING, ConnectionState.CONNECTED]


def test_listener_not_called_on_same_state():
    calls: list[ConnectionState] = []
    sm = StateMachine()
    sm.add_listener(calls.append)
    sm.on_connect_requested()
    sm.on_connect_requested()  # same state
    assert len(calls) == 1


def test_no_otp_error_is_auth_error():
    sm = StateMachine()
    sm.on_connect_requested()
    sm.on_log_line("ERROR: No OTP specified")
    assert sm.state == ConnectionState.AUTH_ERROR
