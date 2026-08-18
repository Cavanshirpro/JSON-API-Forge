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
    int apiVersion = 0;
    QString error;
};

class PluginManager final {
public:
    explicit PluginManager(QStringList searchDirectories);
    ~PluginManager();

    [[nodiscard]] QList<PluginDescriptor> discover() const;
    QStringList loadEnabled(const QSet<QString> &enabledIds, ForgeEditor::EditorHost *host);
    void unloadAll();

private:
    QStringList m_searchDirectories;
    QList<QPluginLoader *> m_loaders;
    QList<ForgeEditor::IEditorPlugin *> m_plugins;
};
