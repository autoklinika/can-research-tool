#pragma once

#include <QAbstractListModel>
#include <QJsonObject>
#include <QString>
#include <vector>

#include "crt/filter/filter_types.hpp"

namespace crt::filter::qt {

class FilterPresetStore final : public QAbstractListModel {
    Q_OBJECT
    Q_PROPERTY(QString projectFile READ projectFile WRITE setProjectFile NOTIFY projectFileChanged)
    Q_PROPERTY(int activeCount READ activeCount NOTIFY activeCountChanged)

public:
    enum Roles {
        IdRole = Qt::UserRole + 1,
        NameRole,
        DescriptionRole,
        EnabledRole,
        ShortcutRole,
        ModeRole,
        ValidRole,
        ErrorRole,
    };

    explicit FilterPresetStore(QObject* parent = nullptr);

    int rowCount(const QModelIndex& parent = {}) const override;
    QVariant data(const QModelIndex& index, int role) const override;
    QHash<int, QByteArray> roleNames() const override;

    QString projectFile() const;
    void setProjectFile(const QString& path);
    int activeCount() const;

    Q_INVOKABLE bool load();
    Q_INVOKABLE bool save() const;
    Q_INVOKABLE int createPreset(const QString& name);
    Q_INVOKABLE bool removePreset(int row);
    Q_INVOKABLE bool setEnabled(int row, bool enabled);
    Q_INVOKABLE bool setShortcut(int row, const QString& shortcut);
    Q_INVOKABLE bool renamePreset(int row, const QString& name);
    Q_INVOKABLE QVariantMap preset(int row) const;
    Q_INVOKABLE bool replacePreset(int row, const QVariantMap& definition);
    Q_INVOKABLE QVariantMap testPreset(int row, const QVariantMap& frame) const;

signals:
    void projectFileChanged();
    void activeCountChanged();
    void persistenceError(const QString& message) const;

private:
    static QJsonObject toJson(const FilterPreset& preset);
    static FilterPreset fromJson(const QJsonObject& object, QString* error);
    static QVariantMap toVariantMap(const FilterPreset& preset);
    static FilterPreset fromVariantMap(const QVariantMap& map, QString* error);

    QString projectFile_;
    std::vector<FilterPreset> presets_;
};

} // namespace crt::filter::qt
