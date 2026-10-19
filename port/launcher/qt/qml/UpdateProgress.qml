import QtQuick
import QtQuick.Controls.Basic

ApplicationWindow {
    id: window
    visible: true
    width: 720; height: 450
    minimumWidth: 640; minimumHeight: 440
    title: "inFAMOUS — Update"
    color: "#13161c"
    onClosing: function(close) { close.accepted = updateJob.settled }

    Column {
        anchors.fill: parent; anchors.margins: 30; spacing: 18
        Text { text: "inFAMOUS"; color: "#ff9c45"; font.pixelSize: 26; font.bold: true }
        Text { width: parent.width; text: updateJob.heading; color: updateJob.failed ? "#ff7373" : "white";
               font.pixelSize: 21; font.bold: true; wrapMode: Text.WordWrap }
        ProgressBar {
            id: bar
            width: parent.width; value: updateJob.fraction; indeterminate: updateJob.indeterminate
            background: Rectangle { implicitHeight: 8; color: "#303742"; radius: 4 }
            contentItem: Item {
                implicitHeight: 8
                Rectangle {
                    width: parent.width * (bar.indeterminate ? 0.22 : bar.position)
                    height: parent.height; radius: 4; color: "#ff9c45"
                    SequentialAnimation on opacity {
                        running: bar.indeterminate; loops: Animation.Infinite
                        NumberAnimation { from: 0.3; to: 1; duration: 650 }
                        NumberAnimation { from: 1; to: 0.3; duration: 650 }
                    }
                }
            }
        }
        Text { width: parent.width; text: updateJob.countText; color: "#e0e4eb"; font.pixelSize: 14 }
        Text { width: parent.width; text: updateJob.filename; color: "#b2bac7"; font.pixelSize: 12;
               elide: Text.ElideMiddle; maximumLineCount: 2; wrapMode: updateJob.failed ? Text.WrapAnywhere : Text.NoWrap }
        Text { width: parent.width; text: updateJob.timing; color: "#b2bac7"; font.pixelSize: 12; wrapMode: Text.WordWrap }
        Text { width: parent.width; text: updateJob.hint; color: "#b2bac7"; font.pixelSize: 13; wrapMode: Text.WordWrap }
        Button { text: updateJob.closeLabel; enabled: updateJob.settled; onClicked: window.close() }
    }
}
