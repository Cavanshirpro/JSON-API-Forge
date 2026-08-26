#include "ApiClient.hpp"
#include "DocumentCodec.hpp"
#include "GraphModel.hpp"
#include "PluginManager.hpp"
#include "PluginCatalogClient.hpp"
#include "PythonSdkPanel.hpp"
#include "TemplateManager.hpp"

#include <QCoreApplication>
#include <QDir>
#include <QElapsedTimer>
#include <QEventLoop>
#include <QFile>
#include <QHostAddress>
#include <QImage>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSharedPointer>
#include <QSignalSpy>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTemporaryDir>
#include <QTest>
#include <QUrlQuery>

#include <functional>

class EditorCoreTests final : public QObject {
    Q_OBJECT

private slots:
    void jsonObjectsOnly();
    void documentPathPolicy();
    void atomicSaveAndDigest();
    void serverUrlPolicy();
    void tokenPolicy();
    void accountSessionTransportPolicy();
    void callTicketUrlPolicy();
    void attachmentSnapshotPolicy();
    void brandAssetAndTheme();
    void pluginManifestPathPolicy();
    void graphModelPolicyAndCompiler();
    void graphCycleRollback();
    void graphCompilerRejectsDesignOnlyNodes();
    void pythonSdkSnippetPolicy();
    void forgePluginCatalogPolicy();
    void embeddedProjectTemplates();
};

namespace {
bool waitUntil(const std::function<bool()> &condition, int timeoutMs = 5000)
{
    QElapsedTimer timer;
    timer.start();
    while (!condition() && timer.elapsed() < timeoutMs) {
        QCoreApplication::processEvents(QEventLoop::AllEvents, 20);
        QTest::qWait(10);
    }
    return condition();
}

class LocalJsonServer final : public QTcpServer {
public:
    struct Response {
        QByteArray status;
        QByteArray body;
        QList<QPair<QByteArray, QByteArray>> headers;
    };

    explicit LocalJsonServer(QObject *parent = nullptr)
        : QTcpServer(parent)
    {
        connect(this, &QTcpServer::newConnection, this, [this] {
            while (hasPendingConnections()) {
                auto *socket = nextPendingConnection();
                const auto bytes = QSharedPointer<QByteArray>::create();
                connect(socket, &QTcpSocket::readyRead, this, [this, socket, bytes] {
                    bytes->append(socket->readAll());
                    const auto headerEnd = bytes->indexOf("\r\n\r\n");
                    if (headerEnd < 0) {
                        return;
                    }
                    qint64 contentLength = 0;
                    for (const auto &line : bytes->left(headerEnd).split('\n')) {
                        const auto normalized = line.trimmed();
                        if (normalized.toLower().startsWith("content-length:")) {
                            contentLength = normalized.mid(15).trimmed().toLongLong();
                        }
                    }
                    const auto total = static_cast<qint64>(headerEnd) + 4 + contentLength;
                    if (bytes->size() < total) {
                        return;
                    }
                    requests.append(bytes->left(total));
                    const auto response = responses.isEmpty()
                        ? Response{QByteArray("500 Internal Server Error"), QByteArray("{}"), {}}
                        : responses.takeFirst();
                    QByteArray output = QByteArray("HTTP/1.1 ") + response.status + QByteArray("\r\n")
                        + QByteArray("Content-Type: application/json\r\nConnection: close\r\nContent-Length: ")
                        + QByteArray::number(response.body.size()) + QByteArray("\r\n");
                    for (const auto &[name, value] : response.headers) {
                        output += name + QByteArray(": ") + value + QByteArray("\r\n");
                    }
                    output += QByteArray("\r\n") + response.body;
                    socket->write(output);
                    socket->disconnectFromHost();
                });
            }
        });
    }

    void enqueue(const QByteArray &status, const QByteArray &body,
                 const QList<QPair<QByteArray, QByteArray>> &headers = {})
    {
        responses.append(Response{status, body, headers});
    }

    QList<QByteArray> requests;
    QList<Response> responses;
};
} // namespace

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
    QVERIFY(DocumentCodec::isSafeDocumentPath(QStringLiteral("graphs/order-flow.forgegraph.json"), true));
    QVERIFY(!DocumentCodec::isSafeDocumentPath(QStringLiteral("graphs/OrderFlow.forgegraph.json"), true));
    QVERIFY(!DocumentCodec::isSafeDocumentPath(QStringLiteral("graphs/nested/order.forgegraph.json"), true));
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
                             QByteArray("jfe_session_9M2vK7pQ4xR8sT6wY3nC5aH1dL0uB7eF9qA2sD4gH6jK8mN"), false,
                             &error));
    QVERIFY(client.isConfigured());
    client.clearCredentials();
    QVERIFY(!client.isConfigured());
    QVERIFY(!client.configure(QUrl(QStringLiteral("https://forge.example.com")),
                              QByteArray("jfe_session_9M2vK7pQ4xR8sT6wY3nC5aH1dL0uB7eF9qA2sD4gH6jK8mN\n"),
                              false, &error));
    QVERIFY(client.configureServer(QUrl(QStringLiteral("https://forge.example.com")), false, &error));
    QSignalSpy failed(&client, &ApiClient::requestFailed);
    client.registerMember(QStringLiteral("jfi_") + QString(40, u'a') + u'\n',
                          QStringLiteral("worker.one"), QStringLiteral("a secure password"),
                          QStringLiteral("Worker One"));
    QCOMPARE(failed.size(), 1);
    client.setupFounder(QByteArray(32, 'a') + '\n', QStringLiteral("founder"),
                        QStringLiteral("a secure password"), QStringLiteral("Founder"));
    QCOMPARE(failed.size(), 2);
}

void EditorCoreTests::accountSessionTransportPolicy()
{
    LocalJsonServer server;
    QVERIFY(server.listen(QHostAddress::LocalHost));
    const QByteArray token("jfe_session_9M2vK7pQ4xR8sT6wY3nC5aH1dL0uB7eF9qA2sD4gH6jK8mN");
    server.enqueue(QByteArray("200 OK"),
                   QJsonDocument(QJsonObject{{QStringLiteral("access_token"), QString::fromUtf8(token)}})
                       .toJson(QJsonDocument::Compact),
                   {{QByteArray("Set-Cookie"), QByteArray("ambient=must-not-return; Path=/")}});
    server.enqueue(QByteArray("200 OK"),
                   QByteArray(R"({"username":"worker","display_name":"Worker"})"));
    server.enqueue(QByteArray("302 Found"), QByteArray("{}"),
                   {{QByteArray("Location"), QByteArray("http://127.0.0.1/credential-sink")}});
    server.enqueue(QByteArray("401 Unauthorized"), QByteArray(R"({"detail":"expired"})"));

    ApiClient client;
    QString error;
    const auto endpoint = QUrl(QStringLiteral("http://127.0.0.1:%1").arg(server.serverPort()));
    QVERIFY2(client.configureServer(endpoint, true, &error), qPrintable(error));
    QSignalSpy received(&client, &ApiClient::jsonReceived);
    QSignalSpy failed(&client, &ApiClient::requestFailed);

    client.login(QStringLiteral("worker"), QStringLiteral("correct horse battery staple"));
    QVERIFY(waitUntil([&received] { return received.size() == 1; }));
    QVERIFY(client.isConfigured());
    client.fetchProfile();
    QVERIFY(waitUntil([&received] { return received.size() == 2; }));
    QCOMPARE(server.requests.size(), 2);
    const auto loginRequest = server.requests.at(0).toLower();
    const auto profileRequest = server.requests.at(1).toLower();
    QVERIFY(loginRequest.startsWith("post /__forge/editor/v1/auth/login http/1.1\r\n"));
    QVERIFY(!loginRequest.contains("authorization:"));
    QVERIFY(!loginRequest.contains("x-forge-editor-token:"));
    QVERIFY(loginRequest.contains("cache-control: no-store"));
    QVERIFY(profileRequest.startsWith("get /__forge/editor/v1/me http/1.1\r\n"));
    QVERIFY(profileRequest.contains(QByteArray("authorization: bearer ") + token.toLower()));
    QVERIFY(!profileRequest.contains("x-forge-editor-token:"));
    QVERIFY(!profileRequest.contains("cookie:"));

    client.fetchMembers();
    QVERIFY(waitUntil([&failed] { return failed.size() == 1; }));
    QCOMPARE(server.requests.size(), 3);
    QVERIFY(failed.at(0).at(2).toString().contains(QStringLiteral("Redirects")));
    QVERIFY(client.isConfigured());

    client.fetchMembers();
    QVERIFY(waitUntil([&failed] { return failed.size() == 2; }));
    QCOMPARE(server.requests.size(), 4);
    QVERIFY(!client.isConfigured());
}

void EditorCoreTests::callTicketUrlPolicy()
{
    ApiClient client;
    QString error;
    QVERIFY(client.configure(QUrl(QStringLiteral("https://forge.example.com/admin")),
                             QByteArray("jfe_session_9M2vK7pQ4xR8sT6wY3nC5aH1dL0uB7eF9qA2sD4gH6jK8mN"), false,
                             &error));
    const auto ticket = QStringLiteral("jfc_9M2vK7pQ4xR8sT6wY3nC5aH1dL0uB7eF9qA2sD4gH6jK");
    const auto url = client.callClientUrl(QStringLiteral("/__forge/editor/v1/call-client/call-id"), ticket);
    QCOMPARE(url.host(), QStringLiteral("forge.example.com"));
    QCOMPARE(url.path(), QStringLiteral("/admin/__forge/editor/v1/call-client/call-id"));
    QVERIFY(url.query().isEmpty());
    QCOMPARE(QUrlQuery(url.fragment()).queryItemValue(QStringLiteral("ticket")),
             ticket);
    QVERIFY(!client.callClientUrl(QStringLiteral("/../redirect"), QStringLiteral("ticket")).isValid());
    QVERIFY(!client.callClientUrl(QStringLiteral("/__forge/editor/v1/call-client/../redirect"), ticket).isValid());
    QVERIFY(!client.callClientUrl(QStringLiteral("/__forge/editor/v1/call-client/call-id"), ticket + u'\n').isValid());
}

void EditorCoreTests::attachmentSnapshotPolicy()
{
    QTemporaryDir directory;
    QVERIFY(directory.isValid());
    ApiClient client;
    QString error;
    QVERIFY(client.configure(QUrl(QStringLiteral("https://forge.example.com")),
                             QByteArray("jfe_session_9M2vK7pQ4xR8sT6wY3nC5aH1dL0uB7eF9qA2sD4gH6jK8mN"), false,
                             &error));
    QSignalSpy failed(&client, &ApiClient::requestFailed);

    client.uploadAttachment(QStringLiteral("area-1"), directory.path(), 1024);
    QCOMPARE(failed.size(), 1);

    const auto oversizedPath = directory.filePath(QStringLiteral("oversized.bin"));
    QFile oversized(oversizedPath);
    QVERIFY(oversized.open(QIODevice::WriteOnly));
    QCOMPARE(oversized.write(QByteArray(1025, 'x')), static_cast<qint64>(1025));
    oversized.close();
    client.uploadAttachment(QStringLiteral("area-1"), oversizedPath, 1024);
    QCOMPARE(failed.size(), 2);

    const auto linkPath = directory.filePath(QStringLiteral("attachment-link.bin"));
    if (QFile::link(oversizedPath, linkPath) && QFileInfo(linkPath).isSymLink()) {
        client.uploadAttachment(QStringLiteral("area-1"), linkPath, 4096);
        QCOMPARE(failed.size(), 3);
    }
}

void EditorCoreTests::brandAssetAndTheme()
{
    const QImage mark(QStringLiteral(":/branding/mark.png"));
    QVERIFY(!mark.isNull());
    QVERIFY(mark.hasAlphaChannel());
    QFile style(QStringLiteral(":/styles/dark.qss"));
    QVERIFY(style.open(QIODevice::ReadOnly));
    const auto qss = style.readAll();
    QVERIFY(qss.contains("#f2b84b"));
    QVERIFY(qss.contains("#202225"));
    QVERIFY(!qss.contains("#0c1016"));
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
        {QStringLiteral("sha256"), QString(64, u'0')},
    };
    QVERIFY(manifest.write(QJsonDocument(definition).toJson(QJsonDocument::Compact)) > 0);
    manifest.close();

    const PluginManager manager({root.filePath(QStringLiteral("plugins"))});
    const auto descriptors = manager.discover();
    QCOMPARE(descriptors.size(), 1);
    QVERIFY(descriptors.first().error.contains(QStringLiteral("inside")));
}

void EditorCoreTests::graphModelPolicyAndCompiler()
{
    GraphModel graph;
    const auto request = graph.addNode(QStringLiteral("request.input"), QStringLiteral("Request"), QPointF(0, 0),
                                       QJsonObject{{QStringLiteral("method"), QStringLiteral("POST")}});
    const auto policy = graph.addNode(QStringLiteral("auth.policy"), QStringLiteral("Policy"), QPointF(280, 0),
                                      QJsonObject{{QStringLiteral("permission"), QStringLiteral("orders.create")}});
    const auto query = graph.addNode(QStringLiteral("data.query"), QStringLiteral("Query"), QPointF(560, 0),
                                     QJsonObject{{QStringLiteral("sql"), QStringLiteral("SELECT :id AS id")},
                                                 {QStringLiteral("mode"), QStringLiteral("fetch_one")},
                                                 {QStringLiteral("params"), QJsonObject{{QStringLiteral("id"), QStringLiteral("$body.id")}}}});
    const auto operation = graph.addNode(QStringLiteral("operation.call"), QStringLiteral("Operation"), QPointF(840, 0),
                                         QJsonObject{{QStringLiteral("name"), QStringLiteral("orders.lookup")},
                                                     {QStringLiteral("method"), QStringLiteral("POST")}});
    QVERIFY(!request.isEmpty());
    QVERIFY(!policy.isEmpty());
    QVERIFY(!query.isEmpty());
    QVERIFY(!operation.isEmpty());
    QString error;
    QVERIFY2(graph.connectNodes(request, QStringLiteral("exec"), policy, QStringLiteral("exec"), &error), qPrintable(error));
    QVERIFY2(graph.connectNodes(policy, QStringLiteral("exec"), query, QStringLiteral("exec"), &error), qPrintable(error));
    QVERIFY2(graph.connectNodes(query, QStringLiteral("exec"), operation, QStringLiteral("exec"), &error), qPrintable(error));
    QVERIFY2(graph.validate(&error), qPrintable(error));
    const auto compiled = graph.compiledFragment(&error);
    QVERIFY2(!compiled.isEmpty(), qPrintable(error));
    const auto compiledOperation = compiled.value(QStringLiteral("operations")).toArray().first().toObject();
    QCOMPARE(compiledOperation.value(QStringLiteral("name")).toString(), QStringLiteral("orders.lookup"));
    QCOMPARE(compiledOperation.value(QStringLiteral("permission")).toString(), QStringLiteral("orders.create"));
    QCOMPARE(compiledOperation.value(QStringLiteral("statements")).toArray().size(), 1);
}

void EditorCoreTests::graphCycleRollback()
{
    GraphModel graph;
    const auto first = graph.addNode(QStringLiteral("logic.branch"), QStringLiteral("First"), QPointF(0, 0));
    const auto second = graph.addNode(QStringLiteral("transform.map"), QStringLiteral("Second"), QPointF(280, 0));
    QString error;
    QVERIFY(graph.connectNodes(first, QStringLiteral("exec"), second, QStringLiteral("exec"), &error));
    QVERIFY(!graph.connectNodes(second, QStringLiteral("exec"), first, QStringLiteral("exec"), &error));
    QVERIFY(error.contains(QStringLiteral("acyclic")));
    QCOMPARE(graph.document().value(QStringLiteral("edges")).toArray().size(), 1);
}

void EditorCoreTests::graphCompilerRejectsDesignOnlyNodes()
{
    GraphModel graph;
    const auto branch = graph.addNode(QStringLiteral("logic.branch"), QStringLiteral("Guard"), QPointF(0, 0));
    const auto query = graph.addNode(QStringLiteral("data.query"), QStringLiteral("Query"), QPointF(280, 0),
                                     QJsonObject{{QStringLiteral("sql"), QStringLiteral("SELECT 1")}});
    const auto operation = graph.addNode(QStringLiteral("operation.call"), QStringLiteral("Operation"), QPointF(560, 0),
                                         QJsonObject{{QStringLiteral("name"), QStringLiteral("guarded.operation")}});
    QString error;
    QVERIFY(graph.connectNodes(branch, QStringLiteral("exec"), query, QStringLiteral("exec"), &error));
    QVERIFY(graph.connectNodes(query, QStringLiteral("exec"), operation, QStringLiteral("exec"), &error));
    QVERIFY(graph.compiledFragment(&error).isEmpty());
    QVERIFY(error.contains(QStringLiteral("design-only")));
    QVERIFY(error.contains(QStringLiteral("not silently omitted")));
}

void EditorCoreTests::pythonSdkSnippetPolicy()
{
    const PythonSdkSettings sync{QStringLiteral("sync"), QStringLiteral("https://forge.example.com"), QString(),
                                 QStringLiteral("enterprise"), QStringLiteral("records"), QStringLiteral("records.summary"),
                                 QStringLiteral("FORGE_API_KEY")};
    QString error;
    const auto code = PythonSdkPanel::generatedSnippet(sync, &error);
    QVERIFY2(!code.isEmpty(), qPrintable(error));
    QVERIFY(code.contains(QStringLiteral("RetryPolicy")));
    QVERIFY(code.contains(QStringLiteral("iter_items")));
    auto unsafe = sync;
    unsafe.endpoint = QStringLiteral("https://user:secret@forge.example.com");
    QVERIFY(PythonSdkPanel::generatedSnippet(unsafe, &error).isEmpty());
    auto cluster = sync;
    cluster.mode = QStringLiteral("cluster");
    cluster.clusterEndpoints = QStringLiteral("https://eu.example.com,https://us.example.com");
    const auto clusterCode = PythonSdkPanel::generatedSnippet(cluster, &error);
    QVERIFY2(clusterCode.contains(QStringLiteral("RoutingStrategy.RENDEZVOUS")), qPrintable(error));
}

void EditorCoreTests::forgePluginCatalogPolicy()
{
    QUrl endpoint;
    QString error;
    QVERIFY(PluginCatalogClient::catalogEndpoint(QUrl(QStringLiteral("https://forge.example.com")),
                                                  QStringLiteral("editor-plugin-registry"), QStringLiteral("editor/plugins"),
                                                  false, &endpoint, &error));
    QCOMPARE(endpoint.path(), QStringLiteral("/api/editor-plugin-registry/v1/editor/plugins"));
    QVERIFY(!PluginCatalogClient::catalogEndpoint(QUrl(QStringLiteral("https://forge.example.com")),
                                                   QStringLiteral("../admin"), QStringLiteral("editor/plugins"), false,
                                                   &endpoint, &error));
    const QJsonArray valid{QJsonObject{{QStringLiteral("plugin_id"), QStringLiteral("vendor.analytics")},
                                       {QStringLiteral("name"), QStringLiteral("Analytics")},
                                       {QStringLiteral("version"), QStringLiteral("1.2.0")},
                                       {QStringLiteral("sha256"), QString(64, u'a')},
                                       {QStringLiteral("download_url"), QStringLiteral("https://packages.example.com/analytics.zip")},
                                       {QStringLiteral("permissions"), QJsonArray{QStringLiteral("graph.nodes.register")}}}};
    QVERIFY2(PluginCatalogClient::validateCatalog(valid, &error), qPrintable(error));
    auto invalid = valid;
    auto item = invalid.first().toObject();
    item.insert(QStringLiteral("download_url"), QStringLiteral("http://packages.example.com/analytics.zip"));
    invalid.replace(0, item);
    QVERIFY(!PluginCatalogClient::validateCatalog(invalid, &error));
}

void EditorCoreTests::embeddedProjectTemplates()
{
    QString error;
    const auto definitions = TemplateManager::templates(&error);
    QVERIFY2(definitions.size() >= 8, qPrintable(error));
    QTemporaryDir workspace;
    QVERIFY(workspace.isValid());
    QVERIFY2(TemplateManager::createProject(definitions.first(), workspace.path(), QStringLiteral("TemplateProject"),
                                             QStringLiteral("template-project"), &error),
             qPrintable(error));
    const QDir project(workspace.filePath(QStringLiteral("TemplateProject")));
    QVERIFY(QFileInfo::exists(project.filePath(QStringLiteral("app.json"))));
    QVERIFY(QFileInfo::exists(project.filePath(QStringLiteral("config/40-resources.json"))));
    QFile graphFile(project.filePath(QStringLiteral("graphs/domain-flow.forgegraph.json")));
    QVERIFY(graphFile.open(QIODevice::ReadOnly));
    QJsonObject graphDocument;
    QVERIFY(DocumentCodec::parseObject(graphFile.readAll(), &graphDocument, &error));
    GraphModel graph;
    QVERIFY2(graph.setDocument(graphDocument, &error), qPrintable(error));
    QVERIFY(!graph.compiledFragment(&error).isEmpty());
    QVERIFY(!TemplateManager::createProject(definitions.first(), workspace.path(), QStringLiteral("TemplateProject"),
                                             QStringLiteral("template-project"), &error));
}

QTEST_MAIN(EditorCoreTests)
#include "tst_editor_core.moc"
