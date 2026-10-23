import QtQuick
import QtQuick.Controls.Basic
import Launcher

Item {
    id: page
    readonly property color accent: Theme.warn
    readonly property int side: 36

    Flickable {
        id: flick
        anchors.fill: parent
        contentWidth: width; contentHeight: body.implicitHeight + 60
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {
            id: bar
            contentItem: Rectangle { implicitWidth: 6; radius: 3; color: bar.pressed ? Theme.ghostLineHover : Theme.ghostLine }
            background: Item { }
        }

        Column {
            id: body
            x: page.side; y: 26; width: flick.width - 2 * page.side; spacing: 14

            Text { text: Theme.tr("upd_title"); color: "#fff"; font.family: Theme.fontDisplay; font.variableAxes: ({ "wght": 800 }); font.pixelSize: 42
                   font.weight: Font.ExtraBold; font.capitalization: Font.AllUppercase; font.letterSpacing: 2.1 }
            Text { width: parent.width; text: Updates.introText; wrapMode: Text.WordWrap; color: Theme.textDim
                   font.family: Theme.fontText; font.pixelSize: 13; lineHeight: 1.35; lineHeightMode: Text.ProportionalHeight }

            Rectangle {
                width: parent.width; height: versions.implicitHeight + 40
                radius: 14; color: Theme.card; border.width: 1
                border.color: Updates.available ? Qt.rgba(Theme.warn.r, Theme.warn.g, Theme.warn.b, 0.7) : Theme.cardLine
                Rectangle { visible: Updates.available; width: 3; height: parent.height - 2; x: 1; y: 1; color: Theme.warn }
                Column {
                    id: versions
                    x: 22; y: 20; width: parent.width - 44; spacing: 14
                    Column {
                        width: parent.width; spacing: 8
                        Text { text: Theme.tr("upd_choose_release"); color: Theme.textMuted; font.family: Theme.fontText; font.pixelSize: 12; font.weight: Font.Bold }
                        Select {
                            width: parent.width; accent: page.accent
                            model: Updates.releaseOptions; currentIndex: Updates.releaseIndex
                            enabled: !Updates.busy && !Updates.checking && !Updates.dialog.open && !Updates.canRestart
                            onActivated: (i) => Updates.selectRelease(i)
                        }
                        Text { width: parent.width; text: Theme.tr("upd_beta_warning"); visible: Updates.betaSelected
                               wrapMode: Text.WordWrap; color: Theme.warn; font.family: Theme.fontText; font.pixelSize: 13 }
                        Text { width: parent.width; text: Theme.tr("upd_beta_empty"); visible: Updates.releaseOptions.length === 1
                               wrapMode: Text.WordWrap; color: Theme.textDim; font.family: Theme.fontText; font.pixelSize: 12 }
                    }
                    Row {
                        width: parent.width; spacing: 24
                        Column {
                            width: (versions.width - 24) / 2; spacing: 4
                            Text { text: Theme.tr("upd_current"); color: Theme.textMuted; font.family: Theme.fontText; font.pixelSize: 12
                                   font.weight: Font.Bold; font.capitalization: Font.AllUppercase; font.letterSpacing: 1 }
                            Text { width: parent.width; wrapMode: Text.WrapAnywhere; text: Updates.current; color: "#fff"; font.family: Theme.fontDisplay; font.variableAxes: ({ "wght": 800 }); font.pixelSize: 30
                                   font.weight: Font.ExtraBold; font.letterSpacing: 1 }
                        }
                        Column {
                            width: (versions.width - 24) / 2; spacing: 4
                            Text { text: Theme.tr("upd_selected_release"); color: Theme.textMuted; font.family: Theme.fontText; font.pixelSize: 12
                                   font.weight: Font.Bold; font.capitalization: Font.AllUppercase; font.letterSpacing: 1 }
                            Text { width: parent.width; wrapMode: Text.WrapAnywhere; text: Updates.latest; color: Updates.available ? Theme.warn : "#fff"
                                   font.family: Theme.fontDisplay; font.variableAxes: ({ "wght": 800 }); font.pixelSize: 30
                                   font.weight: Font.ExtraBold; font.letterSpacing: 1 }
                            Text { text: Updates.published; color: Theme.textMuted; font.family: Theme.fontText; font.pixelSize: 12 }
                        }
                    }
                    Row {
                        spacing: 10
                        Rectangle { width: 4; height: statusText.implicitHeight; color: Updates.tone === "bad" ? Theme.bad : Updates.tone === "warn" ? Theme.warn
                                                                                  : Updates.tone === "good" ? Theme.ok : Theme.textMuted }
                        Text { id: statusText; width: versions.width - 14; text: Updates.statusText; wrapMode: Text.WordWrap; color: Theme.text
                               font.family: Theme.fontText; font.pixelSize: 15; font.weight: Font.DemiBold }
                    }
                    Column {
                        visible: Updates.busy
                        width: versions.width; spacing: 6
                        ProgressBar {
                            id: progressBar
                            width: parent.width; value: Updates.progress; indeterminate: Updates.progressIndeterminate
                            background: Rectangle { implicitHeight: 6; radius: 3; color: Theme.ghostLine }
                            contentItem: Item {
                                implicitHeight: 6
                                Rectangle {
                                    property real pulse: 1
                                    width: parent.width * (progressBar.indeterminate ? 0.22 : progressBar.position)
                                    height: parent.height; radius: 3; color: Theme.warn
                                    opacity: progressBar.indeterminate ? pulse : 1
                                    SequentialAnimation on pulse {
                                        running: progressBar.indeterminate; loops: Animation.Infinite
                                        NumberAnimation { from: 0.3; to: 1; duration: 650 }
                                        NumberAnimation { from: 1; to: 0.3; duration: 650 }
                                    }
                                }
                            }
                        }
                        Text { width: parent.width; text: Updates.progressText; wrapMode: Text.WordWrap; color: Theme.textDim; font.family: Theme.fontText; font.pixelSize: 12 }
                        Text { width: parent.width; visible: text !== ""; text: Updates.progressDetail; elide: Text.ElideMiddle; color: Theme.textMuted; font.family: Theme.fontText; font.pixelSize: 11 }
                    }
                    Flow {
                        width: versions.width; spacing: 10
                        GhostButton { tone: "primary"; accent: Theme.warn; text: Theme.tr("upd_check"); enabled: !Updates.checking && !Updates.busy; onClicked: Updates.check() }
                        GhostButton { visible: Updates.packaged && !Updates.canRestart && !Updates.selectedBetaInstalled; accent: Theme.warn; text: Theme.tr(Updates.betaSelected ? "upd_beta_download" : "upd_install")
                                      enabled: Updates.canInstall; onClicked: Updates.install() }
                        GhostButton { visible: Updates.betaSelected; tone: "primary"; accent: Theme.warn
                                      text: Theme.tr(Updates.selectedBetaInstalled ? "upd_beta_play" : "upd_beta_download_play")
                                      enabled: Updates.selectedBetaInstalled ? Updates.canManageBetas : Updates.canInstall
                                      onClicked: Updates.downloadAndPlayBeta() }
                        GhostButton { visible: Updates.canCancel; text: Theme.tr("upd_cancel"); onClicked: Updates.cancelDownload() }
                        GhostButton { visible: Updates.canRollback; text: Theme.tr("upd_rollback"); onClicked: Updates.rollback() }
                        GhostButton { visible: Updates.canRestart; tone: "primary"; accent: Theme.warn; text: Theme.tr("upd_restart"); onClicked: Updates.restart() }
                        GhostButton { text: Theme.tr(Updates.betaSelected ? "upd_beta_page" : "upd_download"); enabled: Updates.canDownload; onClicked: Updates.download() }
                    }
                    Text { visible: Updates.installHint !== ""; width: versions.width; text: Updates.installHint; wrapMode: Text.WordWrap
                           color: Theme.textDim; font.family: Theme.fontText; font.pixelSize: 12 }
                }
            }

            Rectangle {
                width: parent.width; height: optionRow.implicitHeight + 36
                radius: 12; color: Theme.card; border.width: 1; border.color: Theme.cardLine
                Row {
                    id: optionRow
                    x: 20; y: 18; width: parent.width - 40; spacing: 16
                    Toggle { id: sw; accent: page.accent; checked: Updates.checkOnOpen; onToggled: (v) => Updates.setCheckOnOpen(v)
                             anchors.verticalCenter: parent.verticalCenter }
                    Column {
                        width: parent.width - sw.width - 16; spacing: 3
                        anchors.verticalCenter: parent.verticalCenter
                        Text { text: Theme.tr("upd_check_on_open"); color: "#fff"; font.family: Theme.fontText; font.pixelSize: 15; font.weight: Font.DemiBold }
                        Text { width: parent.width; text: Theme.tr("upd_check_on_open_note"); wrapMode: Text.WordWrap; color: Theme.textDim
                               font.family: Theme.fontText; font.pixelSize: 12 }
                    }
                }
            }

            Row {
                id: notesHeading
                visible: Updates.notes !== ""
                spacing: 10
                Rectangle { width: 4; height: 20; color: page.accent; anchors.verticalCenter: parent.verticalCenter }
                Text { text: Theme.tr("upd_notes"); color: "#fff"; font.family: Theme.fontDisplay; font.variableAxes: ({ "wght": 800 }); font.pixelSize: 22
                       font.weight: Font.ExtraBold; font.capitalization: Font.AllUppercase; font.letterSpacing: 1.3
                       anchors.verticalCenter: parent.verticalCenter }
            }
            Rectangle {
                visible: Updates.notes !== ""
                width: parent.width; height: notesText.implicitHeight + 36
                radius: 12; color: Theme.card; border.width: 1; border.color: Theme.cardLine
                TextEdit { id: notesText; x: 20; y: 18; width: parent.width - 40; text: Updates.notes; readOnly: true; selectByMouse: true
                           wrapMode: TextEdit.Wrap; color: Theme.textSoft; selectionColor: page.accent; selectedTextColor: "#171100"
                           font.family: Theme.fontText; font.pixelSize: 14 }
            }
            Column {
                visible: Updates.betaSelected; width: parent.width; spacing: 12
                Text { width: parent.width; text: Updates.baselineTitle; wrapMode: Text.WordWrap; color: "#fff"
                       font.family: Theme.fontDisplay; font.pixelSize: 22; font.weight: Font.ExtraBold }
                Rectangle {
                    width: parent.width; height: baselineText.implicitHeight + 36
                    radius: 12; color: Theme.card; border.width: 1; border.color: Theme.cardLine
                    TextEdit { id: baselineText; x: 20; y: 18; width: parent.width - 40; text: Updates.baselineNotes
                               readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; color: Theme.textSoft
                               selectionColor: page.accent; font.family: Theme.fontText; font.pixelSize: 14 }
                }
            }
            Column {
                width: parent.width; spacing: 10
                Text { text: Theme.tr("upd_beta_library"); color: "#fff"; font.family: Theme.fontDisplay
                       font.pixelSize: 24; font.weight: Font.ExtraBold }
                Text { width: parent.width; text: Theme.tr("upd_beta_library_note"); wrapMode: Text.WordWrap
                       color: Theme.textDim; font.family: Theme.fontText; font.pixelSize: 13 }
                Text { width: parent.width; text: Updates.betaLibraryPath; elide: Text.ElideMiddle
                       color: Theme.textMuted; font.family: Theme.fontText; font.pixelSize: 11 }
                Text { visible: Updates.installedBetas.length === 0; text: Theme.tr("upd_beta_none_installed")
                       color: Theme.textDim; font.family: Theme.fontText; font.pixelSize: 13 }
                Repeater {
                    model: Updates.installedBetas
                    delegate: Rectangle {
                        required property var modelData
                        width: body.width; height: betaRow.implicitHeight + 28
                        radius: 12; color: Theme.card; border.width: 1; border.color: Theme.cardLine
                        Column {
                            id: betaRow; x: 18; y: 14; width: parent.width - 36; spacing: 10
                            Text { width: parent.width; text: modelData.tag + " · " + modelData.size
                                   color: Theme.text; font.family: Theme.fontText; font.pixelSize: 14; wrapMode: Text.WrapAnywhere }
                            Flow {
                                width: parent.width; spacing: 8
                                GhostButton { tone: "primary"; accent: Theme.warn; text: Theme.tr("upd_beta_play")
                                              enabled: Updates.canManageBetas; onClicked: Updates.playBeta(modelData.tag) }
                                GhostButton { text: Theme.tr("upd_notes"); enabled: !Updates.busy && !Updates.checking
                                              onClicked: Updates.viewBeta(modelData.tag) }
                                GhostButton { text: Theme.tr("upd_beta_delete"); enabled: Updates.canManageBetas
                                              onClicked: Updates.deleteBeta(modelData.tag) }
                            }
                        }
                    }
                }
            }

            Item { width: 1; height: 30 }
        }
    }

    Connections {
        target: Updates
        function onNotesRequested() { flick.contentY = Math.min(notesHeading.y, Math.max(0, flick.contentHeight - flick.height)) }
    }
    ConfirmCard { anchors.fill: parent; target: Updates }
}
