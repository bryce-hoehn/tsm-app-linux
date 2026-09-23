{
  description = "TSM Desktop App for Linux - TradeSkillMaster auction data downloader";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python314;
        tsmVersion = "1.1.11";

        # apscheduler 4.x prerelease (upstream nixpkgs only has 3.x)
        apscheduler4 = python.pkgs.buildPythonPackage rec {
          pname = "apscheduler";
          version = "4.0.0a6";
          pyproject = true;
          src = pkgs.fetchPypi {
            inherit pname version;
            hash = "sha256-UTRhfAKPCX3koJq77vxCYlywzjrctM5J10zCYFQIR2E=";
          };
          build-system = with python.pkgs; [
            setuptools
            setuptools-scm
          ];
          # sdist has no git metadata for setuptools-scm to read
          env.SETUPTOOLS_SCM_PRETEND_VERSION = version;
          dependencies = with python.pkgs; [
            anyio
            attrs
            tenacity
            tzlocal
          ];
          pythonImportsCheck = [ "apscheduler" ];
        };
        tsm-app = pkgs.callPackage ./package.nix {
          inherit pkgs;
          python3Packages = python.pkgs;
          src = self;
          version = tsmVersion;
          apscheduler = apscheduler4;
        };
      in
      {
        packages.default = tsm-app;
        packages.tsm-app = tsm-app;

        apps.default = {
          type = "app";
          program = "${tsm-app}/bin/tsm-app";
        };

        devShells.default = pkgs.mkShell {
          packages =
            with pkgs;
            [
              ruff
              mypy
            ]
            ++ (with python.pkgs; [
              pytest
              pytest-asyncio
              aioresponses
            ])
            ++ tsm-app.dependencies
            ++ tsm-app.build-system;
          shellHook = ''
            export HATCH_VCS_PRETEND_VERSION=${tsmVersion}
          '';
        };
      }
    );
}
