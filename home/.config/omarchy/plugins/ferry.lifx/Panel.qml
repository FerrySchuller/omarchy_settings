import QtQuick
import Quickshell
import Quickshell.Io
import qs.Ui
import qs.Commons

// LIFX bar widget: a bulb icon that opens a control popup.
//
// Every control shells out to the standalone `lifxctl` wrapper next to this
// file (which pins the lamp IP and forwards to lifx.py), so all of lifx.py's
// power / brightness / temperature / colour functionality stays reachable.
Panel {
  id: root
  moduleName: "ferry.lifx"
  ipcTarget: "ferry.lifx"

  readonly property string ctl: Quickshell.env("HOME") + "/.config/omarchy/plugins/ferry.lifx/lifxctl"

  property bool haveState: false
  property bool lampOn: false
  property int brightness: 0
  property int kelvin: 2200
  property int hue: 0
  property int saturation: 0

  readonly property string statusText: {
    if (!haveState) return "OFFLINE"
    if (!lampOn) return "OFF"
    return "ON · " + brightness + "% · " + kelvin + "K"
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  function refresh() {
    if (!stateProc.running) stateProc.running = true
  }

  function run(args) {
    if (actionProc.running) return
    actionProc.command = [ctl].concat(args)
    actionProc.running = true
  }

  Component.onCompleted: refresh()
  onOpenedChanged: if (opened) refresh()

  // Poll only while the popup is open; the icon state is refreshed on open and
  // after every action, so a closed panel costs nothing.
  Timer {
    interval: 5000
    running: root.opened
    repeat: true
    onTriggered: root.refresh()
  }

  Process {
    id: stateProc
    command: [root.ctl, "status"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var info = JSON.parse(String(text || "{}"))
          if (!info || info.power === undefined || !info.color) {
            root.haveState = false
            return
          }
          root.haveState = true
          root.lampOn = String(info.power) === "on"
          root.brightness = Math.round(Number(info.color.brightness_pct) || 0)
          root.kelvin = Math.round(Number(info.color.kelvin) || 2200)
          root.hue = Math.round(Number(info.color.hue_deg) || 0)
          root.saturation = Math.round(Number(info.color.saturation_pct) || 0)
        } catch (e) {
          root.haveState = false
        }
      }
    }
  }

  Process {
    id: actionProc
    onRunningChanged: if (!running) root.refresh()
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "\uf0eb"
    active: root.lampOn
    tooltipText: "LIFX — " + root.statusText
    onPressed: function(b) { root.toggle() }
    onWheelMoved: function(delta) {
      if (!root.haveState) return
      root.run(["b", delta > 0 ? "+10" : "-10"])
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    contentWidth: panel.fittedContentWidth(Style.space(340))
    contentHeight: panel.fittedContentHeight(column.implicitHeight, Style.space(560))

    Column {
      id: column
      width: parent.width
      spacing: Style.space(12)

      // ---------- Hero: bulb · title / status ----------
      Item {
        width: parent.width
        implicitHeight: Math.max(heroIcon.implicitHeight, heroLabels.implicitHeight)

        Text {
          id: heroIcon
          textFormat: Text.PlainText
          text: "\uf0eb"
          color: root.lampOn ? root.bar.foreground : Qt.darker(root.bar.foreground, 1.6)
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.display
          anchors.left: parent.left
          anchors.verticalCenter: parent.verticalCenter
        }

        Column {
          id: heroLabels
          anchors.left: heroIcon.right
          anchors.leftMargin: Style.space(14)
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          spacing: Style.space(2)

          Text {
            text: "LIFX"
            color: root.bar.foreground
            font.family: root.bar.fontFamily
            font.pixelSize: Style.font.title
            font.bold: true
            width: parent.width
            elide: Text.ElideRight
          }

          Text {
            text: root.statusText
            color: Qt.darker(root.bar.foreground, 1.4)
            font.family: root.bar.fontFamily
            font.pixelSize: Style.font.caption
            font.bold: true
            font.letterSpacing: 1.2
            width: parent.width
            elide: Text.ElideRight
          }
        }
      }

      PanelSeparator { foreground: root.bar.foreground }

      // ---------- Power ----------
      Row {
        spacing: Style.space(8)

        Button {
          text: "On"
          foreground: root.bar.foreground
          fontFamily: root.bar.fontFamily
          bordered: true
          selected: root.lampOn
          onClicked: root.run(["on"])
        }

        Button {
          text: "Off"
          foreground: root.bar.foreground
          fontFamily: root.bar.fontFamily
          bordered: true
          selected: root.haveState && !root.lampOn
          onClicked: root.run(["off"])
        }
      }

      // ---------- Warm 50 preset ----------
      Button {
        text: "Warm 50"
        foreground: root.bar.foreground
        fontFamily: root.bar.fontFamily
        bordered: true
        selected: root.lampOn && root.brightness === 50 && root.kelvin === 2200
        onClicked: root.run(["warm", "50"])
      }

      // ---------- Brightness ----------
      PanelSectionHeader {
        text: "BRIGHTNESS"
        foreground: root.bar.foreground
        fontFamily: root.bar.fontFamily
      }

      PanelSlider {
        id: brightnessSlider
        bar: root.bar
        width: parent.width
        minimum: 1
        maximum: 100
        step: 1
        integer: true
        value: root.brightness
        onReleased: function(v) { root.run(["b", String(Math.round(v))]) }
      }

      Text {
        textFormat: Text.PlainText
        text: Math.round(brightnessSlider.dragging ? brightnessSlider.liveValue : root.brightness) + "%"
        color: Qt.darker(root.bar.foreground, 1.4)
        font.family: root.bar.fontFamily
        font.pixelSize: Style.font.caption
      }

      // ---------- Temperature ----------
      PanelSectionHeader {
        text: "TEMPERATURE"
        foreground: root.bar.foreground
        fontFamily: root.bar.fontFamily
      }

      PanelSlider {
        id: kelvinSlider
        bar: root.bar
        width: parent.width
        minimum: 1500
        maximum: 9000
        step: 100
        integer: true
        value: root.kelvin
        onReleased: function(v) { root.run(["k", String(Math.round(v))]) }
      }

      Text {
        textFormat: Text.PlainText
        text: Math.round(kelvinSlider.dragging ? kelvinSlider.liveValue : root.kelvin) + "K"
        color: Qt.darker(root.bar.foreground, 1.4)
        font.family: root.bar.fontFamily
        font.pixelSize: Style.font.caption
      }

      // ---------- Colour presets ----------
      PanelSectionHeader {
        text: "COLOURS"
        foreground: root.bar.foreground
        fontFamily: root.bar.fontFamily
      }

      Flow {
        width: parent.width
        spacing: Style.space(6)

        Repeater {
          model: ["warm", "koel", "wit", "rood", "oranje", "geel", "groen", "turkoois", "blauw", "paars", "roze", "nacht", "lees", "focus"]

          Button {
            required property string modelData
            text: modelData
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            fontSize: Style.font.bodySmall
            bordered: true
            onClicked: root.run([modelData])
          }
        }
      }
    }
  }
}
