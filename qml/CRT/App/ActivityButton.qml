import QtQuick
import QtQuick.Controls

ToolButton {
    id: control
    required property string label
    required property string pageKey
    property bool selected: false

    width: 92
    height: 64
    text: label
    checkable: true
    checked: selected
    display: AbstractButton.TextOnly
    font.pixelSize: 13

    background: Rectangle {
        radius: 6
        color: control.checked ? palette.highlight : (control.hovered ? palette.midlight : "transparent")
        border.color: control.checked ? palette.highlight : palette.mid
    }
}
