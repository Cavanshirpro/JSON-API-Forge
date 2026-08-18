#include "ApiClient.hpp"
#include "DocumentCodec.hpp"
#include "PluginManager.hpp"

#include <QDir>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QTemporaryDir>
#include <QTest>

class EditorCoreTests final : public QObject {
    Q_OBJECT

private slots:
    void jsonObjectsOnly();
    void documentPathPolicy();
    void atomicSaveAndDigest();
    void serverUrlPolicy();
    void tokenPolicy();
    void pluginManifestPathPolicy();
};

void EditorCoreTests::jsonObjectsOnly()
{
    QJsonObject object;
    QString error;
    QVERIFY(DocumentCodec::parseObject(QByteArray(R"({"name":"Forge","enabled":true})"), &object, &error));
    QCOMPARE(object.value(QStringLiteral("name")).toString(), QStringLiteral("Forge"));
    QVERIFY(!DocumentCodec::parseObject(QByteArray(R"([1,2,3])"), &object, &error));
    QVERIFY(error.contains(QStringLiteral("root")));
    QVERIFY(!DocumentCodec::parseObject(QByteArray("{"), &object, &error));
}

void EditorCoreTests::documentPathPolicy()
{
    QVERIFY(DocumentCodec::isSafeDocumentPath(QStringLiteral("app.json"), false));
    QVERIFY(DocumentCodec::isSafeDocumentPath(QStringLiteral("config/40-resources.json"), false));
    QVERIFY(!DocumentCodec::isSafeDocumentPath(QStringLiteral("hooks/business.py"), false));
    QVERIFY(DocumentCodec::isSafeDocumentPath(QStringLiteral("hooks/business.py"), true));
    QVERIFY(!DocumentCodec::isSafeDocumentPath(QStringLiteral("../.env"), true));
    QVERIFY(!DocumentCodec::isSafeDocumentPath(QStringLiteral("config/nested/value.json"), true));
    QVERIFY(!DocumentCodec::isSafeDocumentPath(QStringLiteral("config\\value.json"), true));
}

void EditorCoreTests::atomicSaveAndDigest()
{
    QTemporaryDir directory;
    QVERIFY(directory.isValid());
    const auto path = directory.filePath(QStringLiteral("document.json"));
    const QByteArray content(R"({"resources":[]})");
    QString error;
    QVERIFY2(DocumentCodec::saveAtomically(path, content, &error), qPrintable(error));
    QFile file(path);
    QVERIFY(file.open(QIODevice::ReadOnly));
    QCOMPARE(file.readAll(), content);
    QCOMPARE(DocumentCodec::sha256(content).size(), 64);
}

void EditorCoreTests::serverUrlPolicy()
{
    QUrl normalized;
    QString error;
    QVERIFY(ApiClient::normalizeServerUrl(QUrl(QStringLiteral("https://forge.example.com/base/")), false, &normalized, &error));
    QCOMPARE(normalized.toString(), QStringLiteral("https://forge.example.com/base"));
    QVERIFY(!ApiClient::normalizeServerUrl(QUrl(QStringLiteral("http://forge.example.com")), false, &normalized, &error));
    QVERIFY(!ApiClient::normalizeServerUrl(QUrl(QStringLiteral("http://forge.example.com")), true, &normalized, &error));
    QVERIFY(ApiClient::normalizeServerUrl(QUrl(QStringLiteral("http://127.0.0.1:8000")), true, &normalized, &error));
    QVERIFY(ApiClient::normalizeServerUrl(QUrl(QStringLiteral("http://[::1]:8000")), true, &normalized, &error));
    QVERIFY(!ApiClient::normalizeServerUrl(QUrl(QStringLiteral("https://user:secret@forge.example.com")), false, &normalized, &error));
    QVERIFY(!ApiClient::normalizeServerUrl(QUrl(QStringLiteral("https://forge.example.com?token=x")), false, &normalized, &error));
    QVERIFY(!ApiClient::normalizeServerUrl(QUrl(QStringLiteral("https://forge.example.com/base/../admin")), false, &normalized, &error));
}

void EditorCoreTests::tokenPolicy()
{
    ApiClient client;
    QString error;
    QVERIFY(!client.configure(QUrl(QStringLiteral("https://forge.example.com")), QByteArray("short"), false, &error));
    QVERIFY(client.configure(QUrl(QStringLiteral("https://forge.example.com")),
                             QByteArray("ForgeEditor_9M2vK7pQ4xR8sT6wY3nC5aH1dL0uB"), false, &error));
    QVERIFY(client.isConfigured());
    client.clearCredentials();
    QVERIFY(!client.isConfigured());
}

void EditorCoreTests::pluginManifestPathPolicy()
{
    QTemporaryDir directory;
    QVERIFY(directory.isValid());
    QDir root(directory.path());
    QVERIFY(root.mkpath(QStringLiteral("plugins")));
    QFile outsideLibrary(root.filePath(QStringLiteral("escape.so")));
    QVERIFY(outsideLibrary.open(QIODevice::WriteOnly));
    QVERIFY(outsideLibrary.write("not a plugin") > 0);
    outsideLibrary.close();

    QFile manifest(root.filePath(QStringLiteral("plugins/escape.forgeplugin.json")));
    QVERIFY(manifest.open(QIODevice::WriteOnly));
    const QJsonObject definition{
        {QStringLiteral("id"), QStringLiteral("vendor.escape")},
        {QStringLiteral("name"), QStringLiteral("Escape attempt")},
        {QStringLiteral("version"), QStringLiteral("1.0.0")},
        {QStringLiteral("apiVersion"), ForgeEditor::PluginApiVersion},
        {QStringLiteral("library"), QStringLiteral("../escape.so")},
    };
    QVERIFY(manifest.write(QJsonDocument(definition).toJson(QJsonDocument::Compact)) > 0);
    manifest.close();

    const PluginManager manager({root.filePath(QStringLiteral("plugins"))});
    const auto descriptors = manager.discover();
    QCOMPARE(descriptors.size(), 1);
    QVERIFY(descriptors.first().error.contains(QStringLiteral("inside")));
}

QTEST_MAIN(EditorCoreTests)
#include "tst_editor_core.moc"
