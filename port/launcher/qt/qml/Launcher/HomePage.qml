import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import Launcher

// Play tab (2026-11-11 layout): the game's artwork fills a tall panel on the right with Play and its
// buttons over its lower part; the left side holds the game choice, the state and the quick settings
// in two cards (labels in one column, so the lists line up) and scrolls when the window is short.
Item {
    id: page
    signal openFixes()
    signal openSaves()
    property real pulse: 0
    property bool animate: true
    readonly property color accent: Theme.smoke
    readonly property int labelWidth: 110
    // A picture shown whole (a GIF, or First Light's game icon): the whole tab becomes that picture's paper.
    readonly property bool paperMode: Backend.artWhole
    // Second Son: the game's own pic0.png (Delsin) behind the whole tab, under orange see-through cards.
    readonly property bool backdropMode: Backend.artBackdrop

    SequentialAnimation on pulse {
        running: page.animate && page.visible && !Backend.reducedMotion
        loops: Animation.Infinite
        NumberAnimation { from: 0; to: 1; duration: 1300; easing.type: Easing.InOutSine }
        NumberAnimation { from: 1; to: 0; duration: 1300; easing.type: Easing.InOutSine }
    }

    component RowLabel: Text {
        width: page.labelWidth; wrapMode: Text.WordWrap
        color: Theme.textMuted; font.family: Theme.fontText; font.pixelSize: 13; font.weight: Font.Bold
    }
    component Hint: Text {
        width: parent ? parent.width : 300; wrapMode: Text.WordWrap; color: Theme.textDim
        font.family: Theme.fontText; font.pixelSize: 12; lineHeight: 1.25; lineHeightMode: Text.ProportionalHeight
    }
    component Card: Rectangle {
        default property alias content: inner.data
        width: parent ? parent.width : 300; height: inner.implicitHeight + 32
        radius: 14; border.width: 1
        // over the Second Son picture: an orange-tinted glass card; otherwise the usual dark card
        color: Backend.artBackdrop ? Qt.rgba(0.22, 0.09, 0.03, 0.74) : Qt.rgba(Theme.card.r, Theme.card.g, Theme.card.b, 0.86)
        border.color: Backend.artBackdrop ? Qt.rgba(1, 0.42, 0.17, 0.35) : Theme.cardLine
        Column { id: inner; x: 16; y: 16; width: parent.width - 32; spacing: 12 }
    }

    // ---- Second Son backdrop: pic0.png from the player's game folder behind the whole tab, cut from
    // the left so Delsin stays on the right (under the Play buttons); a soft dark wash on the left keeps
    // the cards readable over the bright fog.
    Image {
        anchors.fill: parent
        visible: page.backdropMode
        source: page.backdropMode ? Backend.artSource : ""
        fillMode: Image.PreserveAspectCrop
        horizontalAlignment: Image.AlignRight
        smooth: true; mipmap: true; asynchronous: true
    }
    Rectangle {
        anchors.fill: parent
        visible: page.backdropMode
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: Qt.rgba(0.04, 0.02, 0.01, 0.62) }
            GradientStop { position: 0.55; color: Qt.rgba(0.04, 0.02, 0.01, 0.30) }
            GradientStop { position: 1; color: Qt.rgba(0.04, 0.02, 0.01, 0.0) }
        }
    }

    // ---- artwork panel with Play ---------------------------------------------------------------
    Item {
        id: artPanel
        anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.right: parent.right
        // paper mode: at least the fitted GIF's width, and wide enough for the buttons' labels
        // paper mode: a tall GIF gets at least its fitted width; a square picture (game icon) the usual width
        width: Backend.artAnimated && animArt.implicitHeight > 0
               ? Math.max(430, Math.round(height * animArt.implicitWidth / animArt.implicitHeight))
               : Math.max(page.paperMode ? 430 : 340, Math.min(560, parent.width * 0.46))
        clip: true
        Image { anchors.fill: parent; source: "image://hero/bg"; cache: false; visible: !page.backdropMode }   // neon + rain (drawn in Python)
        Rectangle {   // a picture shown whole: its own background colour fills the rest of the panel
            anchors.fill: parent; visible: page.paperMode
            color: Backend.artBackground !== "" ? Backend.artBackground : Theme.bg
        }
        Image {   // the game's own picture shown whole (First Light's icon0.png from the player's game folder)
            id: wholeArt
            readonly property bool on: page.paperMode && !Backend.artAnimated
            visible: on
            source: on ? Backend.artSource : ""
            width: parent.width
            height: implicitWidth > 0 ? Math.round(width * implicitHeight / implicitWidth) : 0
            fillMode: Image.PreserveAspectFit
            smooth: true; mipmap: true
        }
        Rectangle {   // its lower edge melts into the paper (no visible line under the picture)
            visible: wholeArt.on
            y: wholeArt.height - height; width: parent.width; height: Math.round(wholeArt.height * 0.28)
            gradient: Gradient {
                GradientStop { position: 0; color: Qt.rgba(paper.color.r, paper.color.g, paper.color.b, 0) }
                GradientStop { position: 1; color: paper.color }
            }
        }
        AnimatedImage {   // the player's launcher-art/<game>.gif, whole (fitted, never cut), playing while shown
            id: animArt
            anchors.fill: parent
            readonly property real paintedX: (width - paintedWidth) / 2
            visible: Backend.artAnimated
            source: Backend.artAnimated ? Backend.artSource : ""
            fillMode: Image.PreserveAspectFit
            verticalAlignment: Image.AlignTop
            playing: page.visible && Backend.artAnimated
            cache: false; smooth: true
        }
        Rectangle {   // the GIF's left and right edges melt into the paper colour around it (no visible join)
            visible: page.paperMode && Backend.artAnimated
            x: animArt.paintedX; width: 36; height: parent.height
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: paper.color }
                GradientStop { position: 1; color: Qt.rgba(paper.color.r, paper.color.g, paper.color.b, 0) }
            }
        }
        Rectangle {
            visible: page.paperMode && Backend.artAnimated
            x: animArt.paintedX + animArt.paintedWidth - 36; width: 36; height: parent.height
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: Qt.rgba(paper.color.r, paper.color.g, paper.color.b, 0) }
                GradientStop { position: 1; color: paper.color }
            }
        }
        Image {   // the player's own picture (launcher-art/<game>.jpg) or the dump's pic1.png; never shipped
            // Covers the panel: a tall picture keeps its top (the face); a wide one (the games' pic1.png)
            // is cut around two thirds of its width, where both games put their hero's face.
            readonly property real ratio: implicitHeight > 0 ? implicitWidth / implicitHeight : 1
            readonly property bool wide: ratio > artPanel.width / Math.max(1, artPanel.height)
            width: wide ? artPanel.height * ratio : artPanel.width
            height: wide ? artPanel.height : artPanel.width / ratio
            x: wide ? Math.max(artPanel.width - width, Math.min(0, artPanel.width / 2 - width * 0.66)) : 0
            source: page.paperMode || page.backdropMode ? "" : Backend.artSource
            visible: Backend.artSource !== "" && !page.paperMode && !page.backdropMode
            smooth: true; mipmap: true
            asynchronous: true
            opacity: status === Image.Ready ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 300 } }
        }
        Rectangle {   // lower part under the buttons: the drawn art's night black, or an animated picture's smoke colour
            id: shadeBox
            readonly property color shade: Backend.artShade
            // paper mode: the GIF's own smoke shows; backdrop: a light shade so the picture still shows under the buttons
            readonly property real strength: page.paperMode ? 0 : (page.backdropMode ? 0.5 : (Backend.artAnimated ? 0.78 : 0.97))
            anchors.bottom: parent.bottom; width: parent.width; height: actions.height + 140
            gradient: Gradient {
                GradientStop { position: 0; color: Qt.rgba(shadeBox.shade.r, shadeBox.shade.g, shadeBox.shade.b, 0) }
                GradientStop { position: 0.45; color: Qt.rgba(shadeBox.shade.r, shadeBox.shade.g, shadeBox.shade.b, shadeBox.strength * 0.85) }
                GradientStop { position: 1; color: Qt.rgba(shadeBox.shade.r, shadeBox.shade.g, shadeBox.shade.b, shadeBox.strength) }
            }
        }
        Item {   // small ember dots (Second Son) or neon dots (First Light) drifting up behind the buttons
            id: drift
            anchors.bottom: parent.bottom; width: parent.width; height: actions.height + 120
            clip: true
            readonly property bool neon: Backend.gameIndex === 1
            readonly property var sparks: neon ? ["#ffa0f5", "#be82ff", "#78e6ff", "#ff5ad2"] : ["#ffd278", "#ff8c32", "#ff5a1e", "#ffb45a"]
            Repeater {   // glowing dots
                model: 46
                Item {
                    property real size: 1.5 + Math.random() * 3.2
                    property real startX: Math.random() * drift.width
                    property int life: 6000 + Math.random() * 9000
                    width: size * 5; height: size * 5
                    x: startX - width / 2
                    Rectangle { anchors.centerIn: parent; width: parent.width; height: parent.height; radius: width / 2
                                color: drift.sparks[index % drift.sparks.length]; opacity: 0.13 }
                    Rectangle { anchors.centerIn: parent; width: size; height: size; radius: size / 2
                                color: drift.sparks[index % drift.sparks.length] }
                    opacity: 0
                    SequentialAnimation on y {
                        running: page.visible && !Backend.reducedMotion; loops: Animation.Infinite
                        PauseAnimation { duration: Math.random() * 7000 }
                        NumberAnimation { from: drift.height; to: drift.height * (0.05 + Math.random() * 0.3); duration: life; easing.type: Easing.OutQuad }
                    }
                    SequentialAnimation on opacity {
                        running: page.visible && !Backend.reducedMotion; loops: Animation.Infinite
                        PauseAnimation { duration: Math.random() * 7000 }
                        NumberAnimation { from: 0; to: 0.95; duration: life * 0.25 }
                        NumberAnimation { from: 0.95; to: 0; duration: life * 0.75 }
                    }
                    Component.onCompleted: if (Backend.reducedMotion) { y = Math.random() * drift.height; opacity = 0.7 }
                }
            }
        }
        Column {
            id: actions
            anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
            anchors.leftMargin: 28; anchors.rightMargin: 28; anchors.bottomMargin: 24
            spacing: 10
            Item {
                id: playBox
                width: parent.width; height: 80
                // pulsing glow (soft rings; the mock animates a box-shadow)
                Repeater {
                    model: 4
                    Rectangle {
                        anchors.centerIn: parent
                        width: playBtn.width + 2 * (4 + index * 7) * (0.5 + page.pulse)
                        height: playBtn.height + 2 * (4 + index * 7) * (0.5 + page.pulse)
                        radius: 14 + (4 + index * 7) * (0.5 + page.pulse)
                        color: Qt.rgba(1, 106/255, 43/255, (Backend.canPlay ? 0.075 : 0.0) * (1 - index * 0.2) * (0.6 + page.pulse * 0.8))
                    }
                }
                Rectangle {
                    id: playBtn
                    anchors.fill: parent
                    radius: 14
                    color: !Backend.canPlay ? "#3a2a22" : (playMouse.containsMouse ? Qt.lighter(page.accent, 1.1) : page.accent)
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        x: 24; spacing: 2
                        Text { text: Theme.tr("play_label"); font.family: Theme.fontDisplay; font.variableAxes: ({ "wght": 800 }); font.pixelSize: 34
                               font.weight: Font.ExtraBold; font.capitalization: Font.AllUppercase; font.letterSpacing: 1.7
                               color: Backend.canPlay ? "#160a04" : "#8a6a5a"; lineHeight: 0.95; lineHeightMode: Text.ProportionalHeight }
                        Text { text: Backend.playSubtitle; width: playBtn.width - 48; elide: Text.ElideRight
                               font.family: Theme.fontText; font.pixelSize: 13; font.weight: Font.DemiBold
                               color: Backend.canPlay ? "#160a04" : "#8a6a5a" }
                    }
                    Rectangle {   // shader list progress (first start): thin bar along the button's bottom edge
                        visible: Backend.jobsProgressValue >= 0
                        x: 24; width: playBtn.width - 48; height: 4; radius: 2
                        anchors.bottom: parent.bottom; anchors.bottomMargin: 8
                        color: "#5a3a2a"
                        Rectangle { width: parent.width * Math.max(0, Backend.jobsProgressValue); height: parent.height
                                    radius: 2; color: "#160a04" }
                    }
                    MouseArea { id: playMouse; anchors.fill: parent; hoverEnabled: true
                                enabled: Backend.canPlay; cursorShape: Qt.PointingHandCursor; onClicked: Backend.play() }
                    Accessible.role: Accessible.Button
                    Accessible.name: Theme.tr("play_label")
                }
            }
            Row {
                width: parent.width; spacing: 10
                GhostButton {
                    width: (parent.width - 10) / 2
                    text: Theme.tr("choose_folder")
                    onClicked: folderDialog.open()
                }
                GhostButton {   // Optional support: opens the creator page in the system browser.
                    width: (parent.width - 10) / 2
                    tone: "primary"; accent: "#FFDD00"
                    text: "☕  " + Theme.tr("coffee_label")
                    onClicked: Backend.openUrl("coffee")
                }
            }
            Rectangle {   // game language (voice and text) on a see-through card, readable over any artwork
                width: parent.width; height: langCol.implicitHeight + 20; radius: 10; border.width: 1
                color: page.backdropMode ? Qt.rgba(0.22, 0.09, 0.03, 0.74) : Qt.rgba(Theme.card.r, Theme.card.g, Theme.card.b, 0.86)
                border.color: page.backdropMode ? Qt.rgba(1, 0.42, 0.17, 0.35) : Theme.cardLine
                Column {
                    id: langCol
                    x: 12; y: 10; width: parent.width - 24; spacing: 4
                    Row {
                        spacing: 10
                        Text { text: Theme.tr("game_language_label"); color: Theme.textMuted; font.family: Theme.fontText; font.pixelSize: 12; font.weight: Font.Bold
                               width: 70; wrapMode: Text.WordWrap; anchors.verticalCenter: parent.verticalCenter }
                        Select {
                            accent: page.accent; width: actions.width - 104
                            model: Backend.gameLanguageOptions
                            currentIndex: Backend.gameLanguageIndex
                            onActivated: (i) => Backend.setGameLanguage(Backend.gameLanguageOptions[i].value)
                        }
                    }
                    Text { visible: Backend.gameLanguageNow !== ""; width: parent.width; text: Backend.gameLanguageNow; color: page.accent
                           font.family: Theme.fontText; font.pixelSize: 12; font.weight: Font.Bold }
                    Text { width: parent.width; text: Theme.tr("game_language_hint"); wrapMode: Text.WordWrap; color: Theme.textSoft
                           font.family: Theme.fontText; font.pixelSize: 12; lineHeight: 1.2; lineHeightMode: Text.ProportionalHeight }
                }
            }
        }
    }

    FolderDialog {
        id: folderDialog
        title: Theme.tr("choose_folder_title")
        currentFolder: Backend.gameDir ? "file://" + Backend.gameDir : ""
        onAccepted: Backend.chooseFolder(selectedFolder.toString())
    }

    // ---- left side backdrop: continues the artwork (its background colour with soft smoke in its smoke
    // colour), so the two halves of the tab join without a seam. Painted once per size/colour change.
    Canvas {
        id: backdrop
        anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.right: artPanel.left
        // Second Son only (the player's choice): First Light keeps the plain dark page.
        readonly property bool on: Backend.gameIndex === 0
        visible: !page.paperMode && !page.backdropMode
        readonly property color base: on && Backend.artAnimated && Backend.artBackground !== "" ? Backend.artBackground : Theme.bg
        readonly property color smoke: Backend.artAnimated ? Backend.artShade : "#ff6a2b"
        readonly property real strength: !on ? 0 : (Backend.artAnimated ? 1.0 : 0.35)
        onStrengthChanged: requestPaint()
        onBaseChanged: requestPaint()
        onSmokeChanged: requestPaint()
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            var ctx = getContext("2d"), W = width, H = height
            ctx.reset()
            ctx.fillStyle = base; ctx.fillRect(0, 0, W, H)
            var seed = 20141; function rnd() { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646 }
            function puff(x, y, r, a, c) {
                var g = ctx.createRadialGradient(x, y, 0, x, y, r)
                g.addColorStop(0, Qt.rgba(c.r, c.g, c.b, a)); g.addColorStop(0.5, Qt.rgba(c.r, c.g, c.b, a * 0.45))
                g.addColorStop(1, Qt.rgba(c.r, c.g, c.b, 0))
                ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill()
            }
            var deep = Qt.darker(smoke, 1.35), light = Qt.lighter(smoke, 1.25)
            // bands of smoke: start (x, y), end (x, y) as fractions, wave size, thickness, puffs
            var bands = [
                [-0.15, 1.02, 1.05, 0.80, 0.07, 0.16, 140],   // along the bottom, rising into the art's lower smoke
                [1.05, 0.06, -0.10, 0.22, 0.05, 0.12, 110],   // across the top, from the art's plume
                [0.10, 0.70, 1.02, 0.38, 0.06, 0.07, 70],     // a thin wisp through the middle
                [-0.10, 0.30, 0.45, -0.05, 0.04, 0.08, 60]    // top-left curl
            ]
            for (var b = 0; b < bands.length; ++b) {
                var bd = bands[b], phase = rnd() * 6.28, freq = 1.2 + rnd() * 1.4
                for (var i = 0; i < bd[6]; ++i) {
                    var t = i / bd[6]
                    var x = (bd[0] + (bd[2] - bd[0]) * t) * W + (rnd() - 0.5) * W * 0.06
                    var y = (bd[1] + (bd[3] - bd[1]) * t + bd[4] * Math.sin(t * 6.28 * freq + phase)) * H + (rnd() - 0.5) * H * 0.04
                    var r = bd[5] * Math.min(W, H) * (0.5 + rnd())
                    var c = rnd() < 0.25 ? deep : (rnd() < 0.5 ? light : smoke)
                    puff(x, y, r, (0.05 + rnd() * 0.07) * strength, c)
                }
            }
            for (var k = 0; k < 90; ++k)   // a few fine specks
                puff(rnd() * W, rnd() * H, 1.5 + rnd() * 3, (0.25 + rnd() * 0.4) * strength, rnd() < 0.5 ? smoke : light)
        }
    }

    // ---- Second Son paper backdrop: the GIF's own background colour behind the whole left side
    // (no copy of the picture); the GIF's left edge fades into it, so the two halves join without a border.
    Rectangle {
        id: paper
        visible: page.paperMode
        anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.right: artPanel.left
        color: Backend.artBackground !== "" ? Backend.artBackground : "#fbf6f1"
    }

    // ---- left side: game, state and quick settings (scrolls when the window is short) -------------
    Flickable {
        id: stateFlick
        anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.right: artPanel.left
        anchors.leftMargin: 32; anchors.rightMargin: 8
        contentWidth: width; contentHeight: stateCol.implicitHeight + 52
        // Opens at the top (and again after switching games), whatever loaded below meanwhile.
        Timer { id: toTop; interval: 3000 }
        onContentHeightChanged: if (toTop.running) contentY = 0
        onContentYChanged: if (toTop.running && !moving && contentY !== 0) contentY = 0
        Component.onCompleted: toTop.start()
        Connections { target: Backend; function onGameDirChanged() { stateFlick.contentY = 0; toTop.restart() } }
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {
            id: stateBar
            contentItem: Rectangle { implicitWidth: 6; radius: 3; color: stateBar.pressed ? Theme.ghostLineHover : Theme.ghostLine
                                     opacity: stateBar.active || stateBar.hovered ? 1 : 0
                                     Behavior on opacity { NumberAnimation { duration: 250 } } }
            background: Item { }
        }
        Column {
            id: stateCol
            y: 26; width: stateFlick.width - 18; spacing: 16

            Text { text: Backend.heroKicker; color: page.paperMode ? "#3a1f12" : page.accent; font.family: Theme.fontDisplay; font.variableAxes: ({ "wght": 700 }); font.pixelSize: 15
                   font.weight: Font.Bold; font.capitalization: Font.AllUppercase; font.letterSpacing: 4.5 }

            Rectangle {   // the data folder has no saves but another place does (typically after an update)
                visible: Saves.homeHint !== ""
                width: parent.width; height: hintCol.implicitHeight + 24
                radius: 10; color: Qt.rgba(0.05, 0.06, 0.07, 0.86); border.width: 1; border.color: Qt.rgba(Theme.ok.r, Theme.ok.g, Theme.ok.b, 0.6)
                Column {
                    id: hintCol
                    x: 16; y: 12; width: parent.width - 32; spacing: 6
                    Text { width: parent.width; wrapMode: Text.WrapAnywhere; text: Saves.homeHint; color: Theme.text
                           font.family: Theme.fontText; font.pixelSize: 13; lineHeight: 1.3; lineHeightMode: Text.ProportionalHeight }
                    Text { text: Theme.tr("saves_home_open") + " →"; color: Theme.ok; font.family: Theme.fontText; font.pixelSize: 13; font.weight: Font.Bold
                           MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: page.openSaves() } }
                }
            }

            Card {   // which game Play starts, and whether everything is ready for it
                Row {   // Second Son or First Light (each keeps its own folder and saves)
                    spacing: 12
                    RowLabel { text: Theme.tr("game_label"); anchors.verticalCenter: parent.verticalCenter }
                    Select {
                        accent: page.accent; width: Math.min(300, stateCol.width - 32 - page.labelWidth - 12)
                        enabled: Backend.playState === "idle"
                        model: Backend.gameOptions
                        currentIndex: Backend.gameIndex
                        onActivated: (i) => Backend.setGame(Backend.gameOptions[i].value)
                    }
                }
                Text { text: Backend.statusTitle; color: Theme.textMuted; font.family: Theme.fontDisplay; font.variableAxes: ({ "wght": 700 }); font.pixelSize: 16
                       font.weight: Font.Bold; font.capitalization: Font.AllUppercase; font.letterSpacing: 0.9 }
                Flow {
                    width: parent.width; spacing: 8
                    Repeater { model: Backend.chips; Chip { text: modelData.text; level: modelData.level } }
                }
                Column {   // verify game files: every art file's size and SHA-256 against the reference list
                    width: parent.width; spacing: 6
                    visible: Backend.gameDir !== ""
                    Row {
                        spacing: 12
                        GhostButton {
                            compact: true
                            text: Backend.verifyRunning ? Theme.tr("verify_stop") : Theme.tr("verify_button")
                            onClicked: Backend.verifyRunning ? Backend.stopVerify() : Backend.verifyGame()
                        }
                        Text { visible: Backend.verifyRunning; anchors.verticalCenter: parent.verticalCenter
                               text: Math.floor(Math.max(0, Backend.verifyProgress) * 100) + "%"; color: Theme.textMuted
                               font.family: Theme.fontText; font.pixelSize: 13; font.weight: Font.Bold }
                    }
                    Rectangle {
                        visible: Backend.verifyRunning
                        width: parent.width; height: 4; radius: 2; color: Theme.cardLine
                        Rectangle { width: parent.width * Math.max(0, Backend.verifyProgress); height: parent.height; radius: 2; color: page.accent }
                    }
                    Hint { visible: Backend.verifyText !== ""; text: Backend.verifyText
                           color: Backend.verifyLevel === "ok" ? Theme.ok : Backend.verifyLevel === "bad" ? Theme.bad
                                : Backend.verifyLevel === "warn" ? Theme.warn : Theme.textDim }
                }
            }

            Card {   // quick settings for the next start
                Column {
                    width: parent.width; spacing: 6
                    Row {
                        spacing: 12
                        RowLabel { text: Theme.tr("home_fps_limit"); anchors.verticalCenter: parent.verticalCenter }
                        Select {
                            accent: page.accent; width: Math.min(300, stateCol.width - 32 - page.labelWidth - 12)
                            enabled: Backend.playState === "idle"
                            model: Backend.fpsLimitOptions
                            currentIndex: Backend.fpsLimitIndex
                            onActivated: (i) => Backend.setFpsLimit(Backend.fpsLimitOptions[i].value)
                            Accessible.name: Theme.tr("home_fps_limit")
                        }
                    }
                    Hint { text: Theme.tr("home_fps_limit_hint") }
                }
                Rectangle { width: parent.width; height: 1; color: Theme.cardLine }
                Column {   // upscaler: Off / FSR 1 / FSR 3.1 / DLSS, and the quality of the temporal ones (next start)
                    width: parent.width; spacing: 6
                    Row {
                        spacing: 12
                        RowLabel { text: Theme.tr("upscaler_label"); anchors.verticalCenter: parent.verticalCenter }
                        Select {
                            accent: page.accent; width: Math.min(300, stateCol.width - 32 - page.labelWidth - 12)
                            model: Backend.upscalerOptions
                            currentIndex: Backend.upscalerIndex
                            onActivated: (i) => {
                                var value = Backend.upscalerOptions[i].value
                                Backend.setUpscaler(value)
                                if (value === "3") Graphics.autoDlss()   // DLSS: fetch its files at once
                            }
                        }
                    }
                    Column {   // the automatic DLSS download: progress, then ready or what is missing
                        visible: Backend.upscalerIndex === 3 && (Graphics.dlssBusy || Graphics.dlssMessage !== "")
                        width: parent.width; spacing: 6
                        Rectangle {
                            visible: Graphics.dlssBusy
                            width: parent.width; height: 4; radius: 2; color: Theme.cardLine
                            Rectangle { width: parent.width * Math.max(0, Graphics.dlssProgress); height: parent.height; radius: 2; color: Theme.ok }
                        }
                        Text { visible: Graphics.dlssBusy && Graphics.dlssProgress > 0; text: Graphics.dlssProgressText; color: Theme.textDim
                               font.family: Theme.fontText; font.pixelSize: 12 }
                        Hint { text: Graphics.dlssMessage
                               color: Graphics.dlssMessageTone === "good" ? Theme.ok : Graphics.dlssMessageTone === "bad" ? Theme.warn : Theme.textSoft }
                    }
                    Row {
                        visible: Backend.upscalerHasQuality
                        spacing: 12
                        RowLabel { text: Theme.tr("upscaler_quality_label"); anchors.verticalCenter: parent.verticalCenter }
                        Select {
                            accent: page.accent; width: Math.min(300, stateCol.width - 32 - page.labelWidth - 12)
                            model: Backend.upscalerQualityOptions
                            currentIndex: Backend.upscalerQualityIndex
                            onActivated: (i) => Backend.setUpscalerQuality(Backend.upscalerQualityOptions[i].value)
                        }
                    }
                    Hint { text: Theme.tr("upscaler_hint") }
                }
            }

            Card {   // trophies showcase (Second Son, First Light): the game's icons, earned ones lit with a gold frame
                visible: Backend.trophies.length > 0
                Row {
                    width: parent.width; spacing: 12
                    Text { text: Theme.tr("trophies_title"); color: "#fff"; font.family: Theme.fontDisplay; font.variableAxes: ({ "wght": 700 })
                           font.pixelSize: 16; font.weight: Font.Bold; font.capitalization: Font.AllUppercase; font.letterSpacing: 0.9
                           anchors.verticalCenter: parent.verticalCenter }
                    Text { text: Theme.tr(Backend.gameIndex === 1 ? "trophies_count_fl" : "trophies_count").replace("{earned}", Backend.trophiesEarned).replace("{total}", Backend.trophies.length)
                           color: Theme.textMuted; font.family: Theme.fontText; font.pixelSize: 13; font.weight: Font.DemiBold
                           anchors.verticalCenter: parent.verticalCenter }
                }
                Rectangle {   // progress, like the in-game menu's bar
                    width: parent.width; height: 6; radius: 3; color: Theme.cardLine
                    Rectangle { width: parent.width * (Backend.trophies.length ? Backend.trophiesEarned / Backend.trophies.length : 0)
                                height: parent.height; radius: 3; color: "#eebf4c" }
                }
                Flow {
                    id: trophyGrid
                    width: parent.width; spacing: 8
                    readonly property int side: 44
                    Repeater {
                        model: Backend.trophies
                        Item {
                            width: trophyGrid.side; height: trophyGrid.side
                            Rectangle { anchors.fill: parent; radius: 6; color: "#0e1014" }
                            Image {
                                anchors.fill: parent; anchors.margins: 2
                                source: modelData.icon; asynchronous: true; smooth: true; mipmap: true
                                sourceSize.width: 96; sourceSize.height: 96
                                opacity: modelData.earned ? 1.0 : 0.3
                            }
                            Rectangle {   // gold frame on earned trophies (the overlay's colour, 238,191,76)
                                anchors.fill: parent; radius: 6; color: "transparent"
                                border.width: modelData.earned ? 2 : (tip.containsMouse ? 1 : 0)
                                border.color: modelData.earned ? "#eebf4c" : Theme.ghostLineHover
                            }
                            MouseArea { id: tip; anchors.fill: parent; hoverEnabled: true }
                            ToolTip {
                                visible: tip.containsMouse
                                delay: 150
                                contentItem: Column {
                                    spacing: 4
                                    Text { text: modelData.name; color: "#fff"; font.family: Theme.fontText; font.pixelSize: 14; font.weight: Font.Bold }
                                    Text { width: 260; text: modelData.requirement; wrapMode: Text.WordWrap; color: Theme.textSoft
                                           font.family: Theme.fontText; font.pixelSize: 12 }
                                    Text { text: modelData.status; color: modelData.earned ? "#eebf4c" : Theme.textDim
                                           font.family: Theme.fontText; font.pixelSize: 12; font.weight: Font.DemiBold }
                                }
                                background: Rectangle { color: Theme.card; radius: 8; border.width: 1; border.color: Theme.ghostLine }
                            }
                        }
                    }
                }
                Hint { text: Theme.tr(Backend.gameIndex === 1 ? "trophies_hint_fl" : "trophies_hint") }
            }

            Item {
                visible: Backend.showFirstRun || Backend.notice !== ""
                width: parent.width; height: warnText.implicitHeight + 24
                Rectangle { anchors.fill: parent; radius: 10
                            color: page.backdropMode ? Qt.rgba(0.22, 0.09, 0.03, 0.74) : Qt.rgba(Theme.card.r, Theme.card.g, Theme.card.b, 0.86) }
                Rectangle { x: 1; y: 1; width: 3; height: parent.height - 2; color: Theme.warn }
                Text { id: warnText; x: 16; y: 12; width: parent.width - 30; wrapMode: Text.WordWrap
                       text: Backend.notice !== "" ? Backend.notice : Theme.tr("first_run_warning")
                       color: Theme.textDim; font.family: Theme.fontText; font.pixelSize: 13; lineHeight: 1.4
                       lineHeightMode: Text.ProportionalHeight }
            }
        }
    }

    // ---- game log, only while the game runs or after it failed --------------------------------
    Rectangle {
        visible: Backend.playState !== "idle" || (Backend.logText !== "" && Backend.logShown)
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        height: 140; color: "#0a0b0e"; border.width: 1; border.color: Theme.cardLine
        Flickable {
            id: flick
            anchors.fill: parent; anchors.margins: 10; clip: true
            contentHeight: logText.implicitHeight
            onContentHeightChanged: contentY = Math.max(0, contentHeight - height)
            Text { id: logText; width: flick.width; text: Backend.logText; color: Theme.textDim
                   font.family: "monospace"; font.pixelSize: 11; wrapMode: Text.WrapAnywhere }
        }
    }
}
