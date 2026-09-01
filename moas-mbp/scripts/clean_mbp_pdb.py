#!/usr/bin/env python3
"""Download 1OMP / 1ANF, keep chain A, rebuild missing heavy atoms with tleap, HIS → HIE."""

from __future__ import annotations

import os
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "systems/mbp/structures"
RCSB = "https://files.rcsb.org/download/{pdb}.pdb"
TLEAP = Path("/home/ly/miniconda3/envs/ambertools/bin/tleap")
AMBERHOME = Path("/home/ly/miniconda3/envs/ambertools")


def fetch(pdb_id: str) -> str:
    url = RCSB.format(pdb=pdb_id.upper())
    dest = DEST / f"{pdb_id.upper()}_raw.pdb"
    DEST.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1000:
        print(f"reuse {dest}")
        return dest.read_text(encoding="utf-8", errors="replace")
    print(f"download {url}")
    with urllib.request.urlopen(url, timeout=60) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    dest.write_text(text, encoding="utf-8")
    return text


def clean_chain_a(text: str) -> str:
    """Keep protein ATOM records of chain A. Leave HIS as HIS for tleap."""
    out = []
    serial = 0
    for line in text.splitlines():
        rec = line[:6].strip()
        if rec != "ATOM":
            continue
        if len(line) < 22:
            continue
        chain = line[21]
        if chain not in ("A", " "):
            continue
        resn = line[17:20].strip()
        if resn in ("HOH", "WAT", "SOL"):
            continue
        serial += 1
        body = line[11:]
        newline = f"ATOM  {serial:5d}{body}".rstrip() + "\n"
        out.append(newline)
    if serial < 200:
        raise SystemExit(f"too few atoms after cleaning ({serial})")
    out.append("TER\nEND\n")
    return "".join(out)


def his_to_hie(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if line.startswith("ATOM") and line[17:20] == "HIS":
            line = line[:17] + "HIE" + line[20:]
        lines.append(line)
    return "\n".join(lines) + "\n"


def tleap_rebuild(src: Path, dest: Path) -> None:
    if not TLEAP.exists():
        raise SystemExit(f"tleap not found at {TLEAP}")
    inp = src.with_name(src.stem + "_leapin.pdb")
    inp.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    script = dest.with_suffix(".tleap.in")
    log = dest.with_suffix(".tleap.log")
    script.write_text(
        "\n".join(
            [
                "source leaprc.protein.ff14SB",
                f"p = loadPdb {inp}",
                f"savePdb p {dest}",
                "quit",
                "",
            ]
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["AMBERHOME"] = str(AMBERHOME)
    print(f"tleap rebuild {src.name}")
    proc = subprocess.run(
        [str(TLEAP), "-f", str(script)],
        cwd=str(DEST),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    log.write_text(proc.stdout or "", encoding="utf-8")
    if proc.returncode != 0 or not dest.exists():
        raise SystemExit(f"tleap failed for {src}\n{(proc.stdout or '')[-2000:]}")
    dest.write_text(his_to_hie(dest.read_text(encoding="utf-8")), encoding="utf-8")


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    open_txt = fetch("1OMP")
    closed_txt = fetch("1ANF")
    stub_open = DEST / "mbp_open_stub.pdb"
    stub_closed = DEST / "mbp_closed_stub.pdb"
    stub_open.write_text(clean_chain_a(open_txt), encoding="utf-8")
    stub_closed.write_text(clean_chain_a(closed_txt), encoding="utf-8")
    tleap_rebuild(stub_open, DEST / "mbp_open.pdb")
    tleap_rebuild(stub_closed, DEST / "mbp_closed.pdb")
    for path in (DEST / "mbp_open.pdb", DEST / "mbp_closed.pdb"):
        n = sum(1 for ln in path.read_text().splitlines() if ln.startswith("ATOM"))
        print(f"wrote {path}  ({n} ATOM)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
