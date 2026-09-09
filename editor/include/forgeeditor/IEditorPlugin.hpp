#pragma once

#include <QAction>
#include <QDockWidget>
#include <QJsonObject>
#include <QObject>
#include <QString>

namespace ForgeEditor {

inline constexpr int PluginApiVersion = 2;

class EditorHost {
public:
    virtual ~EditorHost() = default;
    virtual void addPaletteComponent(const QString &label, const QString &collection, const QJsonObject &documentTemplate) = 0;
    virtual void addGraphNodeType(const QString &label, const QString &type, const QJsonObject &defaultProperties) = 0;
    virtual void addToolAction(QAction *action) = 0;
    virtual void addDockWidget(Qt::DockWidgetArea area, QDockWidget *dock) = 0;
    virtual void showStatusMessage(const QString &message, int timeoutMs = 4000) = 0;
};

class IEditorPlugin {
public:
    virtual ~IEditorPlugin() = default;
    [[nodiscard]] virtual QString pluginId() const = 0;
    [[nodiscard]] virtual QString displayName() const = 0;
    [[nodiscard]] virtual int apiVersion() const = 0;
    virtual bool initialize(EditorHost *host, QString *errorMessage) = 0;
    virtual void shutdown() = 0;
};

} // namespace ForgeEditor

#define ForgeEditorPluginInterface_iid "dev.jsonapiforge.EditorPlugin/2.0"
Q_DECLARE_INTERFACE(ForgeEditor::IEditorPlugin, ForgeEditorPluginInterface_iid)
