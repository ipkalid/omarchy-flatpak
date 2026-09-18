# Package Store v1.2.0

Flatpak Store now includes matching Flatpak, Brew, and mise views in one native
Omarchy panel. The plugin ID remains `ipkalid.flatpak-store`, preserving existing
installations and Flatpak shortcuts.

- Browse, install, and remove Homebrew formulae. Update All refreshes Homebrew and upgrades formulae.
- Install mise tools by selecting an explicit version or Latest. Select installed versions for removal.
- Keep the familiar bottom-prompt picker layout, with Latest selected beside the prompt and newer versions nearest it.
- Check each provider's dependencies, show installation guidance, and disable only affected actions. Check again refreshes availability.
- Add direct Brew and mise menu shortcuts through the existing explicit menu setup action.
- Keep mise global and project defaults unchanged. Confirm selected formulae or tool versions before removal.
- Cancel pending catalog lookups immediately; keep transaction errors visible.

The square marketing artwork is included as `marketing-square.png`. It is a
conceptual illustration, not a screenshot.

## Update

```sh
omarchy plugin update ipkalid.flatpak-store
omarchy-shell shell summon ipkalid.flatpak-store '{}'
```

Choose **Add menu shortcuts** again to add the new providers. Package managers
are not installed automatically. Brew supports Linux formulae; mise has Install
and Remove actions, with no Update action in this release.

## Validation

The automated suite covers all three providers using stub package commands,
including dependency failures, cancellation, exact version selection, and menu
migration. QML and plugin validation also pass. Package transactions were not
run against the host installation; a full live desktop-panel check remains
outside the sandbox's available display environment.
