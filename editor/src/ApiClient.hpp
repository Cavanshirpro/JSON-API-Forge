#pragma once

#include <QByteArray>
#include <QJsonObject>
#include <QList>
#include <QNetworkAccessManager>
#include <QObject>
#include <QPair>
#include <QUrl>
#include <QUrlQuery>

class QNetworkReply;

class ApiClient final : public QObject {
    Q_OBJECT

public:
    explicit ApiClient(QObject *parent = nullptr);
    ~ApiClient() override;

    bool configureServer(const QUrl &serverUrl, bool allowInsecureHttp, QString *errorMessage);
    bool configure(const QUrl &serverUrl, const QByteArray &sessionToken, bool allowInsecureHttp,
                   QString *errorMessage);
    bool setSessionToken(const QByteArray &sessionToken, QString *errorMessage = nullptr);
    void clearCredentials();
    [[nodiscard]] bool hasServer() const;
    [[nodiscard]] bool isConfigured() const;
    [[nodiscard]] QUrl serverUrl() const;

    void login(const QString &username, const QString &password);
    void registerMember(const QString &invitation, const QString &username, const QString &password,
                        const QString &displayName);
    void setupFounder(const QByteArray &setupToken, const QString &username, const QString &password,
                      const QString &displayName);
    void logout();
    void fetchCapabilities();
    void fetchProfile();
    void updateProfile(const QJsonObject &values);
    void fetchProjects();
    void createProject(const QString &directoryName, const QString &slug);
    void fetchDocuments(const QString &project);
    void fetchDocument(const QString &project, const QString &documentPath);
    void saveDocument(const QString &project, const QString &documentPath, const QByteArray &content,
                      const QString &expectedSha256);
    void validateProject(const QString &project);

    void fetchMembers();
    void fetchRoles();
    void createRole(const QString &name, int rank, const QJsonArray &permissions,
                    const QJsonArray &documentAllow, const QJsonArray &documentDeny,
                    const QJsonArray &databaseAllow);
    void updateMember(const QString &userId, const QJsonArray &memberships, bool active);
    void createInvitation(const QString &roleId, const QString &project, int expiresHours);
    void fetchAreas(const QString &project);
    void createArea(const QString &project, const QString &name, const QString &description,
                    const QString &visibility, int minimumRank);
    void fetchMessages(const QString &areaId);
    void postMessage(const QString &areaId, const QString &body, bool announcement = false);
    void fetchAttachments(const QString &areaId);
    void uploadAttachment(const QString &areaId, const QString &filePath, qsizetype maxBytes);
    void downloadAttachment(const QString &attachmentId, const QString &targetPath, qsizetype maxBytes);
    void fetchNotes(const QString &project);
    void createNote(const QString &project, const QString &areaId, const QString &title, const QString &body,
                    const QString &visibility);
    void fetchDatabases(const QString &project);
    void fetchDatabaseRows(const QString &project, const QString &alias, const QString &table, int limit = 100,
                           int offset = 0);
    void startCall(const QString &areaId, const QString &mode);
    void createCallTicket(const QString &callId);
    void fetchAudit(const QString &project = {});
    [[nodiscard]] QUrl callClientUrl(const QString &path, const QString &ticket) const;

    static bool normalizeServerUrl(const QUrl &input, bool allowInsecureHttp, QUrl *normalized,
                                   QString *errorMessage);

signals:
    void jsonReceived(const QString &operation, const QJsonObject &payload);
    void requestFailed(const QString &operation, int statusCode, const QString &message);
    void connectionActivityChanged(bool active);
    void tlsRejected(const QString &message);
    void fileDownloaded(const QString &operation, const QString &path);

private:
    void send(const QString &operation, QNetworkAccessManager::Operation method, const QStringList &pathSegments,
              const QJsonObject &body = {}, const QUrlQuery &query = {}, bool authenticationRequired = true,
              const QList<QPair<QByteArray, QByteArray>> &extraHeaders = {});
    void trackJsonReply(QNetworkReply *reply, const QString &operation, bool authenticationRequired);
    [[nodiscard]] QUrl endpointFor(const QStringList &pathSegments, const QUrlQuery &query = {}) const;

    QNetworkAccessManager m_network;
    QUrl m_serverUrl;
    QByteArray m_sessionToken;
    qsizetype m_maxResponseBytes = 8 * 1024 * 1024;
    int m_activeRequests = 0;
};
