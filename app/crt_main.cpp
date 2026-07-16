#include <QDir>
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QStandardPaths>

#include "crt/filter/qt/filter_preset_store.hpp"

int main(int argc, char* argv[]) {
    QGuiApplication app(argc, argv);
    QCoreApplication::setOrganizationName("CRT");
    QCoreApplication::setApplicationName("CAN Research Tool");

    const QString projectDir = QStandardPaths::writableLocation(QStandardPaths::AppDataLocation);
    QDir{}.mkpath(projectDir);

    crt::filter::qt::FilterPresetStore filterStore;
    filterStore.setProjectFile(projectDir + "/filter-presets.json");
    filterStore.load();

    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty("filterStore", &filterStore);
    engine.rootContext()->setContextProperty("crtProjectPath", projectDir);
    engine.loadFromModule("CRT.App", "Main");

    if (engine.rootObjects().isEmpty()) {
        return 1;
    }

    return app.exec();
}
