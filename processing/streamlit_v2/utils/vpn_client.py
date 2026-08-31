"""NetBird VPN client manager for Streamlit container."""

import os
import subprocess
import time
from typing import Tuple
import streamlit as st


def _run_cmd(cmd: list[str]) -> Tuple[bool, str]:
    """Run a shell command safely, returning (success, output_or_error)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        else:
            return False, result.stderr.strip() or result.stdout.strip()
    except Exception as e:
        return False, str(e)


def is_connected() -> bool:
    """Check if NetBird reports a 'Connected' status."""
    ok, out = _run_cmd(["netbird", "status"])
    if not ok:
        return False
    return "connected" in out.lower()


def ensure_vpn_connected(timeout: int = 30) -> bool:
    """Ensure that the NetBird VPN is up and connected.

    Reads NETBIRD_SETUP_KEY and optionally NETBIRD_MANAGEMENT_URL from environment.
    Caches connection status in st.session_state.
    """
    if st.session_state.get("vpn_connected") and is_connected():
        return True

    if is_connected():
        st.session_state.vpn_connected = True
        return True

    setup_key = os.getenv("NETBIRD_SETUP_KEY")
    management_url = os.getenv("NETBIRD_MANAGEMENT_URL")

    if not setup_key:
        st.error("⚠️ `NETBIRD_SETUP_KEY` is not set in the environment variables.")
        return False

    # Start the daemon service if not running
    _run_cmd(["netbird", "service", "start"])

    # Connect using setup key
    cmd = ["netbird", "up", "--setup-key", setup_key]
    if management_url:
        cmd.extend(["--management-url", management_url])

    with st.spinner("Connecting to NetBird VPN..."):
        ok, out = _run_cmd(cmd)
        if not ok:
            st.error(f"❌ NetBird connection failed: {out}")
            st.session_state.vpn_connected = False
            return False

        # Wait and verify connection
        start_time = time.time()
        while time.time() - start_time < timeout:
            if is_connected():
                st.session_state.vpn_connected = True
                st.sidebar.success("🟢 NetBird VPN Connected")
                return True
            time.sleep(1)

    st.error("❌ Timed out waiting for NetBird VPN to establish connection.")
    st.session_state.vpn_connected = False
    return False


def disconnect_vpn() -> Tuple[bool, str]:
    """Disconnect NetBird VPN session."""
    ok, out = _run_cmd(["netbird", "down"])
    st.session_state.vpn_connected = False
    return ok, out
