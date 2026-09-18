#!/usr/bin/env bash
# Shared by the read-only Brew probe and its launcher. Never run brew shellenv
# or source shell startup files: desktop processes often have a smaller PATH.
configure_brew_path() {
  command -v brew >/dev/null 2>&1 && return 0
  local prefix
  for prefix in "${HOMEBREW_PREFIX:-}" /home/linuxbrew/.linuxbrew "${HOME:-}/.linuxbrew"; do
    [[ $prefix == /* && -x "$prefix/bin/brew" ]] || continue
    export PATH="$prefix/bin:$prefix/sbin${PATH:+:$PATH}"
    return 0
  done
  # Discovery is optional; the usual dependency checks explain what is missing.
  return 0
}
