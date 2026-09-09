#include "PluginManager.hpp"

#include <QDir>
#include <QCryptographicHash>
#include <QFile>
#include <QFileInfo>
#include <QHash>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLibrary>
#include <QRegularExpression>
#include <QSaveFile>
#include <QTemporaryDir>

#include "SafeZipReader.hpp"

#include <algorithm>
#include <limits>

namespace {
constexpr qint64 MaxArchiveBytes = 64LL * 1024 * 1024;
constexpr qint64 MaxExtractedBytes = 128LL * 1024 * 1024;
constexpr qint64 MaxEntryBytes = 64LL * 1024 * 1024;
constexpr int MaxArchiveEntries = 256;

Qt::CaseSensitivity pathCaseSensitivity()
{
#ifdef Q_OS_WIN
    return Qt::CaseInsensitive;
#else
    return Qt::CaseSensitive;
#endif
}

bool isPathInside(const QString &rootPath, const QString &candidatePath)
{
    const auto root = QDir::cleanPath(QDir::fromNativeSeparators(rootPath));
    const auto candidate = QDir::cleanPath(QDir::fromNativeSeparators(candidatePath));
    return candidate.startsWith(root + u'/', pathCaseSensitivity());
}

bool isSafeArchiveSegment(const QString &segment)
{
    static const QRegularExpression SegmentPattern(QStringLiteral(R"(^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$)"));
    static const QRegularExpression ReservedWindowsName(
        QStringLiteral(R"(^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$)"),
        QRegularExpression::CaseInsensitiveOption);
    return SegmentPattern.match(segment).hasMatch()
        && !ReservedWindowsName.match(segment).hasMatch()
        && !segment.endsWith(u'.') && !segment.endsWith(u' ');
}

bool normalizeArchivePath(const QString &archivePath, bool directory, QString *normalized,
                          QString *error)
{
    QString path = archivePath;
    if (directory && path.endsWith(u'/')) {
        path.chop(1);
    }
    if (path.isEmpty() || path.size() > 512 || path.startsWith(u'/') || path.startsWith(u'\\')
        || path.contains(u'\\') || path.contains(u':') || path.contains(QChar::ReplacementCharacter)) {
        if (error != nullptr) {
            *error = QStringLiteral("The ZIP contains an absolute, malformed, or unsupported path.");
        }
        return false;
    }
    for (const auto character : path) {
        if (character.unicode() < 0x20 || character.unicode() == 0x7f) {
            if (error != nullptr) {
                *error = QStringLiteral("The ZIP contains a control character in an entry path.");
            }
            return false;
        }
    }
    const auto segments = path.split(u'/', Qt::KeepEmptyParts);
    if (segments.isEmpty() || segments.size() > 32) {
        if (error != nullptr) {
            *error = QStringLiteral("The ZIP entry path is empty or too deeply nested.");
        }
        return false;
    }
    for (const auto &segment : segments) {
        if (!isSafeArchiveSegment(segment)) {
            if (error != nullptr) {
                *error = QStringLiteral("ZIP entry names may use only portable letters, digits, '.', '_', '+' and '-'.");
            }
            return false;
        }
    }
    if (QDir::cleanPath(path) != path) {
        if (error != nullptr) {
            *error = QStringLiteral("The ZIP contains a path traversal or ambiguous entry.");
        }
        return false;
    }
    if (normalized != nullptr) {
        *normalized = path;
    }
    return true;
}

quint32 crc32(const QByteArray &data)
{
    quint32 crc = std::numeric_limits<quint32>::max();
    for (const auto byte : data) {
        crc ^= static_cast<quint8>(byte);
        for (int bit = 0; bit < 8; ++bit) {
            const quint32 mask = 0U - (crc & 1U);
            crc = (crc >> 1U) ^ (0xedb88320U & mask);
        }
    }
    return ~crc;
}

QList<QFileInfo> pluginManifests(const QString &directory)
{
    QList<QFileInfo> manifests;
    const QDir root(directory);
    manifests.append(root.entryInfoList({QStringLiteral("*.forgeplugin.json")},
                                        QDir::Files | QDir::Readable | QDir::NoSymLinks,
                                        QDir::Name));
    const auto packages = root.entryInfoList(QDir::Dirs | QDir::Readable | QDir::NoDotAndDotDot
                                                 | QDir::NoSymLinks,
                                             QDir::Name);
    for (const auto &package : packages) {
        const QDir packageDirectory(package.absoluteFilePath());
        manifests.append(packageDirectory.entryInfoList(
            {QStringLiteral("*.forgeplugin.json")},
            QDir::Files | QDir::Readable | QDir::NoSymLinks, QDir::Name));
    }
    return manifests;
}

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
    descriptor.sha256 = object.value(QStringLiteral("sha256")).toString().toLower();
    const auto permissionValues = object.value(QStringLiteral("permissions"));
    static const QRegularExpression IdPattern(QStringLiteral(R"(^[a-z0-9]+(?:[.-][a-z0-9]+)*$)"));
    static const QRegularExpression VersionPattern(
        QStringLiteral(R"(^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$)"));
    static const QRegularExpression DigestPattern(QStringLiteral(R"(^[a-f0-9]{64}$)"));
    if (descriptor.id.size() > 128 || !IdPattern.match(descriptor.id).hasMatch()
        || descriptor.name.trimmed().isEmpty() || descriptor.name.size() > 128
        || !std::all_of(descriptor.name.cbegin(), descriptor.name.cend(), [](QChar c) { return c.isPrint(); })
        || descriptor.version.size() > 64 || !VersionPattern.match(descriptor.version).hasMatch() || !isSafeArchiveSegment(libraryName)
        || !DigestPattern.match(descriptor.sha256).hasMatch()) {
        descriptor.error = QStringLiteral("Manifest requires a safe id, semantic version, name, library filename and lowercase SHA-256 digest.");
        return descriptor;
    }
    if (!permissionValues.isUndefined()) {
        if (!permissionValues.isArray() || permissionValues.toArray().size() > 32) {
            descriptor.error = QStringLiteral("Plugin permissions must be an array with at most 32 entries.");
            return descriptor;
        }
        for (const auto &permission : permissionValues.toArray()) {
            if (!permission.isString() || permission.toString().size() > 128 || !IdPattern.match(permission.toString()).hasMatch()) {
                descriptor.error = QStringLiteral("Plugin permission names must use the safe dotted identifier format.");
                return descriptor;
            }
            descriptor.permissions.append(permission.toString());
        }
        descriptor.permissions.removeDuplicates();
    }
    const QDir root(manifest.absolutePath());
    const QFileInfo library(root.absoluteFilePath(libraryName));
    const auto canonicalRoot = QFileInfo(root.absolutePath()).canonicalFilePath();
    const auto canonicalLibrary = library.canonicalFilePath();
    if (canonicalRoot.isEmpty() || canonicalLibrary.isEmpty() || !library.isFile() || library.isSymLink()
        || !isPathInside(canonicalRoot, canonicalLibrary)
        || !QLibrary::isLibrary(canonicalLibrary)) {
        descriptor.error = QStringLiteral("Plugin library must be a regular native library inside its manifest directory.");
        return descriptor;
    }
    descriptor.libraryPath = canonicalLibrary;
    QFile libraryFile(canonicalLibrary);
    if (!libraryFile.open(QIODevice::ReadOnly)) {
        descriptor.error = QStringLiteral("Plugin library cannot be opened for digest verification.");
        return descriptor;
    }
    QCryptographicHash digest(QCryptographicHash::Sha256);
    while (!libraryFile.atEnd()) {
        const auto chunk = libraryFile.read(1024 * 1024);
        if (chunk.isEmpty() && libraryFile.error() != QFile::NoError) {
            descriptor.error = QStringLiteral("Plugin library could not be read for digest verification.");
            return descriptor;
        }
        digest.addData(chunk);
    }
    if (QString::fromLatin1(digest.result().toHex()) != descriptor.sha256) {
        descriptor.error = QStringLiteral("Plugin library SHA-256 does not match its reviewed manifest.");
        return descriptor;
    }
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
        for (const auto &manifest : pluginManifests(directory)) {
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

PluginImportResult PluginManager::importZip(const QString &archivePath,
                                             const QString &destinationDirectory)
{
    PluginImportResult result;
    const QFileInfo archive(archivePath);
    if (!archive.exists() || !archive.isFile() || archive.isSymLink() || archive.size() <= 0
        || archive.size() > MaxArchiveBytes) {
        result.error = QStringLiteral("Choose a regular ZIP file no larger than 64 MiB.");
        return result;
    }

    SafeZipReader reader(archive.absoluteFilePath());
    if (!reader.exists() || !reader.isReadable() || reader.status() != SafeZipReader::NoError
        || reader.count() <= 0 || reader.count() > MaxArchiveEntries) {
        result.error = reader.errorString().isEmpty()
            ? QStringLiteral("The plugin ZIP is unreadable, empty, or contains too many entries.")
            : reader.errorString();
        return result;
    }

    struct ArchiveEntry {
        SafeZipReader::FileInfo info;
        QString path;
        QString relativePath;
    };
    QList<ArchiveEntry> entries;
    QSet<QString> caseFoldedPaths;
    QHash<QString, bool> entryKinds;
    QSet<QString> requiredDirectories;
    QStringList manifestPaths;
    qint64 totalBytes = 0;
    for (const auto &info : reader.fileInfoList()) {
        if (!info.isValid() || info.isSymLink || (!info.isFile && !info.isDir)) {
            result.error = QStringLiteral("Symbolic links and unsupported ZIP entry types are not accepted.");
            return result;
        }
        QString normalized;
        if (!normalizeArchivePath(info.filePath, info.isDir, &normalized, &result.error)) {
            return result;
        }
        const auto folded = normalized.toCaseFolded();
        if (caseFoldedPaths.contains(folded)) {
            result.error = QStringLiteral("The ZIP contains duplicate or case-colliding paths.");
            return result;
        }
        caseFoldedPaths.insert(folded);
        if (info.isFile && requiredDirectories.contains(folded)) {
            result.error = QStringLiteral("A ZIP path is both a file and a parent directory.");
            return result;
        }
        const auto segments = normalized.split(u'/');
        QString prefix;
        for (qsizetype index = 0; index + 1 < segments.size(); ++index) {
            prefix = prefix.isEmpty() ? segments.at(index) : prefix + u'/' + segments.at(index);
            requiredDirectories.insert(prefix.toCaseFolded());
            const auto existing = entryKinds.constFind(prefix.toCaseFolded());
            if (existing != entryKinds.cend() && !existing.value()) {
                result.error = QStringLiteral("A ZIP path is both a file and a parent directory.");
                return result;
            }
        }
        entryKinds.insert(folded, info.isDir);
        if (info.isFile) {
            if (info.size < 0 || info.size > MaxEntryBytes
                || totalBytes > MaxExtractedBytes - info.size) {
                result.error = QStringLiteral("The ZIP exceeds the per-file or 128 MiB extracted-size limit.");
                return result;
            }
            totalBytes += info.size;
            if (normalized.endsWith(QStringLiteral(".forgeplugin.json"))) {
                manifestPaths.append(normalized);
                if (info.size > 128 * 1024) {
                    result.error = QStringLiteral("The plugin manifest exceeds 128 KiB.");
                    return result;
                }
            }
        }
        entries.append({info, normalized, {}});
    }
    if (totalBytes > archive.size() * 100 + 1024 * 1024) {
        result.error = QStringLiteral("The ZIP compression ratio exceeds the safe import limit.");
        return result;
    }
    if (manifestPaths.size() != 1) {
        result.error = QStringLiteral("A plugin ZIP must contain exactly one .forgeplugin.json manifest.");
        return result;
    }

    const auto manifestSegments = manifestPaths.first().split(u'/');
    if (manifestSegments.size() > 2) {
        result.error = QStringLiteral("The manifest must be at the ZIP root or inside one package directory.");
        return result;
    }
    const auto packagePrefix = manifestSegments.size() == 2 ? manifestSegments.first() : QString();
    QString relativeManifest;
    QSet<QString> relativeFiles;
    for (auto &entry : entries) {
        if (!packagePrefix.isEmpty()) {
            if (entry.path == packagePrefix && entry.info.isDir) {
                entry.relativePath.clear();
                continue;
            }
            const auto requiredPrefix = packagePrefix + u'/';
            if (!entry.path.startsWith(requiredPrefix)) {
                result.error = QStringLiteral("Every ZIP entry must belong to the single plugin package directory.");
                return result;
            }
            entry.relativePath = entry.path.mid(requiredPrefix.size());
        } else {
            entry.relativePath = entry.path;
        }
        if (entry.info.isFile) {
            relativeFiles.insert(entry.relativePath);
        }
        if (entry.path == manifestPaths.first()) {
            relativeManifest = entry.relativePath;
        }
    }

    const auto manifestEntry = std::find_if(entries.cbegin(), entries.cend(),
                                            [&relativeManifest](const ArchiveEntry &entry) {
                                                return entry.relativePath == relativeManifest;
                                            });
    if (manifestEntry == entries.cend()) {
        result.error = QStringLiteral("The ZIP manifest entry could not be resolved.");
        return result;
    }
    const auto manifestData = reader.fileData(manifestEntry->info.filePath);
    if (reader.status() != SafeZipReader::NoError || manifestData.size() != manifestEntry->info.size
        || crc32(manifestData) != static_cast<quint32>(manifestEntry->info.crc)) {
        result.error = QStringLiteral("The plugin manifest failed ZIP size or CRC verification.");
        return result;
    }
    QJsonParseError parseError;
    const auto manifestDocument = QJsonDocument::fromJson(manifestData, &parseError);
    if (parseError.error != QJsonParseError::NoError || !manifestDocument.isObject()) {
        result.error = QStringLiteral("The plugin manifest is not a valid JSON object.");
        return result;
    }
    const auto manifestObject = manifestDocument.object();
    result.pluginId = manifestObject.value(QStringLiteral("id")).toString();
    result.pluginName = manifestObject.value(QStringLiteral("name")).toString(result.pluginId);
    result.version = manifestObject.value(QStringLiteral("version")).toString();
    const auto libraryName = manifestObject.value(QStringLiteral("library")).toString();
    static const QRegularExpression IdPattern(QStringLiteral(R"(^[a-z0-9]+(?:[.-][a-z0-9]+)*$)"));
    static const QRegularExpression VersionPattern(
        QStringLiteral(R"(^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$)"));
    if (result.pluginId.size() > 128 || !IdPattern.match(result.pluginId).hasMatch() || result.pluginName.trimmed().isEmpty()
        || result.pluginName.size() > 128
        || !std::all_of(result.pluginName.cbegin(), result.pluginName.cend(), [](QChar c) { return c.isPrint(); })
        || result.version.size() > 64 || !VersionPattern.match(result.version).hasMatch()
        || !isSafeArchiveSegment(libraryName) || !relativeFiles.contains(libraryName)) {
        result.error = QStringLiteral("The ZIP manifest identity, version, name, or library entry is invalid.");
        return result;
    }

    if (!QDir().mkpath(destinationDirectory)) {
        result.error = QStringLiteral("The Editor could not create its user plugin directory.");
        return result;
    }
    const QFileInfo destinationInfo(destinationDirectory);
    const auto canonicalDestination = destinationInfo.canonicalFilePath();
    if (destinationInfo.isSymLink() || canonicalDestination.isEmpty()) {
        result.error = QStringLiteral("The user plugin directory must be a real local directory.");
        return result;
    }
    for (const auto &existing : PluginManager({canonicalDestination}).discover()) {
        if (existing.id == result.pluginId) {
            result.error = QStringLiteral("A plugin with this id is already installed. Remove it before importing another version.");
            return result;
        }
    }
    const auto installFolder = result.pluginId + u'-' + result.version;
    const auto finalPath = QDir(canonicalDestination).absoluteFilePath(installFolder);
    if (QFileInfo::exists(finalPath)) {
        result.error = QStringLiteral("The target plugin version directory already exists.");
        return result;
    }

    QTemporaryDir staging(QDir(canonicalDestination).filePath(QStringLiteral(".forge-plugin-import-XXXXXX")));
    if (!staging.isValid()) {
        result.error = QStringLiteral("The Editor could not create a private plugin staging directory.");
        return result;
    }
    for (const auto &entry : entries) {
        if (entry.relativePath.isEmpty()) {
            continue;
        }
        const auto targetPath = QDir(staging.path()).absoluteFilePath(entry.relativePath);
        if (!isPathInside(staging.path(), targetPath)) {
            result.error = QStringLiteral("A plugin entry escaped the staging directory.");
            return result;
        }
        if (entry.info.isDir) {
            if (!QDir().mkpath(targetPath)) {
                result.error = QStringLiteral("The Editor could not create a staged plugin directory.");
                return result;
            }
            continue;
        }
        const auto parentPath = QFileInfo(targetPath).absolutePath();
        if (!QDir().mkpath(parentPath)) {
            result.error = QStringLiteral("The Editor could not create a staged plugin path.");
            return result;
        }
        const auto data = reader.fileData(entry.info.filePath);
        if (reader.status() != SafeZipReader::NoError || data.size() != entry.info.size || crc32(data) != static_cast<quint32>(entry.info.crc)) {
            result.error = QStringLiteral("A plugin file failed ZIP size or CRC verification.");
            return result;
        }
        QSaveFile output(targetPath);
        output.setDirectWriteFallback(false);
        if (!output.open(QIODevice::WriteOnly) || output.write(data) != data.size()
            || !output.commit()) {
            result.error = QStringLiteral("A verified plugin file could not be staged atomically.");
            return result;
        }
        QFile::setPermissions(targetPath, QFileDevice::ReadOwner | QFileDevice::WriteOwner
                                              | QFileDevice::ReadGroup | QFileDevice::ReadOther);
    }

    const auto stagedDescriptor = readManifest(QFileInfo(QDir(staging.path()).filePath(relativeManifest)));
    if (!stagedDescriptor.error.isEmpty() || stagedDescriptor.id != result.pluginId
        || stagedDescriptor.version != result.version) {
        result.error = stagedDescriptor.error.isEmpty()
            ? QStringLiteral("The staged plugin identity changed during verification.")
            : stagedDescriptor.error;
        return result;
    }
    QDir destination(canonicalDestination);
    if (!destination.rename(QFileInfo(staging.path()).fileName(), installFolder)) {
        result.error = QStringLiteral("The verified plugin could not be moved into the install directory.");
        return result;
    }
    result.success = true;
    result.installDirectory = finalPath;
    return result;
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
