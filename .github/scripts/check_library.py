#!/usr/bin/env python3
"""Konsistenz-Checks für die Tiro-KiCad-Library.

Läuft ohne KiCad, nur mit der Python-Standardbibliothek. Fehler lassen den
Lauf scheitern, Warnungen nur mit --strict. In GitHub Actions werden alle
Meldungen zusätzlich als Annotationen und als Job-Summary ausgegeben.

    python3 .github/scripts/check_library.py [--root .] [--strict]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

LIB_PREFIX = "Tiro_"
MODEL_EXTENSIONS = {".step", ".stp", ".wrl", ".wrz"}
# Dateien, die nie im Repo landen sollen. In CI enthält der Checkout nur
# getrackte Dateien, ein Treffer heißt also: versehentlich eingecheckt.
FORBIDDEN_PATTERNS = ["*.bak", "*-backups", "*.lck", "fp-info-cache", "*.kicad_prl"]


# --------------------------------------------------------------------------
# Minimaler S-Expression-Parser für .kicad_sym / .kicad_mod
# --------------------------------------------------------------------------

class ParseError(Exception):
    pass


class Sym(str):
    """Nicht gequotetes Atom, damit sich (symbol ...) von "symbol" unterscheidet."""


_TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))', re.S)


def parse_sexpr(text: str):
    stack: list[list] = [[]]
    pos = 0
    end = len(text.rstrip())
    while pos < end:
        m = _TOKEN.match(text, pos)
        if not m:
            line = text.count("\n", 0, pos) + 1
            raise ParseError(f"unerwartetes Zeichen in Zeile {line}")
        pos = m.end()
        if m.group(1):
            stack.append([])
        elif m.group(2):
            if len(stack) == 1:
                line = text.count("\n", 0, pos) + 1
                raise ParseError(f"überzählige ')' in Zeile {line}")
            node = stack.pop()
            stack[-1].append(node)
        elif m.group(3) is not None:
            stack[-1].append(re.sub(r"\\(.)", r"\1", m.group(3)))
        else:
            stack[-1].append(Sym(m.group(4)))
    if len(stack) != 1:
        raise ParseError(f"{len(stack) - 1} nicht geschlossene '('")
    if len(stack[0]) != 1 or not isinstance(stack[0][0], list):
        raise ParseError("Datei enthält nicht genau einen Wurzelausdruck")
    return stack[0][0]


def children(node, tag: str):
    return [c for c in node[1:] if isinstance(c, list) and c and c[0] == tag and isinstance(c[0], Sym)]


def first(node, tag: str):
    found = children(node, tag)
    return found[0] if found else None


def properties(node) -> dict[str, str]:
    return {p[1]: p[2] for p in children(node, "property") if len(p) >= 3}


# --------------------------------------------------------------------------
# Meldungen
# --------------------------------------------------------------------------

@dataclass
class Finding:
    level: str  # "error" | "warning"
    file: str
    message: str
    line: int | None = None


class Report:
    def __init__(self, root: Path):
        self.root = root
        self.findings: list[Finding] = []
        self.stats: dict[str, int] = defaultdict(int)

    def add(self, level: str, path: Path, message: str, line: int | None = None):
        self.findings.append(Finding(level, self.rel(path), message, line))

    def error(self, path, message, line=None):
        self.add("error", path, message, line)

    def warning(self, path, message, line=None):
        self.add("warning", path, message, line)

    def rel(self, path: Path) -> str:
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return str(path)

    def count(self, level: str) -> int:
        return sum(1 for f in self.findings if f.level == level)


def line_of(text: str, needle: str) -> int | None:
    idx = text.find(needle)
    return text.count("\n", 0, idx) + 1 if idx >= 0 else None


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

def load_footprint_index(root: Path) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for pretty in sorted((root / "footprints").glob("*.pretty")):
        index[pretty.stem] = {f.stem for f in pretty.glob("*.kicad_mod")}
    return index


def check_symbols(root: Path, fp_index: dict[str, set[str]], rep: Report):
    for lib in sorted((root / "symbols").glob("*.kicad_sym")):
        text = lib.read_text(encoding="utf-8")
        try:
            tree = parse_sexpr(text)
        except ParseError as exc:
            rep.error(lib, f"Datei lässt sich nicht parsen: {exc}")
            continue
        if tree[0] != "kicad_symbol_lib":
            rep.error(lib, "Wurzelelement ist nicht (kicad_symbol_lib ...)")
            continue

        seen: set[str] = set()
        no_datasheet: list[str] = []
        for sym in children(tree, "symbol"):
            name = sym[1]
            rep.stats["symbols"] += 1
            if name in seen:
                rep.error(lib, f"Symbol '{name}' ist doppelt vorhanden", line_of(text, f'(symbol "{name}"'))
            seen.add(name)

            props = properties(sym)
            is_power = first(sym, "power") is not None
            sym_line = line_of(text, f'(symbol "{name}"')

            if not props.get("Reference", "").strip():
                rep.error(lib, f"Symbol '{name}': Reference ist leer", sym_line)

            fp = props.get("Footprint", "").strip()
            if not fp:
                if not is_power:
                    rep.warning(lib, f"Symbol '{name}': kein Footprint zugewiesen", sym_line)
            elif ":" not in fp:
                rep.error(lib, f"Symbol '{name}': Footprint '{fp}' hat kein 'Lib:Name'-Format", sym_line)
            else:
                fp_lib, fp_name = fp.split(":", 1)
                if fp_lib.startswith(LIB_PREFIX):
                    if fp_lib not in fp_index:
                        rep.error(lib, f"Symbol '{name}': Footprint-Library '{fp_lib}' existiert nicht", sym_line)
                    elif fp_name not in fp_index[fp_lib]:
                        rep.error(lib, f"Symbol '{name}': Footprint '{fp}' existiert nicht", sym_line)
                else:
                    rep.stats["external footprint refs"] += 1

            ds = props.get("Datasheet", "").strip()
            if not is_power and ds in ("", "~"):
                no_datasheet.append(name)

        if no_datasheet:
            shown = ", ".join(no_datasheet[:8]) + (" …" if len(no_datasheet) > 8 else "")
            rep.warning(lib, f"{len(no_datasheet)} Symbol(e) ohne Datasheet: {shown}")


def resolve_model(path_str: str, root: Path) -> tuple[str, Path | None]:
    """Ordnet einen 3D-Modellpfad einer Datei im Repo zu.

    Rückgabe (art, pfad): art ist "repo" (liegt in 3dmodels/ dieses Repos),
    "project" (${KIPRJMOD}, gehört zum Projekt, nicht zur Lib) oder
    "external" (irgendwo anders, z.B. ${KICAD10_3DMODEL_DIR}).
    """
    p = path_str.replace("\\", "/")
    if p.startswith("${KIPRJMOD}"):
        return "project", None
    m = re.search(r"(?:^|/)3dmodels/(.+)$", p)
    if not m:
        return "external", None
    # Pfade in die offizielle KiCad-Lib (${KICADx_3DMODEL_DIR}/...) sind extern.
    if re.match(r"^\$\{KICAD\d*_3DMODEL_DIR\}", p):
        return "external", None
    return "repo", root / "3dmodels" / m.group(1)


def is_absolute(path_str: str) -> bool:
    return bool(re.match(r"^([A-Za-z]:[\\/]|/)", path_str))


def check_footprints(root: Path, rep: Report) -> set[Path]:
    used_models: set[Path] = set()
    for pretty in sorted((root / "footprints").glob("*.pretty")):
        absolute: list[str] = []
        for mod in sorted(pretty.glob("*.kicad_mod")):
            rep.stats["footprints"] += 1
            text = mod.read_text(encoding="utf-8")
            try:
                tree = parse_sexpr(text)
            except ParseError as exc:
                rep.error(mod, f"Datei lässt sich nicht parsen: {exc}")
                continue
            if tree[0] not in ("footprint", "module"):
                rep.error(mod, "Wurzelelement ist nicht (footprint ...)")
                continue

            if tree[1] != mod.stem:
                rep.error(mod, f"Footprint-Name '{tree[1]}' passt nicht zum Dateinamen '{mod.stem}'", 1)

            layers = set(re.findall(r'\(layer "([^"]+)"', text))
            if not layers & {"F.CrtYd", "B.CrtYd"}:
                rep.warning(mod, "kein Courtyard (F.CrtYd/B.CrtYd)")

            for model in children(tree, "model"):
                path_str = model[1]
                line = line_of(text, f'(model "{path_str}"')
                kind, resolved = resolve_model(path_str, root)
                if kind == "project":
                    rep.warning(mod, f"3D-Modell zeigt ins Projekt statt in die Lib: {path_str}", line)
                    continue
                if kind == "external":
                    continue
                if is_absolute(path_str):
                    absolute.append(mod.stem)
                if resolved.is_file():
                    used_models.add(resolved.resolve())
                else:
                    rep.error(mod, f"3D-Modell fehlt im Repo: 3dmodels/{resolved.relative_to(root / '3dmodels').as_posix()}", line)
        if absolute:
            shown = ", ".join(absolute[:6]) + (" …" if len(absolute) > 6 else "")
            rep.warning(pretty, f"{len(absolute)} Footprint(s) mit absolutem 3D-Modellpfad "
                                f"(nur auf deinem Rechner gültig, im Paket wird er umgeschrieben): {shown}")
    return used_models


def check_models(root: Path, used: set[Path], rep: Report):
    orphans = []
    for f in sorted((root / "3dmodels").rglob("*")):
        if f.is_file() and f.suffix.lower() in MODEL_EXTENSIONS:
            rep.stats["3d models"] += 1
            if f.resolve() not in used:
                orphans.append(rep.rel(f))
    rep.stats["unused 3d models"] = len(orphans)
    return orphans


def check_forbidden(root: Path, rep: Report):
    for pattern in FORBIDDEN_PATTERNS:
        for f in root.rglob(pattern):
            if ".git" in f.parts:
                continue
            rep.error(f, "Datei gehört nicht ins Repo (Backup/Lock/Cache)")


# --------------------------------------------------------------------------
# Ausgabe
# --------------------------------------------------------------------------

def gh_escape(s: str) -> str:
    return s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def emit(rep: Report, orphans: list[str], strict: bool):
    in_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    for f in rep.findings:
        loc = f"{f.file}:{f.line}" if f.line else f.file
        if in_actions:
            level = "error" if f.level == "error" or strict else "warning"
            meta = f"file={f.file}" + (f",line={f.line}" if f.line else "")
            print(f"::{level} {meta}::{gh_escape(f.message)}")
        else:
            print(f"{f.level.upper():7} {loc}: {f.message}")

    errors, warnings = rep.count("error"), rep.count("warning")
    stats = ", ".join(f"{v} {k}" for k, v in sorted(rep.stats.items()))
    print(f"\n{errors} Fehler, {warnings} Warnungen ({stats})")

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    lines = ["## Library-Check", "", f"**{errors} Fehler, {warnings} Warnungen**", "",
             "| | Anzahl |", "|---|---:|"]
    lines += [f"| {k} | {v} |" for k, v in sorted(rep.stats.items())]
    for level, title in (("error", "Fehler"), ("warning", "Warnungen")):
        items = [f for f in rep.findings if f.level == level]
        if items:
            lines += ["", f"### {title}", ""]
            lines += [f"- `{f.file}{':' + str(f.line) if f.line else ''}` {f.message}" for f in items]
    if orphans:
        lines += ["", "<details><summary>3D-Modelle, die kein Footprint nutzt</summary>", ""]
        lines += [f"- `{o}`" for o in orphans]
        lines += ["", "</details>"]
    with open(summary_path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--strict", action="store_true", help="Warnungen wie Fehler behandeln")
    args = ap.parse_args()
    root = args.root.resolve()

    rep = Report(root)
    fp_index = load_footprint_index(root)
    check_symbols(root, fp_index, rep)
    used = check_footprints(root, rep)
    orphans = check_models(root, used, rep)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        check_forbidden(root, rep)

    emit(rep, orphans, args.strict)
    failed = rep.count("error") > 0 or (args.strict and rep.count("warning") > 0)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
