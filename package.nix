{
  lib,
  python3Packages,
  wrapQtAppsHook,
  libsecret,
  qtwayland,
  qtsvg,

  # provided by the flake
  src,
  version,
  apscheduler,
}:

python3Packages.buildPythonApplication {
  pname = "tsm-app";
  inherit src version;
  format = "pyproject";

  build-system = with python3Packages; [
    hatchling
    hatch-vcs
  ];

  # metadata for hatch-vcs to derive the version from
  env.HATCH_VCS_PRETEND_VERSION = version;

  dependencies = with python3Packages; [
    aiohttp
    aiosqlite
    apscheduler
    keyring
    pydantic
    pyside6
    pyyaml
    structlog
    tomli-w
    typing-extensions
  ];

  nativeBuildInputs = [ wrapQtAppsHook ];

  buildInputs = [
    libsecret
    qtwayland
  ];

  # Qt SVG rendering for the tray icon and UI graphics
  propagatedBuildInputs = [ qtsvg ];

  pythonImportsCheck = [ "tsm" ];

  # Desktop entry + hicolor icons, mirroring packaging/PKGBUILD
  postInstall = ''
    install -Dm644 $src/packaging/tsm-app.desktop \
      $out/share/applications/tsm-app.desktop
    substituteInPlace $out/share/applications/tsm-app.desktop \
      --replace-fail /usr/bin/tsm-app $out/bin/tsm-app
    for size in 16 32 48 128 256; do
      install -Dm644 $src/tsm/ui/assets/tsm_''${size}.png \
        $out/share/icons/hicolor/''${size}x''${size}/apps/tsm-app.png
    done
  '';

  meta = {
    description = "TradeSkillMaster Desktop App for Linux";
    mainProgram = "tsm-app";
    homepage = "https://github.com/exceptionptr/tsm-app-linux";
    changelog = "https://github.com/exceptionptr/tsm-app-linux/blob/v${version}/CHANGELOG.md";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
  };
}
