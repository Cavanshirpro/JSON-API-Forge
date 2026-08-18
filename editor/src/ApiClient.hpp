#pragma once

#include <QByteArray>
#include <QJsonObject>
#include <QNetworkAccessManager>
#include <QObject>
#include <QUrl>

class QNetworkReply;

class ApiClient final : public QObject {
    Q_OBJECT

public:
    explicit ApiClient(QObject *parent = nullptr);
    ~ApiClient() override;

    bool configure(const QUrl &serverUrl, const QByteArray &token, bool allowInsecureHttp, QString *errorMessage);
    void clearCredentials();
    [[nodiscard]] bool isConfigured() const;
    [[nodiscard]] QUrl serverUrl() const;

    void fetchCapabilities();
    void fetchProjects();
    void createProject(const QString &directoryName, const QString &slug);
    void fetchDocuments(const QString &project);
    void fetchDocument(const QString &project, const QString &documentPath);
    void saveDocument(const QString &project, const QString &documentPath, const QByteArray &content, const QString &expectedSha256);
    void validateProject(const QString &project);

    static bool normalizeServerUrl(const QUrl &input, bool allowInsecureHttp, QUrl *normalized, QString *errorMessage);

signals:
    void jsonReceived(const QString &operation, const QJsonObject &payload);
    void requestFailed(const QString &operation, int statusCode, const QString &message);
    void connectionActivityChanged(bool active);
    void tlsRejected(const QString &message);

private:
    void send(const QString &operation, QNetworkAccessManager::Operation method, const QStringList &pathSegments,
              const QJsonObject &body = {});
    [[nodiscard]] QUrl endpointFor(const QStringList &pathSegments) const;

    QNetworkAccessManager m_network;
    QUrl m_serverUrl;
    QByteArray m_token;
    qsizetype m_maxResponseBytes = 4 * 1024 * 1024;
    int m_activeRequests = 0;
};
