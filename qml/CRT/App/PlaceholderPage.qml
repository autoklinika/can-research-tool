import QtQuick
import QtQuick.Controls

Page {
    required property string titleText

    Label {
        anchors.centerIn: parent
        text: titleText + " — moduł zostanie dodany w kolejnych etapach"
        font.pixelSize: 22
    }
}
