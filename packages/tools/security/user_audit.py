"""
UserAuditTool — user/group/privilege audit.

Reports:
  - All local users (UID, GID, shell, home, locked)
  - Users with UID 0 (root-level accounts)
  - Sudo/sudoers configuration summary
  - Users with no password or password never set
  - SSH authorized_keys files found on the system
  - Accounts with login shells that shouldn't have them
  - SUID/SGID binaries on the filesystem
  - World-writable directories in PATH
  - Crontab entries (system + per-user)
  - /etc/hosts.equiv and ~/.rhosts (legacy trust)
  - Last login information

Linux/macOS. Windows support is limited to basic user enumeration.
"""

from __future__ import annotations

import os
import platform
import pwd as _pwd_mod
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType


class UserAuditInput(BaseModel):
    scan_suid: bool = Field(default=True, description="Find SUID/SGID binaries (slow on large filesystems)")
    scan_ssh_keys: bool = Field(default=True, description="Find authorized_keys files")
    scan_crontabs: bool = Field(default=True, description="List crontab entries")
    suid_paths: list[str] = Field(default=["/usr", "/bin", "/sbin", "/opt"], description="Paths to search for SUID binaries")


class UserEntry(BaseModel):
    username: str
    uid: int
    gid: int
    home: str
    shell: str
    is_root_level: bool     # uid == 0
    has_password: bool      # based on shadow/passwd analysis
    account_locked: bool
    last_login: str


class AuditFinding(BaseModel):
    severity: str
    category: str
    detail: str


class UserAuditOutput(BaseModel):
    users: list[UserEntry]
    root_level_users: list[str]
    sudo_users: list[str]
    ssh_authorized_keys: list[str]    # paths found
    suid_binaries: list[str]
    world_writable_path_dirs: list[str]
    crontab_entries: list[str]
    legacy_trust_files: list[str]
    findings: list[AuditFinding]


def _get_users() -> list[UserEntry]:
    entries = []
    system = platform.system()

    if system in ("Linux", "Darwin"):
        # Read shadow for password status on Linux
        shadow_info: dict[str, str] = {}
        try:
            for ln in Path("/etc/shadow").read_text().splitlines():
                parts = ln.split(":")
                if len(parts) >= 2:
                    shadow_info[parts[0]] = parts[1]
        except Exception:
            pass

        for pw in _pwd_mod.getpwall():
            uname = pw.pw_name
            shadow_pw = shadow_info.get(uname, "")
            locked = shadow_pw.startswith("!") or shadow_pw.startswith("*")
            no_pw = shadow_pw in ("", "!", "*", "x", "!!")

            # Last login
            last = ""
            try:
                out = subprocess.run(
                    ["lastlog", "-u", uname], capture_output=True, text=True, timeout=3
                )
                lines = out.stdout.strip().splitlines()
                last = lines[-1] if lines else ""
            except Exception:
                pass

            entries.append(UserEntry(
                username=uname,
                uid=pw.pw_uid,
                gid=pw.pw_gid,
                home=pw.pw_dir,
                shell=pw.pw_shell,
                is_root_level=(pw.pw_uid == 0),
                has_password=not no_pw,
                account_locked=locked,
                last_login=last[:80],
            ))
    elif system == "Windows":
        try:
            out = subprocess.run(
                ["net", "user"], capture_output=True, text=True, timeout=10
            )
            for ln in out.stdout.splitlines():
                name = ln.strip()
                if name and not name.startswith("-") and "User accounts" not in name:
                    entries.append(UserEntry(
                        username=name, uid=0, gid=0, home="", shell="",
                        is_root_level=False, has_password=True, account_locked=False, last_login="",
                    ))
        except Exception:
            pass

    return entries


def _sudo_users() -> list[str]:
    sudo_users = []
    try:
        # Check sudoers
        for path in ["/etc/sudoers", "/etc/sudoers.d"]:
            p = Path(path)
            files = [p] if p.is_file() else list(p.glob("*")) if p.is_dir() else []
            for f in files:
                try:
                    for ln in f.read_text(errors="replace").splitlines():
                        ln = ln.strip()
                        if ln and not ln.startswith("#") and "ALL" in ln:
                            user = ln.split()[0]
                            if user not in ("%sudo", "%wheel", "%admin") and user not in sudo_users:
                                sudo_users.append(user)
                except Exception:
                    pass
    except Exception:
        pass

    # Check groups
    try:
        import grp
        for gname in ("sudo", "wheel", "admin"):
            try:
                g = grp.getgrnam(gname)
                for member in g.gr_mem:
                    if member not in sudo_users:
                        sudo_users.append(member)
            except KeyError:
                pass
    except ImportError:
        pass

    return sudo_users


def _find_ssh_keys() -> list[str]:
    found = []
    try:
        for pw in _pwd_mod.getpwall():
            key_path = Path(pw.pw_dir) / ".ssh" / "authorized_keys"
            if key_path.exists():
                found.append(str(key_path))
    except Exception:
        pass
    # System-wide
    for p in ["/etc/ssh/authorized_keys", "/root/.ssh/authorized_keys"]:
        if Path(p).exists() and p not in found:
            found.append(p)
    return found


def _find_suid(paths: list[str]) -> list[str]:
    suid_bins = []
    for search_path in paths:
        try:
            out = subprocess.run(
                ["find", search_path, "-perm", "/4000", "-o", "-perm", "/2000"],
                capture_output=True, text=True, timeout=30,
            )
            for ln in out.stdout.splitlines():
                ln = ln.strip()
                if ln:
                    suid_bins.append(ln)
        except Exception:
            pass
    return sorted(set(suid_bins))


def _world_writable_path() -> list[str]:
    bad = []
    for d in os.environ.get("PATH", "").split(":"):
        try:
            mode = oct(Path(d).stat().st_mode)
            if mode[-3] in ("2", "3", "6", "7"):
                bad.append(d)
        except Exception:
            pass
    return bad


def _crontabs() -> list[str]:
    entries = []
    # System crontabs
    for path in ["/etc/crontab", "/etc/cron.d"]:
        p = Path(path)
        files = [p] if p.is_file() else list(p.glob("*")) if p.is_dir() else []
        for f in files:
            try:
                for ln in f.read_text(errors="replace").splitlines():
                    ln = ln.strip()
                    if ln and not ln.startswith("#"):
                        entries.append(f"[{f}] {ln}")
            except Exception:
                pass

    # User crontabs
    try:
        cron_dir = Path("/var/spool/cron/crontabs")
        if not cron_dir.exists():
            cron_dir = Path("/var/spool/cron")
        for f in cron_dir.glob("*"):
            try:
                for ln in f.read_text(errors="replace").splitlines():
                    if ln.strip() and not ln.startswith("#"):
                        entries.append(f"[crontab:{f.name}] {ln.strip()}")
            except Exception:
                pass
    except Exception:
        pass

    return entries[:200]


def _legacy_trust() -> list[str]:
    found = []
    for path in ["/etc/hosts.equiv"]:
        if Path(path).exists():
            found.append(path)
    try:
        for pw in _pwd_mod.getpwall():
            rhosts = Path(pw.pw_dir) / ".rhosts"
            if rhosts.exists():
                found.append(str(rhosts))
    except Exception:
        pass
    return found


class UserAuditTool(BaseCallable):
    name = "user_audit"
    description = (
        "Audit local users, groups, sudo privileges, SSH authorized keys, SUID/SGID binaries, "
        "world-writable PATH directories, crontabs, and legacy trust files. "
        "Flags root-level accounts, locked accounts, and privilege escalation risks."
    )
    callable_type = CallableType.TOOL
    input_schema = UserAuditInput
    output_schema = UserAuditOutput

    async def _execute(self, input_data: UserAuditInput, context: object) -> UserAuditOutput:
        users = _get_users()
        root_level = [u.username for u in users if u.is_root_level]
        sudo_list = _sudo_users()
        ssh_keys = _find_ssh_keys() if input_data.scan_ssh_keys else []
        suid = _find_suid(input_data.suid_paths) if input_data.scan_suid else []
        ww_path = _world_writable_path()
        crontabs = _crontabs() if input_data.scan_crontabs else []
        legacy = _legacy_trust()

        findings: list[AuditFinding] = []

        for uname in root_level:
            if uname != "root":
                findings.append(AuditFinding(
                    severity="critical", category="Privilege",
                    detail=f"Non-root account '{uname}' has UID 0 (root-level access)",
                ))

        for u in users:
            if not u.has_password and not u.account_locked and u.shell not in ("/sbin/nologin", "/bin/false", "/usr/sbin/nologin"):
                findings.append(AuditFinding(
                    severity="critical", category="Authentication",
                    detail=f"User '{u.username}' has no password and a valid login shell",
                ))

        for p in legacy:
            findings.append(AuditFinding(
                severity="high", category="Legacy Trust",
                detail=f"Legacy trust file found: {p} — allows password-less rlogin/rsh",
            ))

        for d in ww_path:
            findings.append(AuditFinding(
                severity="high", category="Path Hijacking",
                detail=f"World-writable directory in PATH: {d}",
            ))

        _EXPECTED_SUID = {
            "/usr/bin/sudo", "/usr/bin/su", "/bin/su", "/usr/bin/passwd",
            "/bin/ping", "/usr/bin/ping", "/usr/bin/newgrp", "/usr/bin/gpasswd",
            "/usr/bin/chsh", "/usr/bin/chfn", "/sbin/mount.nfs",
        }
        for binary in suid:
            if binary not in _EXPECTED_SUID:
                findings.append(AuditFinding(
                    severity="medium", category="SUID/SGID",
                    detail=f"Non-standard SUID/SGID binary: {binary}",
                ))

        return UserAuditOutput(
            users=users,
            root_level_users=root_level,
            sudo_users=sudo_list,
            ssh_authorized_keys=ssh_keys,
            suid_binaries=suid,
            world_writable_path_dirs=ww_path,
            crontab_entries=crontabs,
            legacy_trust_files=legacy,
            findings=findings,
        )
