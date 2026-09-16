# Publishing and releases

Repository: https://github.com/ipkalid/omarchy-flatpak
Plugin ID: `ipkalid.flatpak-store`
Author: Khalid Alhazmi
License: MIT

Before each release:

1. Update the version in `manifest.json` and document changes in the release notes.
2. Run all verification commands in the README.
3. Check the centered panel, all three actions using package stubs, shortcut setup,
   missing-dependency guidance, Check again, and cancellation during preflight.
4. Check disable/re-enable, shell reload, and menu cleanup. Confirm the plugin
   folder contains no symlinks and `flatpak-store` remains executable.
5. Push the reviewed changes, then create a version tag and GitHub release.

The [marketplace submission form](https://github.com/omacom/omarchy-plugin-marketplace/issues/new?template=submit-plugin.yml)
requires the public repository URL. Use category **System** and tags **System**,
**Launcher**, and **Quickshell**. A **Flatpak** tag can be suggested separately.

Suggested listing summary:

> Install, remove, and update system Flatpak apps from a native Omarchy panel,
> with familiar terminal pickers and normal Flatpak confirmation.

Marketplace validation and maintainer approval are separate from publishing the
repository. See the [publishing guide](https://plugins.omarchy.org/publish.html).
