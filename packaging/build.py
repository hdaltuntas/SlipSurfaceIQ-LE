"""Build native installers around a PyInstaller directory, without root/pip at runtime."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
DIST = ROOT / "dist"
UPGRADE_CODE = "E1713564-112B-5B18-89C9-24B6D123E784"
URL = "https://github.com/hdaltuntas/SlipSurfaceIQ-LE"


def version() -> str:
    tree = ast.parse((ROOT / "slipsurface/__init__.py").read_text(encoding="utf-8"))
    for item in tree.body:
        if isinstance(item, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__version__" for target in item.targets
        ):
            value = ast.literal_eval(item.value)
            parts = value.split(".")
            if len(parts) == 3 and all(part.isdecimal() for part in parts):
                return value
    raise ValueError("Expected a stable year.minor.patch version")


def msi_version(value: str) -> str:
    # Windows Installer limits major/minor to 255; calendar year 2026 is invalid.
    year, minor, patch = map(int, value.split("."))
    if not (2000 <= year <= 2255 and 0 <= minor <= 255 and 0 <= patch <= 65535):
        raise ValueError("Version cannot be represented by Windows Installer")
    return f"{year - 2000}.{minor}.{patch}"


def run(*args: str, **kwargs) -> None:
    subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def licenses() -> None:
    target = BUILD / "licenses"
    target.mkdir(parents=True, exist_ok=True)
    dependencies = {}
    for dist in importlib.metadata.distributions():
        name = dist.metadata["Name"]
        dependencies[name] = dist.version
        for file in dist.files or []:
            if any(
                word in part.lower()
                for part in file.parts
                for word in ("license", "licence", "copying", "notice")
            ):
                source = Path(dist.locate_file(file))
                if source.is_file():
                    # Flatten safely, preserving distinct upstream notices.
                    dest = target / name / str(file).replace("/", "_").replace("\\", "_")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, dest)
    shutil.copyfile(ROOT / "LICENSE", target / "SlipSurfaceIQ-LE-LICENSE.txt")
    (target / "dependencies.json").write_text(
        json.dumps(dependencies, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def icons() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(ROOT))
    from PySide6.QtWidgets import QApplication

    from slipsurface.ui.icons import icon

    app = QApplication.instance() or QApplication([])
    pixmap = icon("interpret").pixmap(256, 256)
    if not pixmap.save(str(BUILD / "slipsurface.png")):
        raise RuntimeError("Cannot generate package icon")
    from PIL import Image

    with Image.open(BUILD / "slipsurface.png") as image:
        image.save(BUILD / "slipsurface.ico", sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
    app.quit()


def freeze() -> None:
    BUILD.mkdir(exist_ok=True)
    licenses()
    icons()
    run(
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        str(ROOT / "packaging/slipsurface.spec"),
    )
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    manifest = {
        "version": version(),
        "source_commit": revision,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "dependencies": json.loads((BUILD / "licenses/dependencies.json").read_text()),
    }
    (DIST / "slipsurface/build-info.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


DEB_REQUIRES = (
    "libc6 (>= 2.39), libgl1, libegl1, libxkbcommon-x11-0, libfontconfig1, "
    "libdbus-1-3, libglib2.0-0t64, libx11-6, libxcb-cursor0, libxcb-icccm4, "
    "libxcb-image0, libxcb-keysyms1, libxcb-render-util0, libxcb-xinerama0, libxcb-xkb1"
)
RPM_REQUIRES = {
    "fedora": "glibc >= 2.39, libglvnd-egl, libglvnd-glx, libxkbcommon-x11, fontconfig, "
    "dbus-libs, glib2, libX11, xcb-util-cursor, xcb-util-wm, xcb-util-image, "
    "xcb-util-keysyms, xcb-util-renderutil",
    "opensuse": "glibc >= 2.39, libglvnd, libxkbcommon-x11-0, fontconfig, libdbus-1-3, "
    "libglib-2_0-0, libX11-6, libxcb-cursor0, libxcb-icccm4, libxcb-image0, "
    "libxcb-keysyms1, libxcb-render-util0, libxcb-xinerama0, libxcb-xkb1",
}


def linux() -> None:
    staging = BUILD / "payload"
    if staging.exists():
        shutil.rmtree(staging)
    app = staging / "opt/slipsurface-iq-le"
    shutil.copytree(DIST / "slipsurface", app, symlinks=True)
    (staging / "usr/bin").mkdir(parents=True)
    (staging / "usr/bin/slipsurface").symlink_to("/opt/slipsurface-iq-le/slipsurface")
    for source, destination in (
        (
            ROOT / "packaging/linux/slipsurface.desktop",
            "usr/share/applications/slipsurface.desktop",
        ),
        (BUILD / "slipsurface.png", "usr/share/icons/hicolor/256x256/apps/slipsurface-iq-le.png"),
        (ROOT / "LICENSE", "usr/share/licenses/slipsurface-iq-le/LICENSE"),
    ):
        dest = staging / destination
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
    archive = DIST / "payload.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(staging, arcname="payload")
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    pkgbuild = (ROOT / "packaging/linux/PKGBUILD").read_text()
    (DIST / "PKGBUILD").write_text(
        pkgbuild.replace("@VERSION@", version()).replace("@SHA256@", checksum)
    )
    for distro, requires in RPM_REQUIRES.items():
        spec = (ROOT / "packaging/linux/slipsurface.spec.in").read_text()
        spec = spec.replace("@VERSION@", version()).replace("@REQUIRES@", requires)
        (DIST / f"{distro}.spec").write_text(spec)
    size = (
        sum(
            path.stat().st_size
            for path in staging.rglob("*")
            if path.is_file() and not path.is_symlink()
        )
        // 1024
    )
    (staging / "DEBIAN").mkdir()
    (staging / "DEBIAN/control").write_text(
        f"Package: slipsurface-iq-le\nVersion: {version()}-1\nArchitecture: amd64\n"
        "Maintainer: Hasan Deniz Altuntaş <hdaltuntas@gmail.com>\n"
        f"Installed-Size: {size}\nDepends: {DEB_REQUIRES}\nSection: science\nPriority: optional\n"
        f"Homepage: {URL}\nDescription: 2D limit equilibrium slope stability analysis\n"
        " Desktop CAD application with bundled Python, Qt and scientific libraries.\n",
        encoding="utf-8",
    )
    run(
        "dpkg-deb",
        "--root-owner-group",
        "--build",
        str(staging),
        str(DIST / f"slipsurface-iq-le_{version()}-1_ubuntu24.04_amd64.deb"),
    )


def wix_document(bundle: Path) -> ET.Element:
    ns = "http://wixtoolset.org/schemas/v4/wxs"
    ET.register_namespace("", ns)

    def add(parent, tag, **attrs):
        return ET.SubElement(parent, f"{{{ns}}}{tag}", attrs)

    def identifier(prefix, path):
        return prefix + hashlib.sha256(str(path).encode()).hexdigest()[:24]

    root = ET.Element(f"{{{ns}}}Wix")
    package = add(
        root,
        "Package",
        Name=f"SlipSurfaceIQ LE {version()}",
        Manufacturer="Hasan Deniz Altuntaş",
        Version=msi_version(version()),
        UpgradeCode=UPGRADE_CODE,
        Language="1033",
        Scope="perMachine",
        Compressed="yes",
    )
    add(package, "MajorUpgrade", DowngradeErrorMessage="A newer version is already installed.")
    add(package, "MediaTemplate", EmbedCab="yes", CompressionLevel="high")
    add(package, "Icon", Id="ProductIcon", SourceFile=str(BUILD / "slipsurface.ico"))
    add(package, "Property", Id="ARPPRODUCTICON", Value="ProductIcon")
    add(package, "Property", Id="ARPURLINFOABOUT", Value=URL)
    program_files = add(package, "StandardDirectory", Id="ProgramFiles64Folder")
    install = add(program_files, "Directory", Id="INSTALLFOLDER", Name="SlipSurfaceIQ LE")
    feature = add(package, "Feature", Id="Application", Title="SlipSurfaceIQ LE", Level="1")
    directories = {Path("."): install}
    executable_id = None
    for file in sorted(bundle.rglob("*")):
        relative = file.relative_to(bundle)
        if file.is_dir():
            directories[relative] = add(
                directories[relative.parent],
                "Directory",
                Id=identifier("D", relative),
                Name=file.name,
            )
        else:
            component_id = identifier("C", relative)
            component = add(
                directories[relative.parent],
                "Component",
                Id=component_id,
                Guid=str(uuid.uuid5(uuid.UUID(UPGRADE_CODE), relative.as_posix())),
                Bitness="always64",
            )
            file_id = identifier("F", relative)
            add(component, "File", Id=file_id, Source=str(file.resolve()), KeyPath="yes")
            add(feature, "ComponentRef", Id=component_id)
            if relative.as_posix() == "slipsurface.exe":
                executable_id = file_id
    if executable_id is None:
        raise ValueError("Missing frozen slipsurface.exe")
    menu = add(package, "StandardDirectory", Id="ProgramMenuFolder")
    folder = add(menu, "Directory", Id="AppMenu", Name="SlipSurfaceIQ LE")
    shortcut = add(folder, "Component", Id="ApplicationShortcut", Guid="*", Bitness="always64")
    add(
        shortcut,
        "Shortcut",
        Id="StartMenuShortcut",
        Name="SlipSurfaceIQ LE",
        Target=f"[#{executable_id}]",
        WorkingDirectory="INSTALLFOLDER",
        Icon="ProductIcon",
    )
    add(shortcut, "RemoveFolder", Id="RemoveAppMenu", On="uninstall")
    add(
        shortcut,
        "RegistryValue",
        Root="HKLM",
        Key="Software\\SlipSurfaceIQ LE",
        Name="Installed",
        Type="integer",
        Value="1",
        KeyPath="yes",
    )
    add(feature, "ComponentRef", Id="ApplicationShortcut")
    return root


def msi() -> None:
    document = wix_document(DIST / "slipsurface")
    ET.indent(document)
    source = BUILD / "installer.wxs"
    ET.ElementTree(document).write(source, encoding="utf-8", xml_declaration=True)
    run(
        "wix",
        "build",
        str(source),
        "-arch",
        "x64",
        "-pdbtype",
        "none",
        "-o",
        str(DIST / f"SlipSurfaceIQ-LE-{version()}-windows-x64.msi"),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["freeze", "linux", "msi", "version"])
    command = parser.parse_args().command
    if command == "version":
        print(version())
    else:
        {"freeze": freeze, "linux": linux, "msi": msi}[command]()
