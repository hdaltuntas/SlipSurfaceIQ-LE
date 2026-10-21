# Native installation packages

The **Native packages** GitHub Actions workflow builds x86-64 installers containing
Python 3.12, Qt and the scientific libraries. Users do not need to install Python
or run pip. Download the installers from the matching GitHub release:

https://github.com/hdaltuntas/SlipSurfaceIQ-LE/releases

| System | Package | Install |
| --- | --- | --- |
| Windows 10/11, x64 | `SlipSurfaceIQ-LE-2026.1.1-windows-x64.msi` | Double-click the MSI, or `msiexec /i SlipSurfaceIQ-LE-2026.1.1-windows-x64.msi` |
| Ubuntu 24.04 or newer, amd64 | `slipsurface-iq-le_2026.1.1-1_ubuntu24.04_amd64.deb` | `sudo apt install ./slipsurface-iq-le_2026.1.1-1_ubuntu24.04_amd64.deb` |
| Fedora 44 or newer, x86_64 | `slipsurface-iq-le-2026.1.1-1.fedora.x86_64.rpm` | `sudo dnf install ./slipsurface-iq-le-2026.1.1-1.fedora.x86_64.rpm` |
| openSUSE Leap 16 / current Tumbleweed, x86_64 | `slipsurface-iq-le-2026.1.1-1.opensuse.x86_64.rpm` | `sudo zypper install ./slipsurface-iq-le-2026.1.1-1.opensuse.x86_64.rpm` |
| Current Arch Linux, x86_64 | `slipsurface-iq-le-2026.1.1-1-x86_64.pkg.tar.zst` | `sudo pacman -U ./slipsurface-iq-le-2026.1.1-1-x86_64.pkg.tar.zst` |

The MSI is unsigned. RPM packages are not signed with a distribution signing key;
zypper may ask whether to accept an unsigned package. Compare downloads against
the release's `SHA256SUMS` (`sha256sum -c SHA256SUMS --ignore-missing` on Linux;
`Get-FileHash <file> -Algorithm SHA256` on Windows). Checksums detect corruption;
they are not a replacement for code signing.

Linux builds require glibc 2.39 or newer and an X11/XWayland desktop. Qt desktop
libraries are installed by apt/dnf/zypper/pacman through package dependencies.
The workflow tests Ubuntu 24.04, Fedora 44, openSUSE Leap 16 and current Arch Linux.
Tumbleweed uses the openSUSE RPM but is not a separate package build target.
These packages do not target openSUSE Leap 15 or SUSE Linux Enterprise 15.

Start **SlipSurfaceIQ LE** from the application menu, or run `slipsurface` on Linux.
The Windows installation is under `Program Files/SlipSurfaceIQ LE`; Linux uses
`/opt/slipsurface-iq-le` and `/usr/bin/slipsurface`. Uninstall through Windows
Installed Apps or your distribution's package manager. Projects and per-user
settings are not removed by the installer.

## Build and verification

Use a clean Python 3.12 virtual environment on Windows x64 or Ubuntu 24.04 x64:

```sh
python -m pip install -r packaging/requirements.txt
python packaging/build.py freeze
```

On Ubuntu, install the runtime libraries listed in `DEB_REQUIRES` in `build.py`,
then run `python packaging/build.py linux`. This creates the DEB and a shared
payload with generated RPM and Arch recipes under `dist/`. The workflow runs
`rpmbuild` inside Fedora/openSUSE and `makepkg` as an unprivileged Arch user.

On Windows, install the .NET SDK and WiX (`dotnet tool install --global wix
--version 5.0.2`), then run `python packaging/build.py msi`. MSI's numeric version
maps `2026.1.1` to `26.1.1` because Windows Installer limits its major field to 255.
The package title and application retain the complete calendar version. A stable
UpgradeCode allows future MSI versions to replace this installation.

All five packages are installed and uninstalled by CI. The installed executable
is run from a directory outside the checkout and checks a reference calculation,
project save/load, DXF save/load, PDF generation with the bundled Turkish-capable
font, QtAwesome resources and the real modeler window. Linux checks use Xvfb with
the `xcb` platform plugin, not just Qt's headless plugin.

Pull requests build and test artifacts without publishing. Packaging changes on
`main`, published-release events, or a manual run with **publish** enabled attach
the verified files to the **existing** release matching `slipsurface.__version__`.
Publication refuses application code that differs from the release tag, waits for
every package test, and does not overwrite existing release assets. Packaging
changes after a tag are recorded separately in `BUILD-INFO.txt`; the matching
complete source and build recipes are attached as `*-package-source.tar.gz`.
Per-bundle dependency versions and upstream license notices are included in the
installation. Frozen libraries remain separate files; UPX and stripping are disabled.

The workflow needs `contents: write` only in the final publication job. No extra
repository secret is required. MSI signing can be added when a certificate is
available; no signing credentials are stored in the repository.
