import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: window
    width: 1440
    height: 900
    visible: true
    title: "CAN Research Tool"

    property string currentPage: "capture"

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Pane {
            Layout.preferredWidth: 112
            Layout.fillHeight: true
            padding: 10

            ColumnLayout {
                anchors.fill: parent
                spacing: 8

                Label {
                    text: "CRT"
                    font.pixelSize: 26
                    font.bold: true
                    Layout.alignment: Qt.AlignHCenter
                }

                ActivityButton { label: "Live"; pageKey: "capture"; selected: window.currentPage === pageKey; onClicked: window.currentPage = pageKey }
                ActivityButton { label: "Sesje"; pageKey: "sessions"; selected: window.currentPage === pageKey; onClicked: window.currentPage = pageKey }
                ActivityButton { label: "Filtry"; pageKey: "filters"; selected: window.currentPage === pageKey; onClicked: window.currentPage = pageKey }
                ActivityButton { label: "Analiza"; pageKey: "analysis"; selected: window.currentPage === pageKey; onClicked: window.currentPage = pageKey }
                Item { Layout.fillHeight: true }
                ActivityButton { label: "Ustawienia"; pageKey: "settings"; selected: window.currentPage === pageKey; onClicked: window.currentPage = pageKey }
            }
        }

        Rectangle { Layout.preferredWidth: 1; Layout.fillHeight: true; color: palette.mid }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: window.currentPage === "capture" ? 0
                          : window.currentPage === "sessions" ? 1
                          : window.currentPage === "filters" ? 2
                          : window.currentPage === "analysis" ? 3 : 4

            PlaceholderPage { titleText: "Live Capture" }
            PlaceholderPage { titleText: "Zapisane sesje" }
            FiltersPage { }
            PlaceholderPage { titleText: "Analiza" }
            PlaceholderPage { titleText: "Ustawienia" }
        }
    }
}
