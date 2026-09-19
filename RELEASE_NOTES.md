# Package Store (unreleased)

- Brew install and remove now include casks alongside formulae. The install
  catalog merges locally tapped casks with the full API catalog, rows are
  labelled Formula/Cask in the details pane, previews query the right kind,
  and mixed selections run one brew command per kind (brew rejects mixing
  formulae and casks in a single transaction). `brew upgrade` already
  upgrades both kinds, so Update All is unchanged.
- Validated with 67 tests.

# Package Store v1.2.1

Fix Brew being reported as missing when Omarchy's desktop PATH does not include
an existing Homebrew installation.

- Use the same Brew discovery in the dependency probe and terminal launcher.
- Respect Brew already on PATH; otherwise check `HOMEBREW_PREFIX`,
  `/home/linuxbrew/.linuxbrew`, and `~/.linuxbrew`.
- Keep environment changes local to the Brew action. Shell configuration and
  the other providers are unchanged.
- Improve guidance for custom Homebrew installations.

Update with `omarchy plugin update ipkalid.flatpak-store`, reopen Package Store,
and choose **Check again** in the Brew view. No Homebrew reinstall is needed.

Validated with 65 tests, QML and plugin validation, Bash syntax, and ShellCheck.
The dependency probe was also checked with only `/usr/bin:/bin` on PATH and
correctly detected the installed Linuxbrew prefix.

See [v1.2.0](https://github.com/ipkalid/omarchy-flatpak/releases/tag/v1.2.0)
for the original Brew/mise feature release and square marketing artwork.
