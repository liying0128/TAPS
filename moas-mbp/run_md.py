#!/usr/bin/env python3
"""Portable, resumable GROMACS runner for MOAS-MBP (apo maltose-binding protein).

Works after the folder is copied anywhere. All paths are resolved from this
file's location.

  python3 run_md.py --check
  python3 run_md.py --system mbp_open --length 0          # EM + NVT + NPT only
  python3 run_md.py --system mbp_open --length 20 --gpu   # 20 ns open-start cMD
  python3 run_md.py --system mbp_closed --length 0
  python3 run_md.py --nt 16 --gpu
"""

from __future__ import annotations

import argparse
import json
import os
import re
import select
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Paths: always relative to this script, so the folder is relocatable.
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
STATE_PATH = LOG_DIR / "run_state.json"
RUN_LOG = LOG_DIR / "run_md.log"

DONE_MARKERS = (
    "Finished mdrun",
    "Steepest Descents converged",
    "Energy Minimization converged",
    "Converged to Fmax",
)

ABSOLUTE_INCLUDE = re.compile(r'#include\s+"(/[^"]+|\\\\|[A-Za-z]:\\)[^"]*"')
POSRE_INCLUDE = re.compile(r'#include\s+"[^"]*posre\.itp"')
NSTEPS_LINE = re.compile(r"^(\s*nsteps\s*=\s*)\S+(.*)$")
VERBOSE_STEP_RE = re.compile(
    r"step\s+(\d+)\s*,\s*remaining wall clock time:\s+([0-9.]+)\s*s",
    re.I,
)
VERBOSE_STEP_ONLY_RE = re.compile(r"\bstep\s+(\d+)\b", re.I)
EM_STEP_RE = re.compile(
    r"Step\s+(\d+)\b.*?Fmax\s*[:=]\s*([0-9.+\-eE]+)",
    re.I | re.S,
)
LOG_STEP_RE = re.compile(r"Step\s+Time\s+(\d+)\s+([0-9.]+)", re.S)
PERF_RE = re.compile(r"Performance:\s+([0-9.]+)")
MDP_ASSIGN_RE = re.compile(r"^([A-Za-z][\w\-]*)\s*=\s*(\S+)")

PROD_LENGTHS_NS = (20, 50, 100, 200, 500)
DT_PS = 0.002

# MD runner uses the Python standard library only.
OPTIONAL_PACKAGES = (
    ("numpy", "numpy", "analysis / MOAS features"),
    ("scipy", "scipy", "density / kinetic helpers"),
    ("torch", "torch", "optional temporal models later"),
)


class RunnerError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# System catalogue
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SystemSpec:
    key: str
    title: str
    rel_dir: str
    solvent: str  # "vacuum" | "water"
    em_input: str
    em_mdp: str
    nvt_mdp: str
    npt_mdp: Optional[str]
    short_mdp: str
    ref_mdp: str
    required_mdp: Sequence[str]
    default: bool = True

    @property
    def workdir(self) -> Path:
        return ROOT / self.rel_dir


SYSTEMS: Dict[str, SystemSpec] = {
    "mbp_open": SystemSpec(
        key="mbp_open",
        title="MBP apo open (1OMP) explicit water — production start",
        rel_dir="systems/mbp/water_open",
        solvent="water",
        em_input="ions.gro",
        em_mdp="em.mdp",
        nvt_mdp="nvt.mdp",
        npt_mdp="npt.mdp",
        short_mdp="md_short_2ns.mdp",
        ref_mdp="md_ref.mdp",
        required_mdp=("em.mdp", "nvt.mdp", "npt.mdp", "md_short_2ns.mdp", "md_short_1ns.mdp", "md_ref.mdp"),
    ),
    "mbp_closed": SystemSpec(
        key="mbp_closed",
        title="MBP apo closed (1ANF, maltose removed) explicit water — CV reference",
        rel_dir="systems/mbp/water_closed",
        solvent="water",
        em_input="ions.gro",
        em_mdp="em.mdp",
        nvt_mdp="nvt.mdp",
        npt_mdp="npt.mdp",
        short_mdp="md_short_2ns.mdp",
        ref_mdp="md_ref.mdp",
        required_mdp=("em.mdp", "nvt.mdp", "npt.mdp", "md_short_2ns.mdp", "md_short_1ns.mdp", "md_ref.mdp"),
        default=False,
    ),
}

DEFAULT_KEYS = [k for k, s in SYSTEMS.items() if s.default]


@dataclass
class Step:
    name: str
    deffnm: str  # relative to workdir, no suffix
    mdp: str
    coord: str
    posres: bool = False
    traj_cpt: Optional[str] = None  # previous .cpt for grompp -t
    maxwarn: int = 1
    cpt_min: int = 1  # mdrun -cpt minutes


# ---------------------------------------------------------------------------
# Logging / state
# ---------------------------------------------------------------------------
_interrupted = False
_current_proc: Optional[subprocess.Popen] = None


def _terminate_current() -> None:
    proc = _current_proc
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.terminate()
        except Exception:
            pass
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            proc.kill()
        proc.wait()


def _handle_signal(signum, _frame) -> None:
    global _interrupted
    _interrupted = True
    log(f"caught signal {signum}; stopping GROMACS so the next run can resume", "WARN")
    _terminate_current()


def log(msg: str, level: str = "INFO") -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {level:<7s} {msg}"
    print(line, flush=True)
    with RUN_LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"systems": {}}
    return {"systems": {}}


def save_state(state: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    state["root"] = str(ROOT)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(STATE_PATH)


def record_step(state: dict, sys_key: str, step: str, status: str, **extra) -> None:
    systems = state.setdefault("systems", {})
    entry = systems.setdefault(sys_key, {})
    payload = {"status": status, "time": datetime.now().isoformat(timespec="seconds")}
    payload.update(extra)
    entry[step] = payload
    save_state(state)


# ---------------------------------------------------------------------------
# GROMACS helpers
# ---------------------------------------------------------------------------
def find_gmx() -> str:
    explicit = os.environ.get("GMX") or os.environ.get("GMX_BIN")
    if explicit:
        path = Path(explicit)
        if path.exists():
            return str(path)
        found = shutil.which(explicit)
        if found:
            return found
        raise RunnerError(f"GMX={explicit} not found")
    for name in ("gmx", "gmx_mpi", "gmx_d"):
        found = shutil.which(name)
        if found:
            return found
    raise RunnerError("gmx not in PATH. Load the GROMACS module or set GMX=/path/to/gmx")


def gmx_version(gmx: str) -> str:
    proc = subprocess.run(
        [gmx, "--version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    for line in proc.stdout.splitlines():
        if "GROMACS version" in line or line.strip().startswith("GROMACS"):
            return line.strip()
    return "unknown"


def gro_natom(path: Path) -> int:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) < 3:
        raise RunnerError(f"invalid gro file: {path}")
    return int(lines[1].strip())


def log_finished(log_path: Path) -> bool:
    if not log_path.exists():
        return False
    text = log_path.read_text(encoding="utf-8", errors="replace")
    return any(m in text for m in DONE_MARKERS)


def parse_nsteps(text: str) -> Optional[int]:
    for line in text.splitlines():
        stripped = line.split(";", 1)[0].strip()
        if stripped.startswith("nsteps"):
            _, _, rest = stripped.partition("=")
            token = rest.strip().split()[0] if rest.strip() else ""
            try:
                return int(token)
            except ValueError:
                return None
    return None


def step_complete(workdir: Path, deffnm: str, mdp_path: Optional[Path] = None) -> bool:
    gro = workdir / f"{deffnm}.gro"
    logp = workdir / f"{deffnm}.log"
    if not (gro.exists() and gro.stat().st_size > 0 and log_finished(logp)):
        return False
    if mdp_path is not None and mdp_path.exists() and logp.exists():
        wanted = parse_nsteps(mdp_path.read_text(encoding="utf-8", errors="replace"))
        ran = parse_nsteps(logp.read_text(encoding="utf-8", errors="replace"))
        if wanted is not None and ran is not None and ran < wanted:
            return False
    return True


def last_log_tail(path: Path, n: int = 8) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-n:])


def run_cmd(
    argv: Sequence[str],
    cwd: Path,
    env: Optional[dict] = None,
) -> None:
    global _current_proc
    if _interrupted:
        raise KeyboardInterrupt
    log("$ " + " ".join(argv) + f"   (cwd={cwd})")
    merged = os.environ.copy()
    if env:
        merged.update(env)
    merged.setdefault("GMX_MAXBACKUP", "-1")
    merged.setdefault("GMX_SUPPRESS_DUMP", "1")
    proc = subprocess.Popen(
        list(argv),
        cwd=str(cwd),
        env=merged,
        start_new_session=True,
    )
    _current_proc = proc
    try:
        ret = proc.wait()
    except KeyboardInterrupt:
        _terminate_current()
        raise
    finally:
        _current_proc = None
    if _interrupted:
        raise KeyboardInterrupt
    if ret != 0:
        raise RunnerError(f"command failed ({ret}): {' '.join(argv)}")


def parse_mdp_value(text: str, key: str) -> Optional[str]:
    key_l = key.lower()
    for line in text.splitlines():
        stripped = line.split(";", 1)[0].strip()
        match = MDP_ASSIGN_RE.match(stripped)
        if match and match.group(1).lower() == key_l:
            return match.group(2)
    return None


def mdp_timing(mdp_path: Path) -> Tuple[Optional[int], float]:
    if not mdp_path.exists():
        return None, DT_PS
    text = mdp_path.read_text(encoding="utf-8", errors="replace")
    nsteps = parse_nsteps(text)
    dt_token = parse_mdp_value(text, "dt")
    try:
        dt_ps = float(dt_token) if dt_token else DT_PS
    except ValueError:
        dt_ps = DT_PS
    return nsteps, dt_ps


def default_thread_count() -> int:
    return max(1, os.cpu_count() or 4)


def gpu_flag_sets(gpu: bool, is_em: bool) -> List[List[str]]:
    """Most-aggressive GPU offload first, then safer fallbacks."""
    if not gpu:
        return [[]]
    if is_em:
        return [
            ["-nb", "gpu", "-pme", "gpu"],
            ["-nb", "gpu"],
        ]
    return [
        ["-nb", "gpu", "-pme", "gpu", "-bonded", "gpu", "-pmefft", "gpu", "-update", "gpu"],
        ["-nb", "gpu", "-pme", "gpu", "-pmefft", "gpu", "-update", "gpu"],
        ["-nb", "gpu", "-pme", "gpu"],
        ["-nb", "gpu"],
    ]


def describe_gpu_flags(extra: Sequence[str]) -> str:
    if not extra:
        return "cpu"
    pairs = []
    for i in range(0, len(extra), 2):
        if i + 1 < len(extra):
            pairs.append(f"{extra[i].lstrip('-')}={extra[i + 1]}")
    return " ".join(pairs) if pairs else "gpu"


def fmt_duration(seconds: Optional[float]) -> str:
    if seconds is None or seconds < 0:
        return "?"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def fmt_steps(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 10_000:
        return f"{n / 1000:.1f}k"
    return str(n)


def query_gpu_util() -> Optional[str]:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return None
    try:
        proc = subprocess.run(
            [
                smi,
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    parts = [p.strip() for p in proc.stdout.strip().splitlines()[0].split(",")]
    if len(parts) < 3:
        return None
    try:
        util, mem_used, mem_total = parts[0], float(parts[1]), float(parts[2])
    except ValueError:
        return f"GPU {parts[0]}%"
    return f"GPU {util}% {mem_used/1024:.1f}/{mem_total/1024:.0f}GiB"


class MdProgress:
    """Live one-line progress from gmx -v, the .log file, and nvidia-smi."""

    def __init__(
        self,
        label: str,
        nsteps: Optional[int],
        dt_ps: float,
        log_path: Path,
        gpu: bool,
        is_em: bool,
    ) -> None:
        self.label = label
        self.nsteps = nsteps
        self.dt_ps = dt_ps
        self.log_path = log_path
        self.gpu = gpu
        self.is_em = is_em
        self.step = 0
        self.sim_ps: Optional[float] = None
        self.remain_s: Optional[float] = None
        self.ns_per_day: Optional[float] = None
        self.fmax: Optional[float] = None
        self.gpu_line: Optional[str] = None
        self.anchor_step: Optional[int] = None
        self.anchor_t: Optional[float] = None
        self.last_draw = 0.0
        self.last_gpu_poll = 0.0
        self.last_snapshot = time.time()
        self.last_stdout = 0.0
        self.t0 = time.time()
        self.tty = sys.stderr.isatty()
        self._last_width = 0

    def note_step(self, step: int, sim_ps: Optional[float] = None) -> None:
        if step < 0:
            return
        self.step = max(self.step, step)
        if sim_ps is not None:
            self.sim_ps = sim_ps
        elif self.dt_ps > 0:
            self.sim_ps = self.step * self.dt_ps
        now = time.time()
        if self.anchor_step is None:
            self.anchor_step = step
            self.anchor_t = now
            return
        elapsed = now - (self.anchor_t or now)
        dstep = step - self.anchor_step
        if elapsed >= 2.0 and dstep > 0 and self.dt_ps > 0:
            sim_ns = dstep * self.dt_ps / 1000.0
            self.ns_per_day = sim_ns / elapsed * 86400.0

    def feed(self, text: str) -> None:
        if not text:
            return
        text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)
        match = VERBOSE_STEP_RE.search(text)
        if match:
            self.note_step(int(match.group(1)))
            self.remain_s = float(match.group(2))
            return
        em = EM_STEP_RE.search(text)
        if em:
            self.note_step(int(em.group(1)))
            try:
                self.fmax = float(em.group(2))
            except ValueError:
                pass
            return
        only = VERBOSE_STEP_ONLY_RE.search(text)
        if only and re.search(r"^\s*step\s+\d+", text, re.I):
            self.note_step(int(only.group(1)))
        stripped = text.strip()
        if stripped and re.search(r"\b(WARNING|Error|Fatal error)\b", stripped, re.I):
            if self.tty:
                sys.stderr.write("\n" + stripped + "\n")
                sys.stderr.flush()
            else:
                log(stripped, "WARN")

    def poll_log(self) -> None:
        if not self.log_path.exists():
            return
        try:
            size = self.log_path.stat().st_size
            with self.log_path.open("rb") as fh:
                fh.seek(max(0, size - 24576))
                chunk = fh.read().decode("utf-8", errors="replace")
        except OSError:
            return
        matches = list(LOG_STEP_RE.finditer(chunk))
        if matches:
            step = int(matches[-1].group(1))
            sim_ps = float(matches[-1].group(2))
            self.note_step(step, sim_ps)
        perf = list(PERF_RE.finditer(chunk))
        if perf:
            try:
                self.ns_per_day = float(perf[-1].group(1))
            except ValueError:
                pass

    def poll_gpu(self) -> None:
        if not self.gpu:
            return
        now = time.time()
        if now - self.last_gpu_poll < 2.0:
            return
        self.last_gpu_poll = now
        self.gpu_line = query_gpu_util()

    def _percent(self) -> Optional[float]:
        if not self.nsteps:
            return None
        return min(100.0, 100.0 * self.step / self.nsteps)

    def _eta(self) -> Optional[float]:
        if self.remain_s is not None:
            return self.remain_s
        pct = self._percent()
        if pct is None or pct < 0.2:
            return None
        elapsed = time.time() - self.t0
        return elapsed * (100.0 - pct) / pct

    def _bar(self, width: int = 22) -> str:
        pct = self._percent()
        if pct is None:
            return "[" + ("-" * width) + "]"
        filled = int(round(width * pct / 100.0))
        filled = min(width, max(0, filled))
        return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"

    def format_line(self) -> str:
        bits = [self.label, self._bar()]
        pct = self._percent()
        if pct is not None:
            bits.append(f"{pct:5.1f}%")
        if self.nsteps:
            bits.append(f"step {fmt_steps(self.step)}/{fmt_steps(self.nsteps)}")
        elif self.step:
            bits.append(f"step {self.step}")
        if self.sim_ps is not None and not self.is_em:
            sim_ns = self.sim_ps / 1000.0
            if self.nsteps and self.dt_ps > 0:
                total_ns = self.nsteps * self.dt_ps / 1000.0
                bits.append(f"{sim_ns:.2f}/{total_ns:.0f} ns")
            else:
                bits.append(f"{sim_ns:.2f} ns")
        if self.is_em and self.fmax is not None:
            bits.append(f"Fmax={self.fmax:.3g}")
        if self.ns_per_day:
            bits.append(f"{self.ns_per_day:.0f} ns/day")
        eta = self._eta()
        if eta is not None:
            bits.append(f"ETA {fmt_duration(eta)}")
        bits.append(f"wall {fmt_duration(time.time() - self.t0)}")
        if self.gpu_line:
            bits.append(self.gpu_line)
        return "  ".join(bits)

    def draw(self, force: bool = False, final: bool = False) -> None:
        now = time.time()
        if not final and not force and now - self.last_draw < 0.4:
            return
        self.last_draw = now
        self.poll_log()
        self.poll_gpu()
        line = self.format_line()
        if self.tty:
            width = shutil.get_terminal_size((120, 20)).columns
            shown = line[: max(20, width - 1)]
            pad = max(0, self._last_width - len(shown))
            sys.stderr.write("\r" + shown + (" " * pad))
            sys.stderr.flush()
            self._last_width = len(shown)
            if final:
                sys.stderr.write("\n")
                sys.stderr.flush()
        elif final or now - self.last_stdout >= 15:
            print(line, flush=True)
            self.last_stdout = now
        if not final and now - self.last_snapshot >= 60:
            self.last_snapshot = now
            if self.tty:
                sys.stderr.write("\n")
                sys.stderr.flush()
            log(line)

    def snapshot(self) -> str:
        return self.format_line()


def _mdrun_started(log_path: Path) -> bool:
    if not log_path.exists():
        return False
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return "Started mdrun" in text or "starting mdrun" in text.lower()


def run_mdrun_process(
    argv: Sequence[str],
    cwd: Path,
    progress: MdProgress,
) -> None:
    """Run gmx mdrun, streaming -v progress even when stdout is not a TTY."""
    global _current_proc
    if _interrupted:
        raise KeyboardInterrupt
    log("$ " + " ".join(argv) + f"   (cwd={cwd})")
    merged = os.environ.copy()
    merged.setdefault("GMX_MAXBACKUP", "-1")
    merged.setdefault("GMX_SUPPRESS_DUMP", "1")

    master_fd: Optional[int] = None
    used_pty = False
    try:
        import pty

        master_fd, slave_fd = pty.openpty()
        proc = subprocess.Popen(
            list(argv),
            cwd=str(cwd),
            env=merged,
            stdin=subprocess.DEVNULL,
            stdout=slave_fd,
            stderr=slave_fd,
            start_new_session=True,
        )
        os.close(slave_fd)
        used_pty = True
    except (OSError, ImportError):
        proc = subprocess.Popen(
            list(argv),
            cwd=str(cwd),
            env=merged,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            start_new_session=True,
        )
        master_fd = proc.stdout.fileno() if proc.stdout is not None else None

    _current_proc = proc
    buf = b""
    try:
        while proc.poll() is None:
            if _interrupted:
                _terminate_current()
                raise KeyboardInterrupt
            readable = []
            if master_fd is not None:
                readable, _, _ = select.select([master_fd], [], [], 0.4)
            else:
                time.sleep(0.4)
            if readable:
                try:
                    chunk = os.read(master_fd, 8192)
                except OSError:
                    chunk = b""
                if chunk:
                    buf += chunk
                    parts = re.split(rb"[\r\n]", buf)
                    buf = parts[-1]
                    for part in parts[:-1]:
                        progress.feed(part.decode("utf-8", errors="replace"))
            progress.draw()
        if master_fd is not None:
            while True:
                leftover = b""
                try:
                    ready, _, _ = select.select([master_fd], [], [], 0)
                    if not ready:
                        break
                    leftover = os.read(master_fd, 8192)
                except OSError:
                    break
                if not leftover:
                    break
                buf += leftover
        if buf:
            progress.feed(buf.decode("utf-8", errors="replace"))
        progress.draw(force=True, final=True)
        ret = proc.wait()
    except KeyboardInterrupt:
        _terminate_current()
        progress.draw(force=True, final=True)
        raise
    finally:
        _current_proc = None
        if used_pty and master_fd is not None:
            try:
                os.close(master_fd)
            except OSError:
                pass
        elif proc.stdout is not None:
            try:
                proc.stdout.close()
            except OSError:
                pass
    if _interrupted:
        raise KeyboardInterrupt
    if ret != 0:
        raise RunnerError(f"command failed ({ret}): {' '.join(argv)}")


def relativize_topol(top: Path) -> bool:
    """Rewrite posre includes to a local relative path. Return True if changed."""
    text = top.read_text(encoding="utf-8")
    fixed = POSRE_INCLUDE.sub('#include "posre.itp"', text)
    if fixed != text:
        top.write_text(fixed, encoding="utf-8")
        return True
    return False


# ---------------------------------------------------------------------------
# Environment / Python package check (runs before any MD)
# ---------------------------------------------------------------------------
def detect_gpu() -> bool:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return False
    proc = subprocess.run(
        [smi, "-L"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return proc.returncode == 0 and bool(proc.stdout.strip())


def ns_to_nsteps(ns: int, dt_ps: float = DT_PS) -> int:
    return int(round(float(ns) * 1000.0 / dt_ps))


def prod_template_name(spec: SystemSpec) -> str:
    return "md_prod_vacuum.mdp" if spec.solvent == "vacuum" else "md_prod.mdp"


def sync_mdp(spec: SystemSpec) -> None:
    """Copy shared MDP templates into the system folder so a copied tree stays consistent."""
    dest = spec.workdir / "mdp"
    dest.mkdir(parents=True, exist_ok=True)
    names = list(spec.required_mdp) + [prod_template_name(spec)]
    for name in names:
        src = ROOT / "shared" / "mdp" / name
        if src.exists():
            shutil.copy2(src, dest / name)


def write_prod_mdp(spec: SystemSpec, ns: int) -> str:
    """Write a production MDP with nsteps matching --length. Return the filename in mdp/."""
    src = ROOT / "shared" / "mdp" / prod_template_name(spec)
    if not src.exists():
        raise RunnerError(f"missing production template: {src}")
    nsteps = ns_to_nsteps(ns)
    fname = f"md_prod_{ns}ns_vacuum.mdp" if spec.solvent == "vacuum" else f"md_prod_{ns}ns.mdp"
    dest = spec.workdir / "mdp" / fname
    dest.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    replaced = False
    for line in src.read_text(encoding="utf-8").splitlines():
        match = NSTEPS_LINE.match(line)
        if match:
            lines.append(f"nsteps                   = {nsteps}       ; {ns} ns")
            replaced = True
        else:
            lines.append(line)
    if not replaced:
        raise RunnerError(f"no nsteps line in {src}")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"{spec.key}: wrote mdp/{fname}  nsteps={nsteps}  ({ns} ns)")
    return fname


def check_python_packages() -> List[str]:
    """Log interpreter + packages. Returns missing *optional* pip names. Never blocks MD."""
    import importlib.util

    py = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    log(f"Python {py}  ({sys.executable})")
    if sys.version_info < (3, 8):
        log("Python >= 3.8 is required", "ERROR")
        raise RunnerError(f"Python {py} is too old; need >= 3.8")
    log("MD runner: no extra pip packages required (standard library only)")
    missing: List[str] = []
    for mod, pip_name, why in OPTIONAL_PACKAGES:
        if importlib.util.find_spec(mod) is None:
            missing.append(pip_name)
            log(f"optional {pip_name}: not installed  ({why}; not needed to start MD)", "WARN")
        else:
            log(f"optional {pip_name}: installed  ({why})")
    if missing:
        log("later MOAS analysis: python3 -m pip install " + " ".join(missing), "WARN")
    else:
        log("optional MOAS packages: all present")
    req = ROOT / "requirements.txt"
    if req.exists():
        log(f"requirements file: {req}")
    return missing


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------
def self_check(gmx: str, specs: Sequence[SystemSpec], repair: bool = True) -> List[str]:
    errors: List[str] = []
    warnings: List[str] = []

    log(f"ROOT = {ROOT}")
    if not ROOT.exists():
        errors.append(f"project root does not exist: {ROOT}")
        return errors

    ver = gmx_version(gmx)
    log(f"GROMACS executable: {gmx}")
    log(f"GROMACS version: {ver}")

    gpu_ok = detect_gpu()
    log(f"NVIDIA GPU via nvidia-smi: {'yes' if gpu_ok else 'no'}")

    for tmpl in ("md_prod.mdp",):
        path = ROOT / "shared" / "mdp" / tmpl
        if not path.exists():
            errors.append(f"missing shared production template {path.relative_to(ROOT)}")

    for spec in specs:
        wd = spec.workdir
        prefix = spec.key
        if not wd.is_dir():
            if spec.default:
                errors.append(f"{prefix}: missing directory {wd.relative_to(ROOT)}")
            else:
                warnings.append(f"{prefix}: not prepared ({wd.relative_to(ROOT)} missing)")
            continue

        top = wd / "topol.top"
        if not top.exists():
            errors.append(f"{prefix}: missing topol.top")
            continue

        if repair:
            sync_mdp(spec)
            if relativize_topol(top):
                log(f"{prefix}: rewrote posre #include to relative path")

        text = top.read_text(encoding="utf-8")
        for match in ABSOLUTE_INCLUDE.finditer(text):
            inc = match.group(0)
            if "amber99sb-ildn.ff" in inc or "gromacs/top" in inc:
                continue
            errors.append(f"{prefix}: absolute #include will break after copy: {inc}")

        posre = wd / "posre.itp"
        if not posre.exists():
            errors.append(f"{prefix}: missing posre.itp (needed for NVT/NPT POSRES)")

        gro_in = wd / spec.em_input
        if not gro_in.exists():
            errors.append(f"{prefix}: missing starting coordinates {spec.em_input}")
        else:
            natom = gro_natom(gro_in)
            log(f"{prefix}: {spec.em_input}  atoms={natom}")

        for mdp_name in spec.required_mdp:
            if not (wd / "mdp" / mdp_name).exists():
                errors.append(f"{prefix}: missing mdp/{mdp_name}")

        if not (wd / "mdp" / spec.em_mdp).exists():
            errors.append(f"{prefix}: missing mdp/{spec.em_mdp}")

    if warnings:
        for w in warnings:
            log(w, "WARN")
    if errors:
        for e in errors:
            log(e, "ERROR")
    else:
        log("self-check passed")
    return errors


# ---------------------------------------------------------------------------
# Step execution with skip / resume
# ---------------------------------------------------------------------------
def grompp(
    gmx: str,
    spec: SystemSpec,
    step: Step,
    maxwarn: int,
) -> None:
    wd = spec.workdir
    tpr = wd / f"{step.deffnm}.tpr"
    tpr.parent.mkdir(parents=True, exist_ok=True)
    argv = [
        gmx,
        "grompp",
        "-f",
        f"mdp/{step.mdp}",
        "-c",
        step.coord,
        "-p",
        "topol.top",
        "-o",
        f"{step.deffnm}.tpr",
        "-maxwarn",
        str(maxwarn),
    ]
    if step.posres:
        argv += ["-r", step.coord]
    if step.traj_cpt:
        cpt = wd / step.traj_cpt
        if cpt.exists():
            argv += ["-t", step.traj_cpt]
        else:
            log(f"{spec.key}/{step.name}: no {step.traj_cpt}, grompp without -t", "WARN")
    run_cmd(argv, cwd=wd)
    if not tpr.exists():
        raise RunnerError(f"grompp did not produce {tpr}")


def mdrun(
    gmx: str,
    spec: SystemSpec,
    step: Step,
    nt: int,
    gpu: bool,
    resume: bool,
) -> None:
    wd = spec.workdir
    is_em = step.name == "em"
    mdp_path = wd / "mdp" / step.mdp
    nsteps, dt_ps = mdp_timing(mdp_path)
    logp = wd / f"{step.deffnm}.log"
    cpt = wd / f"{step.deffnm}.cpt"

    base = [
        gmx,
        "mdrun",
        "-v",
        "-deffnm",
        step.deffnm,
        "-cpt",
        str(step.cpt_min),
        "-nt",
        str(nt),
        "-pin",
        "on" if gpu else "off",
    ]
    if gpu:
        # One PP rank feeding the GPU; remaining threads are OpenMP.
        base += ["-ntmpi", "1"]

    resume_args: List[str] = []
    if resume and cpt.exists():
        resume_args = ["-cpi", f"{step.deffnm}.cpt", "-append"]
        log(f"{spec.key}/{step.name}: resuming from checkpoint")

    flag_sets = gpu_flag_sets(gpu, is_em=is_em)
    last_error: Optional[Exception] = None
    for attempt, extra in enumerate(flag_sets):
        if extra or gpu:
            log(f"{spec.key}/{step.name}: resources nt={nt} pin={'on' if gpu else 'off'}  {describe_gpu_flags(extra)}")
        progress = MdProgress(
            label=f"{spec.key}/{step.name}",
            nsteps=nsteps,
            dt_ps=dt_ps,
            log_path=logp,
            gpu=gpu,
            is_em=is_em,
        )
        argv = base + extra + resume_args
        try:
            run_mdrun_process(argv, cwd=wd, progress=progress)
            last_error = None
            break
        except KeyboardInterrupt:
            raise
        except RunnerError as exc:
            last_error = exc
            started = _mdrun_started(logp)
            can_fallback = (
                attempt < len(flag_sets) - 1
                and not started
                and not _interrupted
            )
            if not can_fallback:
                raise
            log(
                f"{spec.key}/{step.name}: {describe_gpu_flags(extra)} rejected at startup; "
                f"falling back to {describe_gpu_flags(flag_sets[attempt + 1])}",
                "WARN",
            )

    if last_error is not None:
        raise last_error
    if not step_complete(wd, step.deffnm):
        tail = last_log_tail(logp)
        raise RunnerError(
            f"{spec.key}/{step.name} did not finish cleanly.\n{tail}"
        )


def ensure_step(
    gmx: str,
    spec: SystemSpec,
    step: Step,
    state: dict,
    nt: int,
    gpu: bool,
    force: bool,
) -> str:
    """Return 'skipped' | 'resumed' | 'ran'."""
    wd = spec.workdir
    deffnm = step.deffnm
    tpr = wd / f"{deffnm}.tpr"
    cpt = wd / f"{deffnm}.cpt"
    coord = wd / step.coord

    if _interrupted:
        raise KeyboardInterrupt

    mdp_path = wd / "mdp" / step.mdp

    if not force and step_complete(wd, deffnm, mdp_path):
        log(f"{spec.key}/{step.name}: already complete -> skip")
        record_step(state, spec.key, step.name, "skipped")
        return "skipped"

    if not coord.exists():
        raise RunnerError(f"{spec.key}/{step.name}: missing input {step.coord}")

    logp = wd / f"{deffnm}.log"
    wanted = parse_nsteps(mdp_path.read_text(encoding="utf-8", errors="replace")) if mdp_path.exists() else None
    prev = parse_nsteps(logp.read_text(encoding="utf-8", errors="replace")) if logp.exists() else None
    stale = wanted is not None and prev is not None and prev < wanted
    if stale:
        log(
            f"{spec.key}/{step.name}: previous run had nsteps={prev}, "
            f"mdp now wants {wanted} -> re-run from this step",
            "WARN",
        )

    resume = (
        (not force)
        and (not stale)
        and tpr.exists()
        and cpt.exists()
        and not step_complete(wd, deffnm, mdp_path)
    )
    if resume:
        log(f"{spec.key}/{step.name}: interrupted previously, continuing")
        record_step(state, spec.key, step.name, "resuming")
        mdrun(gmx, spec, step, nt, gpu, resume=True)
        record_step(state, spec.key, step.name, "done", how="resumed")
        return "resumed"

    # Fresh (re)start of this step. Re-grompp unless we are forcing a clean mdrun
    # from an existing tpr that never produced a checkpoint.
    need_grompp = force or stale or not tpr.exists()
    if need_grompp:
        grompp(gmx, spec, step, maxwarn=step.maxwarn)
    elif tpr.exists() and not cpt.exists():
        log(f"{spec.key}/{step.name}: tpr exists without checkpoint, restarting mdrun")

    record_step(state, spec.key, step.name, "running")
    mdrun(gmx, spec, step, nt, gpu, resume=False)
    record_step(state, spec.key, step.name, "done", how="ran")
    return "ran"


def pipeline_steps(
    spec: SystemSpec,
    prod_mdp: Optional[str],
    prod_deffnm: Optional[str],
    short_mdp: Optional[str],
) -> List[Step]:
    steps = [
        Step(name="em", deffnm="em", mdp=spec.em_mdp, coord=spec.em_input, posres=False, cpt_min=5),
        Step(
            name="nvt",
            deffnm="nvt",
            mdp=spec.nvt_mdp,
            coord="em.gro",
            posres=(spec.solvent == "water"),
            cpt_min=5,
        ),
    ]
    if spec.solvent == "water":
        assert spec.npt_mdp
        steps.append(
            Step(
                name="npt",
                deffnm="npt",
                mdp=spec.npt_mdp,
                coord="nvt.gro",
                posres=True,
                traj_cpt="nvt.cpt",
                cpt_min=5,
            )
        )
        prod_coord = "npt.gro"
        prod_cpt = "npt.cpt"
    else:
        prod_coord = "nvt.gro"
        prod_cpt = "nvt.cpt"

    if prod_mdp and prod_deffnm:
        steps.append(
            Step(
                name="prod",
                deffnm=prod_deffnm,
                mdp=prod_mdp,
                coord=prod_coord,
                posres=False,
                traj_cpt=prod_cpt,
                cpt_min=15,
            )
        )
    if short_mdp:
        steps.append(
            Step(
                name="short",
                deffnm="runs/md_short",
                mdp=short_mdp,
                coord=prod_coord,
                posres=False,
                cpt_min=1,
            )
        )
    return steps


def run_system(
    gmx: str,
    spec: SystemSpec,
    state: dict,
    nt: int,
    gpu: bool,
    force: bool,
    prod_mdp: Optional[str],
    prod_deffnm: Optional[str],
    short_mdp: Optional[str],
) -> Dict[str, str]:
    wd = spec.workdir
    if not wd.is_dir():
        raise RunnerError(f"{spec.key}: directory missing: {wd}")
    (wd / "runs").mkdir(exist_ok=True)
    sync_mdp(spec)
    log(f"==== {spec.title}  ({spec.rel_dir}) ====")
    gro_in = wd / spec.em_input
    if gro_in.exists():
        natom = gro_natom(gro_in)
        log(f"{spec.key}: {natom} atoms, {nt} threads, gpu={gpu}")
        if natom < 500 and gpu:
            log(
                f"{spec.key}: small system; a 4090 will not stay at 100% GPU, "
                "that is normal. MBP water should load the GPU much more.",
                "WARN",
            )
    results = {}
    for step in pipeline_steps(
        spec, prod_mdp=prod_mdp, prod_deffnm=prod_deffnm, short_mdp=short_mdp
    ):
        results[step.name] = ensure_step(gmx, spec, step, state, nt, gpu, force)
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Self-checking, resumable GROMACS runner for MOAS-MBP.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Apo MBP only (no maltose). Default system: mbp_open (1OMP).
mbp_closed is the 1ANF apo reference box for domain distance / hinge angle.

--length 0 runs EM + NVT + NPT and stops (build the equilibrated system).
--length 20 writes runs/md_20ns from the NPT checkpoint.

GPU is auto-detected. Use --cpu / --gpu to override, --nt N to cap threads.
Rerun the same command to resume from .cpt.
""",
    )
    p.add_argument(
        "--system",
        action="append",
        dest="systems",
        metavar="KEY",
        help="system key (repeatable). default: all main systems",
    )
    p.add_argument("--list", action="store_true", help="list systems and exit")
    p.add_argument(
        "--check",
        action="store_true",
        help="check Python packages, GROMACS, GPU, and input files; do not simulate",
    )
    p.add_argument("--mbp", action="store_true", help=argparse.SUPPRESS)
    p.add_argument(
        "--length",
        type=int,
        default=20,
        choices=[0, *PROD_LENGTHS_NS],
        help="unrestrained production length in ns (0 = EM+NVT+NPT only). default: 20",
    )
    p.add_argument(
        "--short",
        action="store_true",
        help="also run a 100 ps short trajectory (adaptive-round smoke test)",
    )
    p.add_argument(
        "--short-500ps",
        action="store_true",
        help="use 500 ps short-MD mdp instead of 100 ps (implies --short)",
    )
    p.add_argument(
        "--ref",
        action="store_true",
        help=argparse.SUPPRESS,  # deprecated: production is now the default
    )
    p.add_argument("--force", action="store_true", help="rerun all steps even if already complete")
    p.add_argument("--nt", type=int, default=int(os.environ.get("MOAS_NT", os.environ.get("TAPS_NT", "0")) or 0),
                   help="mdrun -nt (default: all logical CPUs, with -pin on)")
    p.add_argument("--gpu", action="store_true", help="force GPU (default: auto-detect)")
    p.add_argument("--cpu", action="store_true", help="force CPU, disable GPU")
    p.add_argument("--gmx", default=None, help="gmx executable (else $GMX or PATH)")
    return p.parse_args(argv)


def select_specs(args: argparse.Namespace) -> List[SystemSpec]:
    if args.systems:
        keys = args.systems
    else:
        keys = list(DEFAULT_KEYS)
    specs = []
    unknown = []
    for key in keys:
        if key not in SYSTEMS:
            unknown.append(key)
            continue
        spec = SYSTEMS[key]
        if not spec.default and not spec.workdir.is_dir():
            log(f"skip {key}: not prepared", "WARN")
            continue
        specs.append(spec)
    if unknown:
        raise RunnerError("unknown system(s): " + ", ".join(unknown) + "\nknown: " + ", ".join(SYSTEMS))
    if not specs:
        raise RunnerError("no systems selected")
    return specs


def short_mdp_for(spec: SystemSpec, use_500: bool) -> str:
    if not use_500:
        return spec.short_mdp
    if spec.solvent == "vacuum":
        return "md_short_500ps_vacuum.mdp"
    return "md_short_500ps.mdp"


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.list:
        print(f"ROOT: {ROOT}")
        print(f"{'key':<16} {'on by default':<14} directory")
        for key, spec in SYSTEMS.items():
            flag = "yes" if spec.default else "no"
            exists = "ok" if spec.workdir.is_dir() else "MISSING"
            print(f"{key:<16} {flag:<14} {spec.rel_dir}  [{exists}]")
        return 0

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    log("---- environment / Python package check ----")
    try:
        check_python_packages()
    except RunnerError as exc:
        log(str(exc), "ERROR")
        return 2

    if args.gmx:
        os.environ["GMX"] = args.gmx
    try:
        gmx = find_gmx()
    except RunnerError as exc:
        log(str(exc), "ERROR")
        log("load the GROMACS module or: export GMX=/path/to/gmx", "ERROR")
        return 2

    nt = args.nt or default_thread_count()
    ncpu = os.cpu_count() or 0
    if args.cpu and args.gpu:
        log("use only one of --cpu / --gpu", "ERROR")
        return 2
    if args.cpu:
        gpu = False
    elif args.gpu:
        gpu = True
    else:
        gpu = detect_gpu()
        log(f"GPU auto-detect: {'on' if gpu else 'off'}")
    log(
        f"CPU: {ncpu} logical processors, mdrun -nt {nt} -pin on"
        + (" -ntmpi 1" if gpu else "")
    )
    if gpu:
        log("GPU offload: nb + pme + bonded + update (energy min: nb + pme)")

    length = args.length
    if args.ref:
        log("--ref is deprecated; production length is --length (default 20 ns)", "WARN")
        if length == 0:
            length = 20
    do_short = args.short or args.short_500ps

    try:
        specs = select_specs(args)
    except RunnerError as exc:
        log(str(exc), "ERROR")
        return 2

    errors = self_check(gmx, specs, repair=True)
    if errors:
        log(f"self-check found {len(errors)} error(s); fix these before running", "ERROR")
        return 2
    if length and len(specs) > 1:
        log(
            f"{len(specs)} systems × {length} ns production. "
            "MOAS-MBP: start with --system mbp_open --length 0, then --length 20",
            "WARN",
        )
    if args.check:
        log("check finished; no simulation started")
        if length:
            log(f"next: python3 run_md.py --nt {nt} --length {length}")
        else:
            log(f"next: python3 run_md.py --system mbp_open --length 0 --gpu --nt {nt}")
        return 0

    if length == 0:
        log("length=0: EM + NVT + NPT only (no unrestrained production)")

    state = load_state()
    state["gmx"] = gmx
    state["nt"] = nt
    state["gpu"] = gpu
    state["length_ns"] = length
    save_state(state)

    log(
        f"threads = {nt}   gpu = {gpu}   length = {length} ns   "
        f"short = {do_short}   force = {args.force}"
    )
    started = time.time()
    failed = []
    try:
        for spec in specs:
            try:
                prod_mdp = None
                prod_deffnm = None
                if length:
                    prod_mdp = write_prod_mdp(spec, length)
                    prod_deffnm = f"runs/md_{length}ns"
                smdp = None
                if do_short:
                    smdp = short_mdp_for(spec, args.short_500ps)
                    if not (spec.workdir / "mdp" / smdp).exists():
                        raise RunnerError(f"{spec.key}: missing mdp/{smdp}")
                results = run_system(
                    gmx,
                    spec,
                    state,
                    nt=nt,
                    gpu=gpu,
                    force=args.force,
                    prod_mdp=prod_mdp,
                    prod_deffnm=prod_deffnm,
                    short_mdp=smdp,
                )
                log(f"{spec.key} steps: " + ", ".join(f"{k}={v}" for k, v in results.items()))
            except KeyboardInterrupt:
                record_step(state, spec.key, "pipeline", "interrupted")
                log("interrupted. rerun the same command to continue.", "WARN")
                return 130
            except RunnerError as exc:
                log(str(exc), "ERROR")
                record_step(state, spec.key, "pipeline", "failed", error=str(exc))
                failed.append(spec.key)
                log("later systems will still be attempted", "WARN")
    finally:
        elapsed = time.time() - started
        log(f"elapsed {elapsed/60:.1f} min")

    if failed:
        log("failed: " + ", ".join(failed), "ERROR")
        log("rerun python3 run_md.py with the same flags to resume remaining / failed steps")
        return 1
    log("all requested systems finished")
    return 0


if __name__ == "__main__":
    sys.exit(main())
