function validProvider(provider) {
  return provider === "flatpak" || provider === "brew" || provider === "mise";
}

function requestFromPayload(payloadJson) {
  try {
    var payload = JSON.parse(payloadJson || "{}");
    if (!payload || Array.isArray(payload) || typeof payload !== "object") throw new Error("invalid payload");
    var provider = payload.provider === undefined ? "flatpak" : payload.provider;
    if (!validProvider(provider)) throw new Error("invalid provider");
    return { provider: provider, action: validAction(payload.action, provider) ? payload.action : "" };
  } catch (_) {
    return { provider: "flatpak", action: "" };
  }
}

function actionFromPayload(payloadJson) {
  return requestFromPayload(payloadJson).action;
}

function validAction(action, provider) {
  provider = provider === undefined ? "flatpak" : provider;
  return validProvider(provider) && (action === "install" || action === "remove" || (action === "update" && provider !== "mise"));
}

function validDependencies(dependencies) {
  return !!dependencies && ["flatpak", "brew", "mise", "fzf", "python3", "timeout", "xdg-terminal-exec"].every(function(name) {
    return typeof dependencies[name] === "boolean";
  });
}

function requirementsFor(action, provider) {
  provider = provider === undefined ? "flatpak" : provider;
  if (!validAction(action, provider)) return [];
  var required = [provider, "xdg-terminal-exec"];
  if (provider !== "flatpak") required.push("python3");
  if (action !== "update") required.push("fzf", "timeout");
  return required;
}

function canLaunch(action, dependencies, provider) {
  return validAction(action, provider) && !!dependencies && requirementsFor(action, provider).every(function(name) {
    return dependencies[name] === true;
  });
}

function isCurrent(request, generation, opened) {
  return opened && request === generation;
}

function dependencyMessage(dependencies, provider) {
  if (!dependencies) return "";
  provider = provider === undefined ? "flatpak" : provider;
  var messages = [];
  if (!dependencies[provider]) {
    if (provider === "brew") messages.push("Homebrew was not found on PATH or in the usual Linux install locations.\nFor a custom install, expose brew on the desktop PATH or set HOMEBREW_PREFIX. Otherwise install it using https://brew.sh, then check again.");
    else messages.push((provider === "mise" ? "mise" : "Flatpak") + " is not installed.\nInstall in a terminal: omarchy pkg add " + provider);
  }
  if (!dependencies.fzf) messages.push("fzf is required for Install and Remove.\nInstall in a terminal: omarchy pkg add fzf");
  if (!dependencies.timeout) messages.push("timeout is required for Install and Remove.\nInstall in a terminal: omarchy pkg add coreutils");
  if (!dependencies["xdg-terminal-exec"]) messages.push("A terminal launcher is required for package actions.\nInstall in a terminal: omarchy pkg add xdg-terminal-exec");
  if (!dependencies.python3) messages.push((provider === "flatpak" ? "Python is required to add menu shortcuts." : "Python is required for " + (provider === "brew" ? "Brew" : "mise") + " actions and menu shortcuts.") + "\nInstall in a terminal: omarchy pkg add python");
  return messages.join("\n\n");
}

function commandFor(action, scriptPath, provider) {
  provider = provider === undefined ? "flatpak" : provider;
  if (!validAction(action, provider) || !scriptPath || scriptPath.charAt(0) !== "/") return [];
  var command = ["xdg-terminal-exec", "--app-id=org.omarchy.terminal", "bash", scriptPath];
  if (action !== "install") command.push(action);
  return command;
}
