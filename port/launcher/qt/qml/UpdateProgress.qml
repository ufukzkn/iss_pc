import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ApplicationWindow {
    id: window
    visible: true
    width: 800; height: 540
    minimumWidth: 680; minimumHeight: 520
    title: "inFAMOUS — Update"
    color: "#101216"
    readonly property color accent: updateJob.failed ? "#ff4d4d" : updateJob.settled ? "#35d07f" : "#f5c400"
    readonly property string displayFont: typeof updateFontDisplay !== "undefined" ? updateFontDisplay : Qt.application.font.family
    readonly property string textFont: typeof updateFontText !== "undefined" ? updateFontText : Qt.application.font.family
    onClosing: function(close) { close.accepted = updateJob.settled }

    ColumnLayout {
        anchors.fill: parent; anchors.margins: 28; spacing: 20
        RowLayout {
            Layout.fillWidth: true; Layout.preferredHeight: 44; spacing: 16
            Rectangle { width: 3; height: 30; radius: 1; color: window.accent }
            Column {
                spacing: 1
                Text { text: "inFAMOUS"; color: "#e9e6df"; font.family: window.displayFont; font.pixelSize: 30; font.bold: true }
                Text { text: "SECOND SON · PC"; color: "#8e949f"; font.family: window.textFont; font.pixelSize: 10; font.letterSpacing: 2 }
            }
            Item { Layout.fillWidth: true }
            Rectangle {
                implicitWidth: stateLabel.implicitWidth + 28; implicitHeight: 30; radius: 15
                color: Qt.rgba(window.accent.r, window.accent.g, window.accent.b, 0.10)
                border.color: Qt.rgba(window.accent.r, window.accent.g, window.accent.b, 0.35)
                Text {
                    id: stateLabel
                    anchors.centerIn: parent; text: updateJob.statusLabel; color: window.accent
                    font.family: window.textFont; font.pixelSize: 11; font.weight: Font.DemiBold; font.letterSpacing: 0.8
                }
            }
        }
        Rectangle {
            Layout.fillWidth: true; Layout.fillHeight: true
            color: "#15181d"; border.color: "#262b33"; radius: 16
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 24; spacing: 12
                RowLayout {
                    Layout.fillWidth: true; spacing: 24
                    Text {
                        Layout.fillWidth: true; text: updateJob.heading; color: "#e9e6df"
                        font.family: window.displayFont; font.pixelSize: 32; font.bold: true; wrapMode: Text.WordWrap
                    }
                    Text {
                        text: updateJob.failed ? "!" : updateJob.indeterminate ? "…" :
                              (updateJob.settled ? "100" : Math.round(updateJob.fraction * 100)) + "%"
                        color: window.accent; font.family: window.displayFont; font.pixelSize: 52; font.bold: true
                    }
                }
                ProgressBar {
                    id: bar
                    Layout.fillWidth: true; Layout.preferredHeight: 8
                    value: updateJob.settled && !updateJob.failed ? 1 : updateJob.fraction
                    indeterminate: updateJob.indeterminate
                    background: Rectangle { implicitHeight: 8; color: "#262b33"; radius: 4 }
                    contentItem: Item {
                        implicitHeight: 8; clip: true
                        Rectangle {
                            id: fill
                            property real travel: 0
                            width: parent.width * (bar.indeterminate ? 0.24 : bar.position)
                            height: parent.height; radius: 4; color: window.accent
                            x: bar.indeterminate ? travel : 0
                            NumberAnimation on travel {
                                running: bar.indeterminate; loops: Animation.Infinite
                                from: -fill.width; to: bar.width; duration: 1400
                            }
                        }
                    }
                }
                Text { Layout.fillWidth: true; text: updateJob.countText; visible: text.length > 0
                    color: "#c9c5bd"; font.family: window.textFont; font.pixelSize: 13 }
                Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: "#262b33" }
                Text { text: updateJob.detailLabel; color: "#8e949f"; font.family: window.textFont
                    font.pixelSize: 10; font.weight: Font.DemiBold; font.letterSpacing: 1.3 }
                ScrollView {
                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true; contentWidth: availableWidth
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    TextArea {
                        text: updateJob.filename || "—"; readOnly: true; selectByMouse: true
                        color: updateJob.failed ? "#ff8c8c" : "#d8d5ce"
                        font.family: window.textFont; font.pixelSize: 13
                        wrapMode: TextEdit.WrapAnywhere; padding: 0; background: null
                    }
                }
                Text { Layout.fillWidth: true; text: updateJob.timing; color: "#8e949f"
                    font.family: window.textFont; font.pixelSize: 12; wrapMode: Text.WordWrap }
            }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: 24
            Text { Layout.fillWidth: true; text: updateJob.hint; color: "#a3a9b3"
                font.family: window.textFont; font.pixelSize: 13; wrapMode: Text.WordWrap }
            Button {
                id: closeButton
                text: updateJob.closeLabel; enabled: updateJob.settled
                Layout.preferredWidth: 116; Layout.preferredHeight: 42
                onClicked: window.close()
                background: Rectangle {
                    radius: 10; color: closeButton.hovered && closeButton.enabled ? "#22262e" : "#1a1d23"
                    border.color: closeButton.activeFocus ? window.accent : "#303641"; opacity: closeButton.enabled ? 1 : 0.5
                }
                contentItem: Text {
                    text: closeButton.text; color: closeButton.enabled ? "#e9e6df" : "#7d838e"
                    font.family: window.textFont; font.pixelSize: 14; font.weight: Font.DemiBold
                    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                }
            }
        }
    }
}
