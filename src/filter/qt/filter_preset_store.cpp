#include "crt/filter/qt/filter_preset_store.hpp"

#include "crt/filter/filter_engine.hpp"

#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QUuid>

namespace crt::filter::qt {
namespace {

QString logicalName(LogicalOperator op) {
    switch (op) { case LogicalOperator::And: return "and"; case LogicalOperator::Or: return "or"; case LogicalOperator::Not: return "not"; }
    return "and";
}
LogicalOperator logicalFrom(const QString& value) {
    if (value == "or") return LogicalOperator::Or;
    if (value == "not") return LogicalOperator::Not;
    return LogicalOperator::And;
}
QString fieldName(FilterField field) {
    switch (field) { case FilterField::CanId: return "canId"; case FilterField::FrameFormat: return "frameFormat"; case FilterField::Dlc: return "dlc"; case FilterField::RelativeTimeUs: return "relativeTimeUs"; }
    return "canId";
}
FilterField fieldFrom(const QString& value) {
    if (value == "frameFormat") return FilterField::FrameFormat;
    if (value == "dlc") return FilterField::Dlc;
    if (value == "relativeTimeUs") return FilterField::RelativeTimeUs;
    return FilterField::CanId;
}
QString opName(NumericOperator op) {
    static const char* names[] = {"eq","ne","gt","ge","lt","le","between","outside","in","notIn"};
    return names[static_cast<int>(op)];
}
NumericOperator opFrom(const QString& value) {
    if (value == "ne") return NumericOperator::NotEqual; if (value == "gt") return NumericOperator::Greater;
    if (value == "ge") return NumericOperator::GreaterOrEqual; if (value == "lt") return NumericOperator::Less;
    if (value == "le") return NumericOperator::LessOrEqual; if (value == "between") return NumericOperator::BetweenInclusive;
    if (value == "outside") return NumericOperator::OutsideInclusive; if (value == "in") return NumericOperator::InSet;
    if (value == "notIn") return NumericOperator::NotInSet; return NumericOperator::Equal;
}
QJsonObject nodeToJson(const FilterNodePtr& node) {
    QJsonObject out;
    if (!node) return out;
    if (const auto* group = std::get_if<FilterGroup>(&node->value)) {
        out["type"] = "group"; out["operator"] = logicalName(group->op);
        QJsonArray children; for (const auto& child : group->children) children.append(nodeToJson(child));
        out["children"] = children;
    } else {
        const auto& c = std::get<FilterCondition>(node->value);
        out["type"] = "condition"; out["id"] = QString::fromStdString(c.id); out["label"] = QString::fromStdString(c.label);
        out["field"] = fieldName(c.expression.field); out["operator"] = opName(c.expression.op);
        QJsonArray values; for (auto value : c.expression.values) values.append(QString::number(value)); out["values"] = values;
    }
    return out;
}
FilterNodePtr nodeFromJson(const QJsonObject& object, QString* error) {
    if (object["type"] == "group") {
        std::vector<FilterNodePtr> children;
        for (const auto& value : object["children"].toArray()) children.push_back(nodeFromJson(value.toObject(), error));
        return makeGroup(logicalFrom(object["operator"].toString()), std::move(children));
    }
    if (object["type"] != "condition") { if (error) *error = "Unknown filter node type"; return {}; }
    std::vector<std::uint64_t> values;
    for (const auto& value : object["values"].toArray()) values.push_back(value.toString().toULongLong());
    return makeCondition(object["id"].toString().toStdString(), object["label"].toString().toStdString(),
                         fieldFrom(object["field"].toString()), opFrom(object["operator"].toString()), std::move(values));
}
QString modeName(FilterMode mode) { return mode == FilterMode::Exclude ? "exclude" : mode == FilterMode::Highlight ? "highlight" : "include"; }
FilterMode modeFrom(const QString& value) { return value == "exclude" ? FilterMode::Exclude : value == "highlight" ? FilterMode::Highlight : FilterMode::Include; }

} // namespace

FilterPresetStore::FilterPresetStore(QObject* parent) : QAbstractListModel(parent) {}
int FilterPresetStore::rowCount(const QModelIndex& parent) const { return parent.isValid() ? 0 : static_cast<int>(presets_.size()); }
QVariant FilterPresetStore::data(const QModelIndex& index, int role) const {
    if (!index.isValid() || index.row() < 0 || index.row() >= rowCount()) return {};
    const auto& p = presets_[static_cast<std::size_t>(index.row())];
    ValidationResult validation; FilterCompiler{}.compile(p, &validation);
    QString error; for (const auto& issue : validation.issues) if (issue.severity == ValidationIssue::Severity::Error) { error = QString::fromStdString(issue.message); break; }
    switch (role) {
        case IdRole: return QString::fromStdString(p.id); case NameRole: return QString::fromStdString(p.name);
        case DescriptionRole: return QString::fromStdString(p.description); case EnabledRole: return p.enabled;
        case ShortcutRole: return p.shortcut ? QString::fromStdString(*p.shortcut) : QString{};
        case ModeRole: return modeName(p.mode); case ValidRole: return error.isEmpty(); case ErrorRole: return error;
    }
    return {};
}
QHash<int,QByteArray> FilterPresetStore::roleNames() const { return {{IdRole,"presetId"},{NameRole,"name"},{DescriptionRole,"description"},{EnabledRole,"enabled"},{ShortcutRole,"shortcut"},{ModeRole,"mode"},{ValidRole,"valid"},{ErrorRole,"validationError"}}; }
QString FilterPresetStore::projectFile() const { return projectFile_; }
void FilterPresetStore::setProjectFile(const QString& path) { if (path == projectFile_) return; projectFile_ = path; emit projectFileChanged(); }
int FilterPresetStore::activeCount() const { int count = 0; for (const auto& p : presets_) if (p.enabled) ++count; return count; }

bool FilterPresetStore::load() {
    QFile file(projectFile_); if (!file.exists()) return true;
    if (!file.open(QIODevice::ReadOnly)) { emit persistenceError(file.errorString()); return false; }
    const auto document = QJsonDocument::fromJson(file.readAll());
    if (!document.isObject()) { emit persistenceError("Invalid filter project JSON"); return false; }
    std::vector<FilterPreset> loaded;
    for (const auto& value : document.object()["presets"].toArray()) { QString error; auto p = fromJson(value.toObject(), &error); if (!error.isEmpty()) { emit persistenceError(error); return false; } loaded.push_back(std::move(p)); }
    beginResetModel(); presets_ = std::move(loaded); endResetModel(); emit activeCountChanged(); return true;
}
bool FilterPresetStore::save() const {
    QJsonArray presets; for (const auto& p : presets_) presets.append(toJson(p));
    QJsonObject root{{"formatVersion",1},{"presets",presets}};
    QFile file(projectFile_); if (!file.open(QIODevice::WriteOnly|QIODevice::Truncate)) { emit persistenceError(file.errorString()); return false; }
    return file.write(QJsonDocument(root).toJson(QJsonDocument::Indented)) >= 0;
}
int FilterPresetStore::createPreset(const QString& name) {
    FilterPreset p; p.id = QUuid::createUuid().toString(QUuid::WithoutBraces).toStdString(); p.name = name.toStdString();
    p.root = makeGroup(LogicalOperator::And, {makeCondition("can-id","CAN ID",FilterField::CanId,NumericOperator::Equal,{0})});
    const int row = rowCount(); beginInsertRows({},row,row); presets_.push_back(std::move(p)); endInsertRows(); emit activeCountChanged(); return row;
}
bool FilterPresetStore::removePreset(int row) { if (row < 0 || row >= rowCount()) return false; const bool active = presets_[row].enabled; beginRemoveRows({},row,row); presets_.erase(presets_.begin()+row); endRemoveRows(); if (active) emit activeCountChanged(); return true; }
bool FilterPresetStore::setEnabled(int row, bool enabled) { if (row<0||row>=rowCount()) return false; presets_[row].enabled=enabled; emit dataChanged(index(row),index(row),{EnabledRole}); emit activeCountChanged(); return true; }
bool FilterPresetStore::setShortcut(int row,const QString& shortcut) { if(row<0||row>=rowCount()) return false; presets_[row].shortcut=shortcut.isEmpty()?std::nullopt:std::optional<std::string>(shortcut.toStdString()); emit dataChanged(index(row),index(row),{ShortcutRole}); return true; }
bool FilterPresetStore::renamePreset(int row,const QString& name) { if(row<0||row>=rowCount()||name.trimmed().isEmpty()) return false; presets_[row].name=name.toStdString(); emit dataChanged(index(row),index(row),{NameRole}); return true; }
QVariantMap FilterPresetStore::preset(int row) const { return row<0||row>=rowCount()?QVariantMap{}:toVariantMap(presets_[row]); }
bool FilterPresetStore::replacePreset(int row,const QVariantMap& definition) { if(row<0||row>=rowCount()) return false; QString error; auto replacement=fromVariantMap(definition,&error); if(!error.isEmpty()){emit persistenceError(error);return false;} presets_[row]=std::move(replacement); emit dataChanged(index(row),index(row)); emit activeCountChanged(); return true; }
QVariantMap FilterPresetStore::testPreset(int row,const QVariantMap& frame) const {
    if(row<0||row>=rowCount()) return {{"state","unavailable"},{"reason","Preset row is invalid"}};
    CanFrameRecord record; record.canId=frame.value("canId").toUInt(); record.dlc=static_cast<std::uint8_t>(frame.value("dlc").toUInt()); record.relativeTimeUs=frame.value("relativeTimeUs").toULongLong(); record.format=frame.value("extended").toBool()?FrameFormat::Extended:FrameFormat::Standard; record.hasData=record.dlc>0;
    ValidationResult validation; const auto compiled=FilterCompiler{}.compile(presets_[row],&validation); if(!compiled) return {{"state","unavailable"},{"reason",data(index(row),ErrorRole)}};
    const auto result=compiled->evaluate(FilterContext{&record}); const QString state=result.state==MatchState::Match?"match":result.state==MatchState::NoMatch?"noMatch":"unavailable"; return {{"state",state},{"reason",QString::fromStdString(result.reason)}};
}

QJsonObject FilterPresetStore::toJson(const FilterPreset& p) { QJsonObject o{{"formatVersion",static_cast<int>(p.formatVersion)},{"id",QString::fromStdString(p.id)},{"name",QString::fromStdString(p.name)},{"description",QString::fromStdString(p.description)},{"enabled",p.enabled},{"mode",modeName(p.mode)},{"root",nodeToJson(p.root)}}; if(p.shortcut)o["shortcut"]=QString::fromStdString(*p.shortcut); return o; }
FilterPreset FilterPresetStore::fromJson(const QJsonObject& o,QString* error) { FilterPreset p; p.formatVersion=static_cast<std::uint32_t>(o["formatVersion"].toInt(1)); p.id=o["id"].toString().toStdString(); p.name=o["name"].toString().toStdString(); p.description=o["description"].toString().toStdString(); p.enabled=o["enabled"].toBool(true); p.mode=modeFrom(o["mode"].toString()); if(o.contains("shortcut"))p.shortcut=o["shortcut"].toString().toStdString(); p.root=nodeFromJson(o["root"].toObject(),error); return p; }
QVariantMap FilterPresetStore::toVariantMap(const FilterPreset& p) { return toJson(p).toVariantMap(); }
FilterPreset FilterPresetStore::fromVariantMap(const QVariantMap& map,QString* error) { return fromJson(QJsonObject::fromVariantMap(map),error); }

} // namespace crt::filter::qt
