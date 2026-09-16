pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import qs.Commons
import qs.Ui as Ui
import "Actions.js" as Actions

Ui.Panel {
  id: root
  property var manifest: null
  moduleName: manifest && manifest.id ? manifest.id : "ipkalid.flatpak-store"
  manageIpc: false
  property int selectedIndex: 0
  readonly property var fonts: Style.font
  readonly property string scriptPath: decodeURIComponent(Qt.resolvedUrl("flatpak-store").toString().replace(/^file:\/\//, ""))
  readonly property string menuPath: decodeURIComponent(Qt.resolvedUrl("menu.py").toString().replace(/^file:\/\//, ""))
  readonly property string probePath: decodeURIComponent(Qt.resolvedUrl("check-dependencies").toString().replace(/^file:\/\//, ""))
  property var dependencies: null
  property int generation: 0
  property bool checking: false
  property bool menuBusy: false
  property bool settingUp: false
  property string menuState: "unknown"
  property string menuError: ""
  property string probeError: ""
  readonly property string guidance: [probeError, Actions.dependencyMessage(dependencies), menuError].filter(function(text) { return !!text }).join("\n\n")
  readonly property var actions: [
    { action: "install", title: "Install", detail: "Find apps on Flathub", icon: "󰏖" },
    { action: "remove", title: "Remove", detail: "Uninstall apps; keep saved data", icon: "󰭌" },
    { action: "update", title: "Update All", detail: "Update system apps and runtimes", icon: "󰚰" },
    { action: "setup", title: settingUp ? "Adding menu shortcuts…" : menuBusy ? "Checking menu shortcuts…" : menuState === "complete" ? "Menu shortcuts added" : "Add menu shortcuts",
      detail: "Omarchy → Install / Remove / Update → Flatpak", icon: menuState === "complete" ? "✓" : "󰐕" },
    { action: "check", title: checking ? "Checking requirements…" : "Check again", detail: "Refresh requirements and menu status", icon: "󰑐" }
  ]

  function enabledFor(action) {
    if (action === "check") return !checking && !menuBusy && !settingUp
    if (action === "setup") return !!dependencies && dependencies.python3 === true && !checking && !menuBusy && !settingUp && menuState !== "complete"
    return !checking && Actions.canLaunch(action, dependencies)
  }

  function run(argv, callback) {
    var job = commandFactory.createObject(root) as AsyncCommand
    job.finished.connect(callback)
    job.start(argv)
  }

  function open(payloadJson) {
    selectedIndex = 0
    controller.show()
    refresh(Actions.actionFromPayload(payloadJson))
  }

  // Includes shell hide, outside clicks, Escape, and popout switches.
  onOpenedChanged: if (!opened) generation++

  function refresh(action) {
    var request = ++generation
    checking = true
    menuBusy = false
    dependencies = null
    probeError = ""
    menuError = ""
    menuState = "unknown"
    run(["bash", probePath], function(code, output) {
      if (!Actions.isCurrent(request, root.generation, root.opened)) return
      root.checking = false
      try {
        var result = JSON.parse(output)
        if (code !== 0 || typeof result.flatpak !== "boolean" || typeof result.fzf !== "boolean" || typeof result.python3 !== "boolean") throw new Error("probe failed")
        root.dependencies = result
      } catch (_) {
        root.probeError = "Could not check requirements. Choose Check again."
      }
      if (Actions.canLaunch(action, root.dependencies)) {
        Quickshell.execDetached(Actions.commandFor(action, root.scriptPath))
        root.close()
      } else if (root.dependencies && root.dependencies.python3 && !root.settingUp) {
        root.checkMenu(request)
      }
    })
  }

  function checkMenu(request) {
    menuBusy = true
    run(["python3", "-B", menuPath, "status", "--json"], function(code, output) {
      if (!Actions.isCurrent(request, root.generation, root.opened)) return
      root.menuBusy = false
      root.receiveMenu(code, output)
    })
  }

  function receiveMenu(code, output) {
    try {
      var result = JSON.parse(output)
      if (code !== 0 || !result.ok) throw new Error(result.error || "Menu command failed.")
      menuState = result.status
      menuError = result.status === "conflict" ? "Menu shortcuts conflict with custom entries: " + result.conflicts.join(", ") + ". Edit those entries, then check again." : ""
    } catch (error) {
      menuState = "error"
      menuError = "Could not configure menu shortcuts. " + error.message
    }
  }

  function activate(action) {
    if (!enabledFor(action)) return
    if (action === "check") { refresh(""); return }
    if (action !== "setup") { refresh(action); return }
    settingUp = true
    menuError = ""
    run(["python3", "-B", menuPath, "setup", "--json"], function(code, output) {
      root.settingUp = false
      if (root.opened) {
        root.receiveMenu(code, output)
      }
    })
  }

  function moveSelection(direction) {
    for (var i = 0; i < actions.length; i++) {
      selectedIndex = (selectedIndex + direction + actions.length) % actions.length
      if (enabledFor(actions[selectedIndex].action)) return
    }
  }

  Component { id: commandFactory; AsyncCommand {} }

  CenteredPanel {
    id: panel
    owner: root
    open: root.opened
    focusTarget: keys
    contentWidth: panel.fittedContentWidth(Style.space(420))
    contentHeight: panel.fittedContentHeight(content.implicitHeight)

    Ui.PanelKeyCatcher {
      id: keys
      anchors.fill: parent
      onCloseRequested: root.close()
      onMoveRequested: function(dx, dy) { if (dy) root.moveSelection(dy) }
      onTabRequested: function(direction) { root.moveSelection(direction) }
      onActivateRequested: root.activate(root.actions[root.selectedIndex].action)

      Column {
        id: content
        width: parent.width
        spacing: Style.space(10)

        Column {
          width: parent.width
          spacing: Style.space(4)
          Text {
            text: "Flatpak Store"
            textFormat: Text.PlainText
            color: Color.foreground
            font.family: root.fonts.family
            font.pixelSize: root.fonts.heading
            font.bold: true
          }
          Text {
            text: "Manage apps on this system"
            textFormat: Text.PlainText
            color: Color.foreground
            opacity: 0.72
            font.family: root.fonts.family
            font.pixelSize: root.fonts.body
          }
        }

        Ui.PanelSeparator { width: parent.width }

        Text {
          visible: root.guidance !== ""
          width: parent.width
          text: root.guidance
          textFormat: Text.PlainText
          wrapMode: Text.WordWrap
          color: Color.urgent
          font.family: root.fonts.family
          font.pixelSize: root.fonts.bodySmall
          Accessible.role: Accessible.StaticText
          Accessible.name: text
        }

        Repeater {
          model: root.actions
          delegate: Ui.CursorSurface {
            id: actionRow
            required property int index
            required property var modelData
            width: content.width
            height: Math.max(Style.space(index < 3 ? 66 : 54), labels.implicitHeight + Style.space(16))
            enabled: root.enabledFor(modelData.action)
            opacity: enabled || (modelData.action === "setup" && root.menuState === "complete") ? 1 : 0.45
            hasCursor: enabled && root.selectedIndex === index
            accent: modelData.action === "remove" ? Color.urgent : Color.accent
            Accessible.role: Accessible.Button
            Accessible.name: modelData.title
            Accessible.description: modelData.detail
            Accessible.onPressAction: root.activate(actionRow.modelData.action)

            Text {
              id: icon
              anchors.left: parent.left
              anchors.leftMargin: Style.space(12)
              anchors.verticalCenter: parent.verticalCenter
              width: Style.space(28)
              text: actionRow.modelData.icon
              color: actionRow.accent
              font.family: root.fonts.family
              font.pixelSize: root.fonts.iconLarge
            }
            Column {
              id: labels
              anchors.left: icon.right
              anchors.leftMargin: Style.space(10)
              anchors.right: parent.right
              anchors.rightMargin: Style.space(12)
              anchors.verticalCenter: parent.verticalCenter
              spacing: Style.space(4)
              Text {
                width: parent.width
                text: actionRow.modelData.title
                textFormat: Text.PlainText
                color: Color.foreground
                font.family: root.fonts.family
                font.pixelSize: actionRow.index < 3 ? root.fonts.subtitle : root.fonts.body
                font.bold: true
              }
              Text {
                width: parent.width
                text: actionRow.modelData.detail
                textFormat: Text.PlainText
                color: Color.foreground
                opacity: 0.72
                font.family: root.fonts.family
                font.pixelSize: root.fonts.bodySmall
                wrapMode: Text.WordWrap
              }
            }
            MouseArea {
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onPositionChanged: root.selectedIndex = actionRow.index
              onClicked: root.activate(actionRow.modelData.action)
            }
          }
        }

        Ui.PanelSeparator { width: parent.width }
        Text {
          width: parent.width
          text: "↑↓ / Tab to choose · Enter to open · Esc to close"
          textFormat: Text.PlainText
          wrapMode: Text.WordWrap
          color: Color.foreground
          opacity: 0.65
          font.family: root.fonts.family
          font.pixelSize: root.fonts.caption
        }
      }
    }
  }
}
