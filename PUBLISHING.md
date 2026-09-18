# Publishing and releases

Repository: https://github.com/ipkalid/omarchy-flatpak
Plugin ID: `ipkalid.flatpak-store`
Author: Khalid Alhazmi
License: MIT

Before each release:

1. Update the version in `manifest.json` and document changes in the release notes.
2. Run all verification commands in the README.
3. Check the centered panel, all three provider views using package stubs, shortcut setup,
   missing-dependency guidance, Check again, and cancellation during preflight.
4. Check disable/re-enable, shell reload, and menu cleanup. Confirm the plugin
   folder contains no symlinks and `flatpak-store`, `brew-store`, and `mise-store` remain executable.
5. Push the reviewed changes, then create a version tag and GitHub release.

The [marketplace submission form](https://github.com/omacom/omarchy-plugin-marketplace/issues/new?template=submit-plugin.yml)
requires the public repository URL. Use category **System** and tags **System**,
**Launcher**, and **Quickshell**. A **Flatpak** tag can be suggested separately.

Suggested listing summary:

> Manage Flatpak apps, Homebrew formulae, and mise tool versions from one native
> Omarchy panel, with familiar terminal pickers and version selection.

Marketplace validation and maintainer approval are separate from publishing the
repository. See the [publishing guide](https://plugins.omarchy.org/publish.html).

For an existing marketplace listing, use the **Plugin verification** form and
select **Verify and publish a newer upstream commit**. Submit the existing plugin
ID, repository URL, and full SHA of the pushed HEAD. Marketplace metadata is
promoted only after the maintainers approve that exact commit; pushing a release
does not immediately replace the listed snapshot. See the
[existing-listing update instructions](https://github.com/omacom/omarchy-plugin-marketplace/blob/main/SUBMISSION.md#update-an-existing-listing).

The square release artwork is `marketing-square.png`; its generation prompt and
illustration disclosure are recorded in `marketing-square.prompt.md`.
