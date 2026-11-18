# Dev environment for keycap-legends on NixOS.
#
# This repo is driven by `uv`, which downloads a generic (non-Nix) Python and
# installs manylinux wheels (OCP/OpenCASCADE, VTK, SciPy). Those binaries need a
# standard FHS layout and glibc loader, which NixOS does not provide out of the
# box. buildFHSEnv gives us that layout plus the shared libraries the wheels
# dlopen, so `uv run ...` works unchanged.
#
#   nix-shell                     # enter the env
#   uv sync                       # first time: install deps into ./.venv
#   uv run main.py --config ...   # generate (see README / commands below)
#
{ pkgs ? import <nixpkgs> { } }:

let
  # Iosevka Nerd Font Mono for the legends (OCCT family name "Iosevka NFM").
  iosevka = pkgs.nerd-fonts.iosevka;
in
(pkgs.buildFHSEnv {
  name = "keycap-legends";

  targetPkgs = p: (with p; [
    uv
    git
    bashInteractive
    coreutils

    # Fonts
    iosevka
    fontconfig
    freetype

    # C/C++ runtime for the native wheels
    stdenv.cc.cc.lib      # libstdc++, libgcc_s
    zlib
    glib
    expat
    openssl
    libffi
    bzip2
    xz
    sqlite
    ncurses
    readline
    util-linux            # libuuid

    # OpenGL / Mesa (VTK)
    libGL
    libGLU
    libglvnd

    # X11 stack (OCCT font/text + VTK)
    xorg.libX11
    xorg.libXext
    xorg.libXrender
    xorg.libXrandr
    xorg.libXfixes
    xorg.libXcursor
    xorg.libXi
    xorg.libXinerama
    xorg.libXxf86vm
    xorg.libxcb
    xorg.libXau
    xorg.libXdmcp
    xorg.libSM
    xorg.libICE
    xorg.libXt
    xorg.libXmu
    libxkbcommon
    dbus
  ]);

  # OCCT finds fonts via CSF_MyFontsDirectory (it ignores fontconfig). Point it
  # at the user font directory where fonts are installed.
  profile = ''
    export CSF_MyFontsDirectory="$HOME/.local/share/fonts"
    export UV_PYTHON_PREFERENCE=only-managed
    echo "keycap-legends env ready. Fonts: ~/.local/share/fonts. Try: uv sync && uv run main.py --help"
  '';

  runScript = "bash";
}).env
