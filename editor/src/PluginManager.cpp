#include "PluginManager.hpp"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLibrary>
#include <QRegularExpression>

namespace {
PluginDescriptor readManifest(const QFileInfo &manifest)
{
    PluginDescriptor descriptor;
    descriptor.manifestPath = manifest.canonicalFilePath();
    if (manifest.isSymLink()) {
        descriptor.error = QStringLiteral("Plugin manifests may not be symbolic links.");
        return descriptor;
    }
    QFile file(manifest.absoluteFilePath());
    if (!file.open(QIODevice::ReadOnly) || file.size() > 128 * 1024) {
        descriptor.error = QStringLiteral("Cannot read plugin manifest or it exceeds 128 KiB.");
        return descriptor;
    }
    QJsonParseError parseError;
    const auto document = QJsonDocument::fromJson(file.readAll(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
        descriptor.error = QStringLiteral("Invalid plugin manifest JSON.");
        return descriptor;
    }
    const auto object = document.object();
    descriptor.id = object.value(QStringLiteral("id")).toString();
    descriptor.name = object.value(QStringLiteral("name")).toString(descriptor.id);
    descriptor.version = object.value(QStringLiteral("version")).toString();
    descriptor.apiVersion = object.value(QStringLiteral("apiVersion")).toInt();
    const auto libraryName = object.value(QStringLiteral("library")).toString();
    static const QRegularExpression IdPattern(QStringLiteral(R"(^[a-z0-9]+(?:[.-][a-z0-9]+)*$)"));
    if (!IdPattern.match(descriptor.id).hasMatch() || descriptor.name.isEmpty() || libraryName.isEmpty()) {
        descriptor.error = QStringLiteral("Manifest requires a safe id, name and library.");
        return descriptor;
    }
    const QDir root(manifest.absolutePath());
    const QFileInfo library(root.absoluteFilePath(libraryName));
    const auto canonicalRoot = QFileInfo(root.absolutePath()).canonicalFilePath();
    const auto canonicalLibrary = library.canonicalFilePath();
    if (canonicalLibrary.isEmpty() || library.isSymLink() || !canonicalLibrary.startsWith(canonicalRoot + QDir::separator())
        || !QLibrary::isLibrary(canonicalLibrary)) {
        descriptor.error = QStringLiteral("Plugin library must be a regular native library inside its manifest directory.");
        return descriptor;
    }
    descriptor.libraryPath = canonicalLibrary;
    if (descriptor.apiVersion != ForgeEditor::PluginApiVersion) {
        descriptor.error = QStringLiteral("Plugin API %1 is incompatible with editor API %2.")
                               .arg(descriptor.apiVersion)
                               .arg(ForgeEditor::PluginApiVersion);
    }
    return descriptor;
}
} // namespace

PluginManager::PluginManager(QStringList searchDirectories)
    : m_searchDirectories(std::move(searchDirectories))
{
    m_searchDirectories.removeDuplicates();
}

PluginManager::~PluginManager()
{
    unloadAll();
}

QList<PluginDescriptor> PluginManager::discover() const
{
    QList<PluginDescriptor> descriptors;
    QSet<QString> seenIds;
    for (const auto &directory : m_searchDirectories) {
        const QDir root(directory);
        const auto manifests = root.entryInfoList({QStringLiteral("*.forgeplugin.json")}, QDir::Files | QDir::Readable, QDir::Name);
        for (const auto &manifest : manifests) {
            auto descriptor = readManifest(manifest);
            if (!descriptor.id.isEmpty() && seenIds.contains(descriptor.id)) {
                descriptor.error = QStringLiteral("Duplicate plugin id; the first discovered manifest wins.");
            } else if (!descriptor.id.isEmpty()) {
                seenIds.insert(descriptor.id);
            }
            descriptors.append(descriptor);
        }
    }
    return descriptors;
}

QStringList PluginManager::loadEnabled(const QSet<QString> &enabledIds, ForgeEditor::EditorHost *host)
{
    unloadAll();
    QStringList messages;
    for (const auto &descriptor : discover()) {
        if (!enabledIds.contains(descriptor.id)) {
            continue;
        }
        if (!descriptor.error.isEmpty()) {
            messages.append(QStringLiteral("%1: %2").arg(descriptor.name, descriptor.error));
            continue;
        }
        auto *loader = new QPluginLoader(descriptor.libraryPath);
        QObject *instance = loader->instance();
        auto *plugin = qobject_cast<ForgeEditor::IEditorPlugin *>(instance);
        if (plugin == nullptr) {
            messages.append(QStringLiteral("%1: %2").arg(descriptor.name, loader->errorString()));
            delete loader;
            continue;
        }
        if (plugin->pluginId() != descriptor.id || plugin->apiVersion() != ForgeEditor::PluginApiVersion) {
            messages.append(QStringLiteral("%1: runtime identity/API does not match its manifest.").arg(descriptor.name));
            loader->unload();
            delete loader;
            continue;
        }
        QString error;
        if (!plugin->initialize(host, &error)) {
            messages.append(QStringLiteral("%1: %2").arg(descriptor.name, error));
            loader->unload();
            delete loader;
            continue;
        }
        m_loaders.append(loader);
        m_plugins.append(plugin);
        messages.append(QStringLiteral("Loaded %1 %2").arg(descriptor.name, descriptor.version));
    }
    return messages;
}

void PluginManager::unloadAll()
{
    for (auto *plugin : std::as_const(m_plugins)) {
        plugin->shutdown();
    }
    m_plugins.clear();
    for (auto *loader : std::as_const(m_loaders)) {
        loader->unload();
        delete loader;
    }
    m_loaders.clear();
}
