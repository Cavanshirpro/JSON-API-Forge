#pragma once

#include <QList>
#include <QPluginLoader>
#include <QSet>
#include <QStringList>

#include <forgeeditor/IEditorPlugin.hpp>

struct PluginDescriptor {
    QString id;
    QString name;
    QString version;
    QString manifestPath;
    QString libraryPath;
    QString sha256;
    QStringList permissions;
    int apiVersion = 0;
    QString error;
};

struct PluginImportResult {
    bool success = false;
    QString pluginId;
    QString pluginName;
    QString version;
    QString installDirectory;
    QString error;
};

class PluginManager final {
public:
    explicit PluginManager(QStringList searchDirectories);
    ~PluginManager();

    [[nodiscard]] QList<PluginDescriptor> discover() const;
    [[nodiscard]] static PluginImportResult importZip(const QString &archivePath,
                                                       const QString &destinationDirectory);
    QStringList loadEnabled(const QSet<QString> &enabledIds, ForgeEditor::EditorHost *host);
    void unloadAll();

private:
    QStringList m_searchDirectories;
    QList<QPluginLoader *> m_loaders;
    QList<ForgeEditor::IEditorPlugin *> m_plugins;
};
