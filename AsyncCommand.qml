pragma ComponentBehavior: Bound

import QtQuick
import Quickshell.Io

// One instance per request: old completions cannot consume a new request's output.
Item {
  id: root
  property bool exited: false
  property bool drained: false
  property bool completed: false
  property int code: -1
  signal finished(int exitCode, string output)

  function start(argv) {
    process.command = argv
    watchdog.start()
    process.running = true
  }

  function finishIfReady() {
    if (exited && drained) finish(code, output.text)
  }

  function finish(exitCode, text) {
    if (completed) return
    completed = true
    watchdog.stop()
    finished(exitCode, text)
    root.destroy()
  }

  Process {
    id: process
    stdout: StdioCollector {
      id: output
      waitForEnd: true
      onStreamFinished: {
        root.drained = true
        root.finishIfReady()
      }
    }
    stderr: StdioCollector {}
    // Quickshell's type metadata omits QProcess::ExitStatus; only the code is used.
    // qmllint disable signal-handler-parameters
    onExited: function(exitCode) {
      root.code = exitCode
      root.exited = true
      root.finishIfReady()
    }
    // qmllint enable signal-handler-parameters
  }

  Timer {
    id: watchdog
    interval: 10000
    onTriggered: {
      process.running = false
      root.finish(-1, '{"ok":false,"error":"Command failed to start or timed out. Check again."}')
    }
  }
}
