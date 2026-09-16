pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.Commons
import qs.Ui as Ui

// Quickshell supplies the platform-specific PanelWindow implementation at runtime.
// qmllint disable uncreatable-type
PanelWindow {
  // qmllint enable uncreatable-type
  id: root
  property bool open: false
  property var owner: null
  property Item focusTarget: null
  property int contentWidth: Style.space(420)
  property int contentHeight: Style.space(348)
  readonly property var spacing: Style.spacing
  readonly property var popupColors: Color.popups
  property int padding: spacing.popupPadding
  property bool focusPrimed: false
  default property alias panelContent: contentHolder.children

  function close() { if (owner) owner.close() }
  function fittedContentWidth(desired) {
    return Math.max(1, Math.min(desired, screen ? screen.width : desired))
  }
  function fittedContentHeight(desired) {
    var height = desired + card.contentTopInset + card.contentBottomInset
    return Math.max(1, Math.min(height, screen ? screen.height : height))
  }

  visible: open
  color: "transparent"
  exclusionMode: ExclusionMode.Ignore
  anchors { top: true; bottom: true; left: true; right: true }
  WlrLayershell.namespace: "flatpak-store-panel"
  WlrLayershell.layer: WlrLayer.Overlay
  WlrLayershell.keyboardFocus: open
    ? (focusPrimed ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.Exclusive)
    : WlrKeyboardFocus.None

  onOpenChanged: {
    focusPrimed = false
    if (open) {
      primeTimer.restart()
      Qt.callLater(function() { if (root.open && root.focusTarget) root.focusTarget.forceActiveFocus() })
    } else primeTimer.stop()
  }
  Timer {
    id: primeTimer
    interval: 100
    onTriggered: root.focusPrimed = true
  }

  MouseArea {
    anchors.fill: parent
    acceptedButtons: Qt.AllButtons
    onClicked: root.close()
  }

  Ui.BorderSurface {
    id: card
    anchors.centerIn: parent
    width: root.contentWidth
    height: root.contentHeight
    padding: root.padding
    color: root.popupColors.background
    radius: Style.cornerRadius
    borderSpec: Border.surfaceSpec("popups", "border", root.popupColors.border, Math.max(1, Style.space(2)))

    MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons }
    Item {
      id: contentHolder
      anchors.fill: parent
      anchors.topMargin: card.contentTopInset
      anchors.rightMargin: card.contentRightInset
      anchors.bottomMargin: card.contentBottomInset
      anchors.leftMargin: card.contentLeftInset
    }
  }

  Variants {
    model: root.open ? Quickshell.screens : []
    delegate: PanelWindow {
      required property var modelData
      screen: modelData
      visible: root.open && !!root.screen && modelData.name !== root.screen.name
      color: "transparent"
      exclusionMode: ExclusionMode.Ignore
      anchors { top: true; bottom: true; left: true; right: true }
      WlrLayershell.namespace: "flatpak-store-dismiss"
      WlrLayershell.layer: WlrLayer.Overlay
      WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
      MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; onPressed: root.close() }
    }
  }
}
