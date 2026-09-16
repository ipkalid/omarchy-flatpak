function actionFromPayload(payloadJson) {
  try {
    var payload = JSON.parse(payloadJson || "{}");
    if (!payload || Array.isArray(payload) || typeof payload !== "object") return "";
    return validAction(payload.action) ? payload.action : "";
  } catch (_) {
    return "";
  }
}

function validAction(action) {
  return action === "install" || action === "remove" || action === "update";
}

function canLaunch(action, dependencies) {
  return validAction(action) && !!dependencies && dependencies.flatpak === true
    && (action === "update" || dependencies.fzf === true);
}

function isCurrent(request, generation, opened) {
  return opened && request === generation;
}

function dependencyMessage(dependencies) {
  if (!dependencies) return "";
  var messages = [];
  if (!dependencies.flatpak) messages.push("Flatpak is not installed.\nInstall in a terminal: omarchy pkg add flatpak");
  if (!dependencies.fzf) messages.push("fzf is required for Install and Remove.\nInstall in a terminal: omarchy pkg add fzf");
  if (!dependencies.python3) messages.push("Python is required to add menu shortcuts.\nInstall in a terminal: omarchy pkg add python");
  return messages.join("\n\n");
}

function commandFor(action, scriptPath) {
  if (!validAction(action) || !scriptPath || scriptPath.charAt(0) !== "/") return [];
  var command = ["xdg-terminal-exec", "--app-id=org.omarchy.terminal", "bash", scriptPath];
  if (action !== "install") command.push(action);
  return command;
}
