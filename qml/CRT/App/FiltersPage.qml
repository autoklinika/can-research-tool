import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

Page {
    id: root
    property int selectedRow: presetList.currentIndex
    property var currentPreset: selectedRow >= 0 ? filterStore.preset(selectedRow) : ({})
    property var testResult: ({ state: "", reason: "" })

    header: ToolBar {
        RowLayout {
            anchors.fill: parent
            anchors.margins: 10
            Label { text: "Filtry"; font.pixelSize: 22; font.bold: true }
            Item { Layout.fillWidth: true }
            Label { text: "Zapis: wszystkie ramki"; font.bold: true }
            Label { text: "Aktywne filtry: " + filterStore.activeCount }
            Button { text: "Zapisz"; onClicked: filterStore.save() }
        }
    }

    SplitView {
        anchors.fill: parent

        Pane {
            SplitView.preferredWidth: 340
            ColumnLayout {
                anchors.fill: parent
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "Presety projektu"; font.bold: true; Layout.fillWidth: true }
                    Button {
                        text: "+"
                        onClicked: {
                            const row = filterStore.createPreset("Nowy filtr")
                            presetList.currentIndex = row
                            currentPreset = filterStore.preset(row)
                        }
                    }
                    Button { text: "−"; enabled: selectedRow >= 0; onClicked: filterStore.removePreset(selectedRow) }
                }

                ListView {
                    id: presetList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: filterStore
                    delegate: ItemDelegate {
                        width: ListView.view.width
                        highlighted: ListView.isCurrentItem
                        onClicked: {
                            presetList.currentIndex = index
                            root.currentPreset = filterStore.preset(index)
                        }
                        contentItem: RowLayout {
                            CheckBox { checked: model.enabled; onToggled: filterStore.setEnabled(index, checked) }
                            ColumnLayout {
                                Layout.fillWidth: true
                                Label { text: model.name; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                                Label { text: model.valid ? (model.shortcut || "Brak skrótu") : model.validationError; font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true }
                            }
                            Label { text: model.mode }
                        }
                    }
                }
            }
        }

        ScrollView {
            SplitView.fillWidth: true
            contentWidth: availableWidth

            ColumnLayout {
                width: parent.width
                spacing: 14
                enabled: selectedRow >= 0

                GroupBox {
                    title: "Preset"
                    Layout.fillWidth: true
                    GridLayout {
                        anchors.fill: parent
                        columns: 2
                        Label { text: "Nazwa" }
                        TextField {
                            Layout.fillWidth: true
                            text: currentPreset.name || ""
                            onEditingFinished: {
                                filterStore.renamePreset(selectedRow, text)
                                root.currentPreset = filterStore.preset(selectedRow)
                            }
                        }
                        Label { text: "Skrót" }
                        TextField { Layout.fillWidth: true; text: currentPreset.shortcut || ""; onEditingFinished: filterStore.setShortcut(selectedRow, text) }
                    }
                }

                GroupBox {
                    title: "Drzewo warunków"
                    Layout.fillWidth: true
                    ColumnLayout {
                        anchors.fill: parent
                        Label { text: "AND"; font.bold: true }
                        Repeater {
                            model: currentPreset.root && currentPreset.root.children ? currentPreset.root.children : []
                            delegate: Frame {
                                Layout.fillWidth: true
                                RowLayout {
                                    anchors.fill: parent
                                    Label { text: "Warunek"; font.bold: true }
                                    Label { text: modelData.field || "" }
                                    Label { text: modelData.operator || "" }
                                    Label { text: modelData.values ? modelData.values.join(", ") : ""; Layout.fillWidth: true }
                                }
                            }
                        }
                        Label { text: "Pełne operacje na zagnieżdżonym drzewie wymagają modelu QAbstractItemModel."; wrapMode: Text.WordWrap }
                    }
                }

                GroupBox {
                    title: "Test filtra na ramce"
                    Layout.fillWidth: true
                    GridLayout {
                        anchors.fill: parent
                        columns: 4
                        Label { text: "CAN ID" }
                        TextField { id: testCanId; text: "18FEAE30" }
                        Label { text: "DLC" }
                        SpinBox { id: testDlc; from: 0; to: 64; value: 8 }
                        Label { text: "Format" }
                        ComboBox { id: testFormat; model: ["STD", "EXT"]; currentIndex: 1 }
                        Label { text: "Czas [µs]" }
                        TextField { id: testTime; text: "0" }
                        Button {
                            text: "Sprawdź"
                            onClicked: {
                                const raw = testCanId.text.trim().replace(/^0x/i, "")
                                testResult = filterStore.testPreset(selectedRow, {
                                    canId: parseInt(raw, 16), dlc: testDlc.value,
                                    extended: testFormat.currentIndex === 1,
                                    relativeTimeUs: Number(testTime.text)
                                })
                            }
                        }
                        Label { Layout.columnSpan: 3; text: testResult.state ? testResult.state.toUpperCase() + (testResult.reason ? " — " + testResult.reason : "") : ""; font.bold: true }
                    }
                }
            }
        }
    }

    Connections {
        target: filterStore
        function onPersistenceError(message) { errorDialog.text = message; errorDialog.open() }
    }
    MessageDialog { id: errorDialog; title: "Błąd filtrów" }
}
