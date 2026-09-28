#!/usr/bin/env python3
"""Baut aus der Library ein Paket für den KiCad Plugin and Content Manager (PCM).

Erzeugt in --out:
  <slug>-<version>.zip   das Paket (metadata.json, symbols/, footprints/, 3dmodels/)
  packages.json          PCM-Paketliste mit Download-URL und SHA-256
  repository.json        PCM-Repository; diese URL trägt man in KiCad ein

Beim Packen werden zwei Dinge umgeschrieben, damit die Lib nach der
Installation über den PCM funktioniert:
  * 3D-Modellpfade, die in 3dmodels/ dieses Repos zeigen (auch absolute wie
    S:/.../3dmodels/...), werden zu ${KICAD10_3RD_PARTY}/3dmodels/<id>/...
  * Footprint-Felder der Symbole ("Tiro_X:Name") bekommen das Library-Präfix,
    das der PCM beim Eintragen in die Library-Tabellen vergibt ("PCM_Tiro_X").

    python3 .github/scripts/build_package.py --version 2026.928.1 --status development \\
        --download-base https://github.com/OWNER/REPO/releases/download/nightly
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True  # kein __pycache__ im Repo
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_library import MODEL_EXTENSIONS, resolve_model  # noqa: E402

SCHEMA_URL = "https://go.kicad.org/pcm/schemas/v1"
# Feste Zeitstempel im ZIP, damit gleicher Inhalt dieselbe Prüfsumme ergibt.
ZIP_DATE = (2020, 1, 1, 0, 0, 0)


def package_identifier(repo: str) -> str:
    owner, name = repo.lower().split("/", 1)
    ident = f"com.github.{owner}.{name}"
    ident = re.sub(r"[^a-z0-9.-]+", "-", ident).strip("-.")
    return ident[:100]


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def rewrite_footprint(text: str, root: Path, model_base: str) -> str:
    def repl(m: re.Match) -> str:
        kind, resolved = resolve_model(m.group(1), root)
        if kind != "repo":
            return m.group(0)
        rel = resolved.relative_to(root / "3dmodels").as_posix()
        return f'(model "{model_base}/{rel}"'

    return re.sub(r'\(model "([^"]+)"', repl, text)


def rewrite_symbols(text: str, lib_prefix: str, nick_prefix: str) -> str:
    if not nick_prefix:
        return text
    return re.sub(
        rf'(\(property\s+"Footprint"\s+"){re.escape(lib_prefix)}',
        lambda m: m.group(1) + nick_prefix + lib_prefix,
        text,
    )


def add_file(zf: zipfile.ZipFile, arcname: str, data: bytes) -> int:
    info = zipfile.ZipInfo(arcname, ZIP_DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    zf.writestr(info, data)
    return len(data)


def read_text(path: Path) -> str:
    # newline="" erhält CRLF/LF so, wie es in der Datei steht.
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def build(args) -> int:
    root = args.root.resolve()
    cfg = json.loads((root / ".github" / "pcm" / "package.json").read_text(encoding="utf-8"))
    repo = args.repo
    owner = repo.split("/", 1)[0]
    ident = package_identifier(repo)
    kicad_major = cfg["kicad_version"].split(".")[0]
    # Der PCM installiert 3D-Modelle nach 3rdparty/3dmodels/<identifier mit '_' statt '.'>/
    model_base = f"${{KICAD{kicad_major}_3RD_PARTY}}/3dmodels/{ident.replace('.', '_')}"
    nick_prefix = cfg.get("lib_nickname_prefix", "PCM_")

    homepage = f"{args.server_url}/{repo}"
    version_entry = {
        "version": args.version,
        "status": args.status,
        "kicad_version": cfg["kicad_version"],
    }
    metadata = {
        "$schema": SCHEMA_URL,
        "name": cfg["name"] + (" (Nightly)" if args.status == "development" else ""),
        "description": cfg["description"],
        "description_full": cfg["description_full"],
        "identifier": ident,
        "type": "library",
        "author": {"name": owner, "contact": {"github": f"{args.server_url}/{owner}"}},
        "license": cfg["license"],
        "resources": {"homepage": homepage},
        "tags": cfg["tags"],
        "versions": [version_entry],
    }

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    zip_path = out / f"{slugify(cfg['name'])}-{args.version}.zip"

    install_size = 0
    counts = {"symbol libs": 0, "footprints": 0, "3d models": 0, "rewritten model paths": 0}
    with zipfile.ZipFile(zip_path, "w") as zf:
        meta_bytes = (json.dumps(metadata, indent=2, ensure_ascii=False) + "\n").encode()
        install_size += add_file(zf, "metadata.json", meta_bytes)

        for lib in sorted((root / "symbols").glob("*.kicad_sym")):
            text = rewrite_symbols(read_text(lib), "Tiro_", nick_prefix)
            install_size += add_file(zf, f"symbols/{lib.name}", text.encode("utf-8"))
            counts["symbol libs"] += 1

        for pretty in sorted((root / "footprints").glob("*.pretty")):
            for mod in sorted(pretty.glob("*.kicad_mod")):
                original = read_text(mod)
                text = rewrite_footprint(original, root, model_base)
                counts["rewritten model paths"] += sum(
                    1 for a, b in zip(re.findall(r'\(model "[^"]+"', original),
                                      re.findall(r'\(model "[^"]+"', text)) if a != b)
                install_size += add_file(zf, f"footprints/{pretty.name}/{mod.name}", text.encode("utf-8"))
                counts["footprints"] += 1

        for f in sorted((root / "3dmodels").rglob("*")):
            if f.is_file() and f.suffix.lower() in MODEL_EXTENSIONS:
                rel = f.relative_to(root / "3dmodels").as_posix()
                install_size += add_file(zf, f"3dmodels/{rel}", f.read_bytes())
                counts["3d models"] += 1

    zip_bytes = zip_path.read_bytes()
    base = args.download_base.rstrip("/") if args.download_base else None
    if base:
        version_entry["download_url"] = f"{base}/{zip_path.name}"
    version_entry["download_sha256"] = hashlib.sha256(zip_bytes).hexdigest()
    version_entry["download_size"] = len(zip_bytes)
    version_entry["install_size"] = install_size

    packages = {"packages": [metadata]}
    packages_bytes = (json.dumps(packages, indent=2, ensure_ascii=False) + "\n").encode()
    (out / "packages.json").write_bytes(packages_bytes)

    now = int(time.time())
    repository = {
        "$schema": SCHEMA_URL,
        "name": f"{cfg['name']} ({'Nightly' if args.status == 'development' else 'Releases'})",
        "maintainer": metadata["author"],
        "packages": {
            "url": f"{base}/packages.json" if base else "file:///packages.json",
            "sha256": hashlib.sha256(packages_bytes).hexdigest(),
            "update_timestamp": now,
            "update_time_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now)),
        },
    }
    (out / "repository.json").write_text(json.dumps(repository, indent=2, ensure_ascii=False) + "\n",
                                         encoding="utf-8")

    if args.validate:
        validate(out, metadata, packages, repository)

    print(f"Paket:      {zip_path}")
    print(f"Identifier: {ident}")
    print(f"Version:    {args.version} ({args.status})")
    print("Inhalt:     " + ", ".join(f"{v} {k}" for k, v in counts.items()))
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as fh:
            fh.write(f"zip={zip_path}\nzip_name={zip_path.name}\n")
    return 0


def validate(out: Path, metadata: dict, packages: dict, repository: dict):
    """Prüft die JSON-Dateien gegen das offizielle PCM-Schema (braucht jsonschema)."""
    import urllib.request

    import jsonschema

    # Ohne eigenen User-Agent antwortet go.kicad.org mit 403.
    req = urllib.request.Request(SCHEMA_URL, headers={"User-Agent": "tiro-kicad-lib-ci"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        schema = json.load(resp)
    defs = schema["definitions"]

    def check(obj, ref, what):
        sub = {"$ref": f"#/definitions/{ref}", "definitions": defs}
        try:
            jsonschema.validate(obj, sub)
        except jsonschema.ValidationError as exc:
            sys.exit(f"{what} verletzt das PCM-Schema: {exc.message} (bei {list(exc.absolute_path)})")

    check(metadata, "Package", "metadata.json")
    check(packages, "PackageArray", "packages.json")
    check(repository, "Repository", "repository.json")
    print("Schema:     metadata.json, packages.json, repository.json gültig")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--version", required=True, help="major[.minor[.patch]], z.B. 1.2.0")
    ap.add_argument("--status", default="stable", choices=["stable", "testing", "development"])
    ap.add_argument("--out", type=Path, default=Path("dist"))
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "Tiro1999/KiCAD_myPartLib"),
                    help="owner/name des GitHub-Repos")
    ap.add_argument("--server-url", default=os.environ.get("GITHUB_SERVER_URL", "https://github.com"))
    ap.add_argument("--download-base", help="URL, unter der ZIP und packages.json veröffentlicht werden")
    ap.add_argument("--validate", action="store_true", help="gegen das PCM-Schema prüfen")
    args = ap.parse_args()

    if not re.fullmatch(r"\d{1,4}(\.\d{1,4}(\.\d{1,6})?)?", args.version):
        ap.error(f"Version '{args.version}' passt nicht zum PCM-Format major[.minor[.patch]]")
    return build(args)


if __name__ == "__main__":
    sys.exit(main())
