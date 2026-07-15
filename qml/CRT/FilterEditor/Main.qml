import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    width: 1280
    height: 760
    visible: true
    title: "CRT — Global Filters"

    property int selectedRow: presetList.currentIndex
    property var currentPreset: selectedRow >= 0 ? filterStore.preset(selectedRow) : ({})
    property var testResult: ({ state: "", reason: "" })

    header: ToolBar {
        RowLayout {
            anchors.fill: parent
            anchors.margins: 10
            Label { text: "Filtry"; font.pixelSize: 22; font.bold: true }
            Item { Layout.fillWidth: true }
            Label { text: "Aktywne: " + filterStore.activeCount }
            Button { text: "Zapisz"; onClicked: filterStore.save() }
        }
    }

    SplitView {
        anchors.fill: parent

        Pane {
            SplitView.preferredWidth: 340
            ColumnLayout {
                anchors.fill: parent
                spacing: 8
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "Presety"; font.bold: true; Layout.fillWidth: true }
                    Button {
                        text: "+"
                        onClicked: {
                            const row = filterStore.createPreset("Nowy filtr")
                            presetList.currentIndex = row
                            currentPreset = filterStore.preset(row)
                        }
                    }
                    Button {
                        text: "−"
                        enabled: selectedRow >= 0
                        onClicked: {
                            filterStore.removePreset(selectedRow)
                            presetList.currentIndex = Math.min(selectedRow, filterStore.rowCount() - 1)
                        }
                    }
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
                            currentPreset = filterStore.preset(index)
                        }
                        contentItem: RowLayout {
                            CheckBox {
                                checked: model.enabled
                                onToggled: filterStore.setEnabled(index, checked)
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                Label { text: model.name; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                                Label { text: model.valid ? (model.shortcut || "Brak skrótu") : model.validationError; color: model.valid ? palette.mid : palette.accent; font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true }
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
                                currentPreset = filterStore.preset(selectedRow)
                            }
                        }
                        Label { text: "Skrót" }
                        TextField {
                            Layout.fillWidth: true
                            placeholderText: "np. Ctrl+1"
                            text: currentPreset.shortcut || ""
                            onEditingFinished: filterStore.setShortcut(selectedRow, text)
                        }
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
                                    ComboBox { model: ["canId", "frameFormat", "dlc", "relativeTimeUs"]; currentIndex: Math.max(0, model.indexOf(modelData.field)) }
                                    ComboBox { model: ["eq", "ne", "gt", "ge", "lt", "le", "between", "outside", "in", "notIn"]; currentIndex: Math.max(0, model.indexOf(modelData.operator)) }
                                    TextField { Layout.fillWidth: true; text: modelData.values ? modelData.values.join(", ") : ""; placeholderText: "wartość / wartości" }
                                }
                            }
                        }
                        RowLayout {
                            Button { text: "+ Warunek"; enabled: false; ToolTip.text: "Dodawanie do dowolnej gałęzi będzie aktywowane po wprowadzeniu modelu drzewa Qt" }
                            Button { text: "+ Grupa AND"; enabled: false }
                            Button { text: "+ Grupa OR"; enabled: false }
                        }
                    }
                }

                GroupBox {
                    title: "Test na ramce"
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
                                    canId: parseInt(raw, 16),
                                    dlc: testDlc.value,
                                    extended: testFormat.currentIndex === 1,
                                    relativeTimeUs: Number(testTime.text)
                                })
                            }
                        }
                        Label {
                            Layout.columnSpan: 3
                            text: testResult.state ? testResult.state.toUpperCase() + (testResult.reason ? " — " + testResult.reason : "") : ""
                            font.bold: true
                        }
                    }
                }

                Label {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    text: "Etap 2 przygotowuje globalny menedżer presetów i edytor. Integracja z prawdziwym Live Capture pozostaje w Etapie 3."
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
