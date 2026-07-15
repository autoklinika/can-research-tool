#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QStandardPaths>
#include <QDir>

#include "crt/filter/qt/filter_preset_store.hpp"

int main(int argc, char* argv[]) {
    QGuiApplication app(argc, argv);
    QCoreApplication::setOrganizationName("CRT");
    QCoreApplication::setApplicationName("CAN Research Tool");

    const QString projectDir = QStandardPaths::writableLocation(QStandardPaths::AppDataLocation);
    QDir{}.mkpath(projectDir);

    crt::filter::qt::FilterPresetStore store;
    store.setProjectFile(projectDir + "/filter-presets.json");
    store.load();

    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty("filterStore", &store);
    engine.loadFromModule("CRT.FilterEditor", "Main");
    if (engine.rootObjects().isEmpty()) return 1;
    return app.exec();
}
