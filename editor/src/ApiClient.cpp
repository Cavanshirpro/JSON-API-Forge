#include "ApiClient.hpp"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QHostAddress>
#include <QHttpMultiPart>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonParseError>
#include <QNetworkProxy>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QPointer>
#include <QRegularExpression>
#include <QSaveFile>
#include <QSharedPointer>
#include <QSslError>

#include <limits>
#include <utility>

#if defined(Q_OS_WIN)
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#elif defined(Q_OS_UNIX)
#include <cerrno>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#endif

namespace {
constexpr auto EditorPrefix = "__forge/editor/v1";

QString responseDetail(const QByteArray &bytes, const QString &fallback)
{
    QJsonParseError parseError;
    const auto document = QJsonDocument::fromJson(bytes, &parseError);
    if (parseError.error == QJsonParseError::NoError && document.isObject()) {
        const auto detail = document.object().value(QStringLiteral("detail"));
        if (detail.isString()) {
            return detail.toString();
        }
        if (!detail.isUndefined()) {
            return QString::fromUtf8(
                QJsonDocument(QJsonObject{{QStringLiteral("detail"), detail}}).toJson(QJsonDocument::Compact));
        }
    }
    const auto text = QString::fromUtf8(bytes.left(2048)).trimmed();
    return text.isEmpty() ? fallback : text;
}

bool validSessionToken(const QByteArray &token)
{
    static const QRegularExpression pattern(
        QStringLiteral(R"(\Ajfe_session_[A-Za-z0-9_-]{40,100}\z)"));
    return pattern.match(QString::fromLatin1(token)).hasMatch();
}

bool validInvitationToken(const QString &token)
{
    static const QRegularExpression pattern(
        QStringLiteral(R"(\Ajfi_[A-Za-z0-9_-]{40,80}\z)"));
    return pattern.match(token).hasMatch();
}

bool validSetupToken(const QByteArray &token)
{
    if (token.size() < 32 || token.size() > 512) {
        return false;
    }
    for (const char character : token) {
        const auto byte = static_cast<unsigned char>(character);
        if (byte < 0x21U || byte > 0x7eU) {
            return false;
        }
    }
    return true;
}

constexpr qsizetype MaximumAttachmentSnapshot = 512 * 1024 * 1024;

bool safeAttachmentSnapshot(const QString &filePath, qsizetype maxBytes, QByteArray *snapshot,
                            QString *errorMessage)
{
    if (snapshot == nullptr || maxBytes < 0 || maxBytes > MaximumAttachmentSnapshot) {
        if (errorMessage != nullptr) {
            *errorMessage = QStringLiteral("The attachment size policy is invalid.");
        }
        return false;
    }

#if defined(Q_OS_WIN)
    const auto nativePath = QDir::toNativeSeparators(filePath);
    const auto handle = CreateFileW(reinterpret_cast<LPCWSTR>(nativePath.utf16()), GENERIC_READ,
                                    FILE_SHARE_READ, nullptr, OPEN_EXISTING,
                                    FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT
                                        | FILE_FLAG_SEQUENTIAL_SCAN,
                                    nullptr);
    if (handle == INVALID_HANDLE_VALUE) {
        if (errorMessage != nullptr) {
            *errorMessage = QStringLiteral("The selected file could not be opened safely.");
        }
        return false;
    }
    struct HandleGuard final {
        HANDLE value;
        ~HandleGuard() { CloseHandle(value); }
    } guard{handle};

    BY_HANDLE_FILE_INFORMATION before{};
    if (!GetFileInformationByHandle(handle, &before)
        || (before.dwFileAttributes & (FILE_ATTRIBUTE_DIRECTORY | FILE_ATTRIBUTE_REPARSE_POINT)) != 0) {
        if (errorMessage != nullptr) {
            *errorMessage = QStringLiteral("The selected path is not a regular non-link file.");
        }
        return false;
    }
    const quint64 expectedSize = (static_cast<quint64>(before.nFileSizeHigh) << 32U)
        | static_cast<quint64>(before.nFileSizeLow);
    if (expectedSize > static_cast<quint64>(maxBytes)
        || expectedSize > static_cast<quint64>(std::numeric_limits<qsizetype>::max())) {
        if (errorMessage != nullptr) {
            *errorMessage = QStringLiteral("The selected file exceeds the server attachment limit.");
        }
        return false;
    }

    QByteArray content;
    content.resize(static_cast<qsizetype>(expectedSize));
    quint64 offset = 0;
    while (offset < expectedSize) {
        const auto requestSize = static_cast<DWORD>(qMin<quint64>(
            expectedSize - offset, static_cast<quint64>(std::numeric_limits<DWORD>::max())));
        DWORD received = 0;
        if (!ReadFile(handle, content.data() + static_cast<qsizetype>(offset), requestSize,
                      &received, nullptr)
            || received == 0) {
            if (errorMessage != nullptr) {
                *errorMessage = QStringLiteral("The selected file changed or could not be read completely.");
            }
            return false;
        }
        offset += static_cast<quint64>(received);
    }
    BY_HANDLE_FILE_INFORMATION after{};
    if (!GetFileInformationByHandle(handle, &after)
        || before.dwVolumeSerialNumber != after.dwVolumeSerialNumber
        || before.nFileIndexHigh != after.nFileIndexHigh || before.nFileIndexLow != after.nFileIndexLow
        || before.nFileSizeHigh != after.nFileSizeHigh || before.nFileSizeLow != after.nFileSizeLow
        || CompareFileTime(&before.ftLastWriteTime, &after.ftLastWriteTime) != 0) {
        if (errorMessage != nullptr) {
            *errorMessage = QStringLiteral("The selected file changed while it was being read.");
        }
        return false;
    }
    *snapshot = std::move(content);
    return true;
#elif defined(Q_OS_UNIX)
    auto flags = O_RDONLY;
#ifdef O_CLOEXEC
    flags |= O_CLOEXEC;
#endif
#ifdef O_NOFOLLOW
    flags |= O_NOFOLLOW;
#endif
    const auto encodedPath = QFile::encodeName(filePath);
    const int descriptor = ::open(encodedPath.constData(), flags);
    if (descriptor < 0) {
        if (errorMessage != nullptr) {
            *errorMessage = QStringLiteral("The selected file could not be opened safely.");
        }
        return false;
    }
    struct DescriptorGuard final {
        int value;
        ~DescriptorGuard() { ::close(value); }
    } guard{descriptor};

    struct stat before {};
    if (::fstat(descriptor, &before) != 0 || !S_ISREG(before.st_mode) || before.st_size < 0
        || static_cast<quint64>(before.st_size) > static_cast<quint64>(maxBytes)) {
        if (errorMessage != nullptr) {
            *errorMessage = QStringLiteral("The selected path is not a bounded regular file.");
        }
        return false;
    }

    QByteArray content;
    content.reserve(static_cast<qsizetype>(before.st_size));
    char buffer[64 * 1024];
    while (true) {
        ssize_t received = -1;
        do {
            received = ::read(descriptor, buffer, sizeof(buffer));
        } while (received < 0 && errno == EINTR);
        if (received < 0) {
            if (errorMessage != nullptr) {
                *errorMessage = QStringLiteral("The selected file could not be read completely.");
            }
            return false;
        }
        if (received == 0) {
            break;
        }
        const auto count = static_cast<qsizetype>(received);
        if (content.size() > maxBytes - count) {
            if (errorMessage != nullptr) {
                *errorMessage = QStringLiteral("The selected file exceeds the server attachment limit.");
            }
            return false;
        }
        content.append(buffer, count);
    }

    struct stat after {};
    bool unchanged = ::fstat(descriptor, &after) == 0 && before.st_dev == after.st_dev
        && before.st_ino == after.st_ino && before.st_size == after.st_size;
#if defined(Q_OS_DARWIN)
    unchanged = unchanged && before.st_mtimespec.tv_sec == after.st_mtimespec.tv_sec
        && before.st_mtimespec.tv_nsec == after.st_mtimespec.tv_nsec
        && before.st_ctimespec.tv_sec == after.st_ctimespec.tv_sec
        && before.st_ctimespec.tv_nsec == after.st_ctimespec.tv_nsec;
#else
    unchanged = unchanged && before.st_mtim.tv_sec == after.st_mtim.tv_sec
        && before.st_mtim.tv_nsec == after.st_mtim.tv_nsec
        && before.st_ctim.tv_sec == after.st_ctim.tv_sec
        && before.st_ctim.tv_nsec == after.st_ctim.tv_nsec;
#endif
    if (!unchanged || content.size() != static_cast<qsizetype>(before.st_size)) {
        if (errorMessage != nullptr) {
            *errorMessage = QStringLiteral("The selected file changed while it was being read.");
        }
        return false;
    }
    *snapshot = std::move(content);
    return true;
#else
    QFile file(filePath);
    if (!file.open(QIODevice::ReadOnly)) {
        if (errorMessage != nullptr) {
            *errorMessage = QStringLiteral("The selected file could not be opened for reading.");
        }
        return false;
    }
    const auto content = file.read(maxBytes + 1);
    if (content.size() > maxBytes || !file.atEnd()) {
        if (errorMessage != nullptr) {
            *errorMessage = QStringLiteral("The selected file exceeds the server attachment limit.");
        }
        return false;
    }
    *snapshot = content;
    return true;
#endif
}

void hardenRequest(QNetworkRequest &request)
{
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    request.setAttribute(QNetworkRequest::CacheLoadControlAttribute, QNetworkRequest::AlwaysNetwork);
    request.setAttribute(QNetworkRequest::CacheSaveControlAttribute, false);
    request.setAttribute(QNetworkRequest::CookieLoadControlAttribute, QNetworkRequest::Manual);
    request.setAttribute(QNetworkRequest::CookieSaveControlAttribute, QNetworkRequest::Manual);
    request.setAttribute(QNetworkRequest::AuthenticationReuseAttribute, QNetworkRequest::Manual);
    request.setRawHeader("Cache-Control", "no-store");
}
} // namespace

ApiClient::ApiClient(QObject *parent)
    : QObject(parent)
{
    // A management session must never leak to a desktop's ambient HTTP proxy.
    m_network.setProxy(QNetworkProxy(QNetworkProxy::NoProxy));
}

ApiClient::~ApiClient()
{
    clearCredentials();
}

bool ApiClient::normalizeServerUrl(const QUrl &input, bool allowInsecureHttp, QUrl *normalized,
                                   QString *errorMessage)
{
    if (!input.isValid() || input.host().isEmpty() || !input.userInfo().isEmpty() || input.hasQuery()
        || input.hasFragment()) {
        if (errorMessage != nullptr) {
            *errorMessage = QStringLiteral("Enter an absolute server URL without credentials, query or fragment.");
        }
        return false;
    }
    const auto scheme = input.scheme().toLower();
    QHostAddress address;
    const bool loopbackHost = input.host().compare(QStringLiteral("localhost"), Qt::CaseInsensitive) == 0
        || (address.setAddress(input.host()) && address.isLoopback());
    if (scheme != QStringLiteral("https")
        && !(allowInsecureHttp && scheme == QStringLiteral("http") && loopbackHost)) {
        if (errorMessage != nullptr) {
            *errorMessage = QStringLiteral(
                "HTTPS is required. Plain HTTP can only be enabled explicitly for a loopback server.");
        }
        return false;
    }
    QUrl value(input);
    value.setScheme(scheme);
    auto path = value.path();
    while (path.endsWith(u'/')) {
        path.chop(1);
    }
    const auto pathParts = path.split(u'/', Qt::KeepEmptyParts);
    if (path.contains(u'\\') || path.contains(QChar::Null) || pathParts.contains(QStringLiteral("."))
        || pathParts.contains(QStringLiteral(".."))) {
        if (errorMessage != nullptr) {
            *errorMessage = QStringLiteral("The server URL base path contains an unsafe segment.");
        }
        return false;
    }
    value.setPath(path);
    if (normalized != nullptr) {
        *normalized = value;
    }
    return true;
}

bool ApiClient::configureServer(const QUrl &serverUrl, bool allowInsecureHttp, QString *errorMessage)
{
    QUrl normalized;
    if (!normalizeServerUrl(serverUrl, allowInsecureHttp, &normalized, errorMessage)) {
        return false;
    }
    clearCredentials();
    m_serverUrl = normalized;
    return true;
}

bool ApiClient::configure(const QUrl &serverUrl, const QByteArray &sessionToken, bool allowInsecureHttp,
                          QString *errorMessage)
{
    if (!configureServer(serverUrl, allowInsecureHttp, errorMessage)) {
        return false;
    }
    if (!setSessionToken(sessionToken, errorMessage)) {
        m_serverUrl.clear();
        return false;
    }
    return true;
}

bool ApiClient::setSessionToken(const QByteArray &sessionToken, QString *errorMessage)
{
    if (!validSessionToken(sessionToken)) {
        if (errorMessage != nullptr) {
            *errorMessage = QStringLiteral("The server returned an invalid Editor session token.");
        }
        return false;
    }
    m_sessionToken.fill('\0');
    m_sessionToken = sessionToken;
    return true;
}

void ApiClient::clearCredentials()
{
    m_sessionToken.fill('\0');
    m_sessionToken.clear();
    m_serverUrl.clear();
}

bool ApiClient::hasServer() const
{
    return m_serverUrl.isValid();
}

bool ApiClient::isConfigured() const
{
    return hasServer() && validSessionToken(m_sessionToken);
}

QUrl ApiClient::serverUrl() const
{
    return m_serverUrl;
}

QUrl ApiClient::endpointFor(const QStringList &pathSegments, const QUrlQuery &query) const
{
    auto path = m_serverUrl.path();
    path += u'/' + QString::fromLatin1(EditorPrefix);
    for (const auto &segment : pathSegments) {
        path += u'/' + QString::fromLatin1(QUrl::toPercentEncoding(segment, QByteArray(), QByteArray("/")));
    }
    QUrl result(m_serverUrl);
    result.setPath(path);
    result.setQuery(query);
    return result;
}

void ApiClient::send(const QString &operation, QNetworkAccessManager::Operation method,
                     const QStringList &pathSegments, const QJsonObject &body, const QUrlQuery &query,
                     bool authenticationRequired, const QList<QPair<QByteArray, QByteArray>> &extraHeaders)
{
    if (!hasServer() || (authenticationRequired && !isConfigured())) {
        emit requestFailed(operation, 0, QStringLiteral("Connect and sign in to a Forge server first."));
        return;
    }
    QNetworkRequest request(endpointFor(pathSegments, query));
    request.setHeader(QNetworkRequest::ContentTypeHeader, QStringLiteral("application/json"));
    request.setRawHeader("Accept", "application/json");
    if (authenticationRequired) {
        request.setRawHeader("Authorization", QByteArray("Bearer ") + m_sessionToken);
    }
    for (const auto &[name, value] : extraHeaders) {
        request.setRawHeader(name, value);
    }
    hardenRequest(request);
    request.setTransferTimeout(15000);
    const auto encodedBody = body.isEmpty() ? QByteArray() : QJsonDocument(body).toJson(QJsonDocument::Compact);
    QNetworkReply *reply = nullptr;
    switch (method) {
    case QNetworkAccessManager::GetOperation:
        reply = m_network.get(request);
        break;
    case QNetworkAccessManager::PostOperation:
        reply = m_network.post(request, encodedBody);
        break;
    case QNetworkAccessManager::PutOperation:
        reply = m_network.put(request, encodedBody);
        break;
    case QNetworkAccessManager::CustomOperation:
        reply = m_network.sendCustomRequest(request, QByteArray("PATCH"), encodedBody);
        break;
    default:
        emit requestFailed(operation, 0, QStringLiteral("Unsupported editor HTTP operation."));
        return;
    }

    trackJsonReply(reply, operation, authenticationRequired);
}

void ApiClient::trackJsonReply(QNetworkReply *reply, const QString &operation,
                               bool authenticationRequired)
{
    ++m_activeRequests;
    emit connectionActivityChanged(true);
    const auto buffer = QSharedPointer<QByteArray>::create();
    const auto tooLarge = QSharedPointer<bool>::create(false);
    connect(reply, &QNetworkReply::readyRead, this, [this, reply, buffer, tooLarge]() {
        buffer->append(reply->readAll());
        if (buffer->size() > m_maxResponseBytes) {
            *tooLarge = true;
            reply->abort();
        }
    });
    connect(reply, &QNetworkReply::sslErrors, this, [this, reply](const QList<QSslError> &errors) {
        QStringList descriptions;
        descriptions.reserve(errors.size());
        for (const auto &error : errors) {
            descriptions.append(error.errorString());
        }
        reply->abort();
        emit tlsRejected(descriptions.join(QStringLiteral("; ")));
    });
    connect(reply, &QNetworkReply::finished, this,
            [this, reply, operation, buffer, tooLarge, authenticationRequired]() {
                buffer->append(reply->readAll());
                if (buffer->size() > m_maxResponseBytes) {
                    *tooLarge = true;
                }
                m_activeRequests = qMax(0, m_activeRequests - 1);
                emit connectionActivityChanged(m_activeRequests > 0);
                const auto statusCode = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
                const auto redirect = reply->attribute(QNetworkRequest::RedirectionTargetAttribute);
                if (*tooLarge) {
                    emit requestFailed(operation, statusCode,
                                       QStringLiteral("Server response exceeded the 8 MiB editor limit."));
                } else if (redirect.isValid()) {
                    emit requestFailed(operation, statusCode,
                                       QStringLiteral("Redirects are not followed by the Editor client."));
                } else if (reply->error() != QNetworkReply::NoError || statusCode >= 400) {
                    if (authenticationRequired && statusCode == 401) {
                        m_sessionToken.fill('\0');
                        m_sessionToken.clear();
                    }
                    emit requestFailed(operation, statusCode,
                                       responseDetail(*buffer, reply->errorString()));
                } else if (statusCode == 204 && buffer->isEmpty()) {
                    emit jsonReceived(operation, QJsonObject{});
                } else {
                    QJsonParseError parseError;
                    const auto document = QJsonDocument::fromJson(*buffer, &parseError);
                    if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
                        emit requestFailed(operation, statusCode,
                                           QStringLiteral("Server returned an invalid JSON object."));
                    } else {
                        const auto payload = document.object();
                        if (operation.startsWith(QStringLiteral("auth-"))) {
                            QString tokenError;
                            if (!setSessionToken(payload.value(QStringLiteral("access_token")).toString().toUtf8(),
                                                 &tokenError)) {
                                emit requestFailed(operation, statusCode, tokenError);
                                reply->deleteLater();
                                return;
                            }
                        }
                        emit jsonReceived(operation, payload);
                    }
                }
                reply->deleteLater();
            });
}

void ApiClient::login(const QString &username, const QString &password)
{
    send(QStringLiteral("auth-login"), QNetworkAccessManager::PostOperation,
         {QStringLiteral("auth"), QStringLiteral("login")},
         QJsonObject{{QStringLiteral("username"), username}, {QStringLiteral("password"), password}}, {}, false);
}

void ApiClient::registerMember(const QString &invitation, const QString &username, const QString &password,
                               const QString &displayName)
{
    if (!validInvitationToken(invitation)) {
        emit requestFailed(QStringLiteral("auth-register"), 0,
                           QStringLiteral("The invitation token format is invalid."));
        return;
    }
    send(QStringLiteral("auth-register"), QNetworkAccessManager::PostOperation,
         {QStringLiteral("auth"), QStringLiteral("register")},
         QJsonObject{{QStringLiteral("invitation"), invitation},
                     {QStringLiteral("username"), username},
                     {QStringLiteral("password"), password},
                     {QStringLiteral("display_name"), displayName}},
         {}, false);
}

void ApiClient::setupFounder(const QByteArray &setupToken, const QString &username, const QString &password,
                             const QString &displayName)
{
    if (!validSetupToken(setupToken)) {
        emit requestFailed(QStringLiteral("auth-setup"), 0,
                           QStringLiteral("The founder setup token format is invalid."));
        return;
    }
    send(QStringLiteral("auth-setup"), QNetworkAccessManager::PostOperation,
         {QStringLiteral("setup"), QStringLiteral("founder")},
         QJsonObject{{QStringLiteral("username"), username},
                     {QStringLiteral("password"), password},
                     {QStringLiteral("display_name"), displayName}},
         {}, false, {{QByteArray("X-Forge-Setup-Token"), setupToken}});
}

void ApiClient::logout()
{
    send(QStringLiteral("auth-logout"), QNetworkAccessManager::PostOperation,
         {QStringLiteral("auth"), QStringLiteral("logout")});
    m_sessionToken.fill('\0');
    m_sessionToken.clear();
}

void ApiClient::fetchCapabilities()
{
    send(QStringLiteral("capabilities"), QNetworkAccessManager::GetOperation,
         {QStringLiteral("capabilities")});
}

void ApiClient::fetchProfile()
{
    send(QStringLiteral("team-me"), QNetworkAccessManager::GetOperation, {QStringLiteral("me")});
}

void ApiClient::updateProfile(const QJsonObject &values)
{
    send(QStringLiteral("team-profile-update"), QNetworkAccessManager::CustomOperation,
         {QStringLiteral("me")}, values);
}

void ApiClient::fetchProjects()
{
    send(QStringLiteral("projects"), QNetworkAccessManager::GetOperation, {QStringLiteral("projects")});
}

void ApiClient::createProject(const QString &directoryName, const QString &slug)
{
    send(QStringLiteral("create-project"), QNetworkAccessManager::PostOperation,
         {QStringLiteral("projects")},
         QJsonObject{{QStringLiteral("name"), directoryName}, {QStringLiteral("slug"), slug}});
}

void ApiClient::fetchDocuments(const QString &project)
{
    send(QStringLiteral("documents:%1").arg(project), QNetworkAccessManager::GetOperation,
         {QStringLiteral("projects"), project, QStringLiteral("documents")});
}

void ApiClient::fetchDocument(const QString &project, const QString &documentPath)
{
    send(QStringLiteral("document:%1:%2").arg(project, documentPath), QNetworkAccessManager::GetOperation,
         {QStringLiteral("projects"), project, QStringLiteral("documents"), documentPath});
}

void ApiClient::saveDocument(const QString &project, const QString &documentPath, const QByteArray &content,
                             const QString &expectedSha256)
{
    send(QStringLiteral("save:%1:%2").arg(project, documentPath), QNetworkAccessManager::PutOperation,
         {QStringLiteral("projects"), project, QStringLiteral("documents"), documentPath},
         QJsonObject{{QStringLiteral("content"), QString::fromUtf8(content)},
                     {QStringLiteral("expected_sha256"), expectedSha256}});
}

void ApiClient::validateProject(const QString &project)
{
    send(QStringLiteral("validate:%1").arg(project), QNetworkAccessManager::PostOperation,
         {QStringLiteral("projects"), project, QStringLiteral("validate")});
}

void ApiClient::fetchMembers()
{
    send(QStringLiteral("team-members"), QNetworkAccessManager::GetOperation, {QStringLiteral("members")});
}

void ApiClient::fetchRoles()
{
    send(QStringLiteral("team-roles"), QNetworkAccessManager::GetOperation, {QStringLiteral("roles")});
}

void ApiClient::createRole(const QString &name, int rank, const QJsonArray &permissions,
                           const QJsonArray &documentAllow, const QJsonArray &documentDeny,
                           const QJsonArray &databaseAllow)
{
    send(QStringLiteral("team-role-create"), QNetworkAccessManager::PostOperation,
         {QStringLiteral("roles")},
         QJsonObject{{QStringLiteral("name"), name},
                     {QStringLiteral("rank"), rank},
                     {QStringLiteral("permissions"), permissions},
                     {QStringLiteral("document_allow"), documentAllow},
                     {QStringLiteral("document_deny"), documentDeny},
                     {QStringLiteral("database_allow"), databaseAllow}});
}

void ApiClient::updateMember(const QString &userId, const QJsonArray &memberships, bool active)
{
    send(QStringLiteral("team-member-update"), QNetworkAccessManager::PutOperation,
         {QStringLiteral("members"), userId},
         QJsonObject{{QStringLiteral("memberships"), memberships},
                     {QStringLiteral("active"), active}});
}

void ApiClient::createInvitation(const QString &roleId, const QString &project, int expiresHours)
{
    const QJsonArray memberships{QJsonObject{{QStringLiteral("role_id"), roleId},
                                             {QStringLiteral("project"), project}}};
    send(QStringLiteral("team-invitation"), QNetworkAccessManager::PostOperation,
         {QStringLiteral("invitations")},
         QJsonObject{{QStringLiteral("memberships"), memberships},
                     {QStringLiteral("expires_hours"), expiresHours}});
}

void ApiClient::fetchAreas(const QString &project)
{
    QUrlQuery query;
    query.addQueryItem(QStringLiteral("project"), project);
    send(QStringLiteral("team-areas"), QNetworkAccessManager::GetOperation, {QStringLiteral("areas")}, {},
         query);
}

void ApiClient::createArea(const QString &project, const QString &name, const QString &description,
                           const QString &visibility, int minimumRank)
{
    send(QStringLiteral("team-area-create"), QNetworkAccessManager::PostOperation,
         {QStringLiteral("areas")},
         QJsonObject{{QStringLiteral("project"), project},
                     {QStringLiteral("name"), name},
                     {QStringLiteral("description"), description},
                     {QStringLiteral("visibility"), visibility},
                     {QStringLiteral("minimum_rank"), minimumRank},
                     {QStringLiteral("allowed_role_ids"), QJsonArray{}}});
}

void ApiClient::fetchMessages(const QString &areaId)
{
    QUrlQuery query;
    query.addQueryItem(QStringLiteral("limit"), QStringLiteral("200"));
    send(QStringLiteral("team-messages:%1").arg(areaId), QNetworkAccessManager::GetOperation,
         {QStringLiteral("areas"), areaId, QStringLiteral("messages")}, {}, query);
}

void ApiClient::postMessage(const QString &areaId, const QString &body, bool announcement)
{
    send(QStringLiteral("team-message:%1").arg(areaId), QNetworkAccessManager::PostOperation,
         {QStringLiteral("areas"), areaId, QStringLiteral("messages")},
         QJsonObject{{QStringLiteral("body"), body},
                     {QStringLiteral("kind"), announcement ? QStringLiteral("announcement")
                                                           : QStringLiteral("message")}});
}

void ApiClient::fetchAttachments(const QString &areaId)
{
    send(QStringLiteral("team-attachments:%1").arg(areaId), QNetworkAccessManager::GetOperation,
         {QStringLiteral("areas"), areaId, QStringLiteral("attachments")});
}

void ApiClient::uploadAttachment(const QString &areaId, const QString &filePath, qsizetype maxBytes)
{
    if (!isConfigured()) {
        emit requestFailed(QStringLiteral("team-attachment-upload"), 0,
                           QStringLiteral("Connect and sign in to a Forge server first."));
        return;
    }
    const QFileInfo info(filePath);
    const auto name = info.fileName();
    if (!info.exists() || !info.isFile() || info.isSymLink() || name.isEmpty()
        || name.size() > 255 || name.contains(u'\r') || name.contains(u'\n') || name.contains(u'"')
        || name.contains(u';') || name.contains(QChar::Null)) {
        emit requestFailed(QStringLiteral("team-attachment-upload"), 0,
                           QStringLiteral("The selected file is unsafe or exceeds the server attachment limit."));
        return;
    }
    QByteArray snapshot;
    QString snapshotError;
    if (!safeAttachmentSnapshot(info.absoluteFilePath(), maxBytes, &snapshot, &snapshotError)) {
        emit requestFailed(QStringLiteral("team-attachment-upload"), 0, snapshotError);
        return;
    }
    auto *multipart = new QHttpMultiPart(QHttpMultiPart::FormDataType);
    QHttpPart part;
    part.setHeader(QNetworkRequest::ContentTypeHeader, QStringLiteral("application/octet-stream"));
    part.setHeader(QNetworkRequest::ContentDispositionHeader,
                   QStringLiteral("form-data; name=\"upload\"; filename=\"%1\"").arg(name));
    part.setBody(snapshot);
    multipart->append(part);

    QNetworkRequest request(endpointFor(
        {QStringLiteral("areas"), areaId, QStringLiteral("attachments")}));
    request.setRawHeader("Accept", "application/json");
    request.setRawHeader("Authorization", QByteArray("Bearer ") + m_sessionToken);
    hardenRequest(request);
    request.setTransferTimeout(30000);
    auto *reply = m_network.post(request, multipart);
    multipart->setParent(reply);
    trackJsonReply(reply, QStringLiteral("team-attachment-upload"), true);
}

void ApiClient::downloadAttachment(const QString &attachmentId, const QString &targetPath,
                                   qsizetype maxBytes)
{
    const auto operation = QStringLiteral("team-attachment-download");
    if (!isConfigured() || targetPath.isEmpty() || maxBytes < 1) {
        emit requestFailed(operation, 0, QStringLiteral("A signed-in server and safe target path are required."));
        return;
    }
    QNetworkRequest request(endpointFor({QStringLiteral("attachments"), attachmentId}));
    request.setRawHeader("Accept", "application/octet-stream");
    request.setRawHeader("Authorization", QByteArray("Bearer ") + m_sessionToken);
    hardenRequest(request);
    request.setTransferTimeout(30000);
    auto *reply = m_network.get(request);
    ++m_activeRequests;
    emit connectionActivityChanged(true);
    const auto buffer = QSharedPointer<QByteArray>::create();
    const auto tooLarge = QSharedPointer<bool>::create(false);
    connect(reply, &QNetworkReply::readyRead, this, [reply, buffer, tooLarge, maxBytes]() {
        buffer->append(reply->readAll());
        if (buffer->size() > maxBytes) {
            *tooLarge = true;
            reply->abort();
        }
    });
    connect(reply, &QNetworkReply::sslErrors, this, [this, reply](const QList<QSslError> &errors) {
        QStringList descriptions;
        for (const auto &error : errors) {
            descriptions.append(error.errorString());
        }
        reply->abort();
        emit tlsRejected(descriptions.join(QStringLiteral("; ")));
    });
    connect(reply, &QNetworkReply::finished, this,
            [this, reply, operation, targetPath, buffer, tooLarge, maxBytes]() {
                buffer->append(reply->readAll());
                if (buffer->size() > maxBytes) {
                    *tooLarge = true;
                }
                m_activeRequests = qMax(0, m_activeRequests - 1);
                emit connectionActivityChanged(m_activeRequests > 0);
                const auto statusCode = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
                const auto redirect = reply->attribute(QNetworkRequest::RedirectionTargetAttribute);
                if (*tooLarge) {
                    emit requestFailed(operation, statusCode,
                                       QStringLiteral("Attachment exceeded the server-advertised size limit."));
                } else if (redirect.isValid()) {
                    emit requestFailed(operation, statusCode,
                                       QStringLiteral("Redirects are not followed by the Editor client."));
                } else if (reply->error() != QNetworkReply::NoError || statusCode >= 400) {
                    if (statusCode == 401) {
                        m_sessionToken.fill('\0');
                        m_sessionToken.clear();
                    }
                    emit requestFailed(operation, statusCode,
                                       responseDetail(*buffer, reply->errorString()));
                } else {
                    QSaveFile output(targetPath);
                    if (!output.open(QIODevice::WriteOnly) || output.write(*buffer) != buffer->size()
                        || !output.commit()) {
                        output.cancelWriting();
                        emit requestFailed(operation, 0,
                                           QStringLiteral("The attachment could not be saved atomically."));
                    } else {
                        emit fileDownloaded(operation, targetPath);
                    }
                }
                reply->deleteLater();
            });
}

void ApiClient::fetchNotes(const QString &project)
{
    QUrlQuery query;
    query.addQueryItem(QStringLiteral("project"), project);
    send(QStringLiteral("team-notes"), QNetworkAccessManager::GetOperation, {QStringLiteral("notes")}, {},
         query);
}

void ApiClient::createNote(const QString &project, const QString &areaId, const QString &title,
                           const QString &body, const QString &visibility)
{
    send(QStringLiteral("team-note-create"), QNetworkAccessManager::PostOperation,
         {QStringLiteral("notes")},
         QJsonObject{{QStringLiteral("project"), project},
                     {QStringLiteral("area_id"), areaId.isEmpty() ? QJsonValue(QJsonValue::Null)
                                                                  : QJsonValue(areaId)},
                     {QStringLiteral("title"), title},
                     {QStringLiteral("body"), body},
                     {QStringLiteral("visibility"), visibility},
                     {QStringLiteral("minimum_rank"), 0},
                     {QStringLiteral("allowed_role_ids"), QJsonArray{}}});
}

void ApiClient::fetchDatabases(const QString &project)
{
    send(QStringLiteral("team-databases:%1").arg(project), QNetworkAccessManager::GetOperation,
         {QStringLiteral("projects"), project, QStringLiteral("databases")});
}

void ApiClient::fetchDatabaseRows(const QString &project, const QString &alias, const QString &table,
                                  int limit, int offset)
{
    QUrlQuery query;
    query.addQueryItem(QStringLiteral("limit"), QString::number(qBound(1, limit, 500)));
    query.addQueryItem(QStringLiteral("offset"), QString::number(qMax(0, offset)));
    send(QStringLiteral("team-rows:%1:%2:%3").arg(project, alias, table),
         QNetworkAccessManager::GetOperation,
         {QStringLiteral("projects"), project, QStringLiteral("databases"), alias,
          QStringLiteral("tables"), table, QStringLiteral("rows")},
         {}, query);
}

void ApiClient::startCall(const QString &areaId, const QString &mode)
{
    send(QStringLiteral("team-call"), QNetworkAccessManager::PostOperation,
         {QStringLiteral("calls")},
         QJsonObject{{QStringLiteral("area_id"), areaId}, {QStringLiteral("mode"), mode}});
}

void ApiClient::createCallTicket(const QString &callId)
{
    send(QStringLiteral("team-call-ticket:%1").arg(callId), QNetworkAccessManager::PostOperation,
         {QStringLiteral("calls"), callId, QStringLiteral("ticket")});
}

void ApiClient::fetchAudit(const QString &project)
{
    QUrlQuery query;
    query.addQueryItem(QStringLiteral("limit"), QStringLiteral("200"));
    if (!project.isEmpty()) {
        query.addQueryItem(QStringLiteral("project"), project);
    }
    send(QStringLiteral("team-audit"), QNetworkAccessManager::GetOperation, {QStringLiteral("audit")}, {},
         query);
}

QUrl ApiClient::callClientUrl(const QString &path, const QString &ticket) const
{
    static const QRegularExpression ticketPattern(
        QStringLiteral(R"(\Ajfc_[A-Za-z0-9_-]{40,80}\z)"));
    static const QRegularExpression pathPattern(
        QStringLiteral(R"(\A/__forge/editor/v1/call-client/[A-Za-z0-9][A-Za-z0-9_-]{0,127}\z)"));
    if (!hasServer() || !pathPattern.match(path).hasMatch()
        || !ticketPattern.match(ticket).hasMatch()) {
        return {};
    }
    auto relative = path;
    while (relative.startsWith(u'/')) {
        relative.remove(0, 1);
    }
    auto basePath = m_serverUrl.path();
    if (!basePath.endsWith(u'/')) {
        basePath += u'/';
    }
    QUrl result(m_serverUrl);
    result.setPath(basePath + relative);
    QUrlQuery fragment;
    fragment.addQueryItem(QStringLiteral("ticket"), ticket);
    result.setFragment(fragment.query(QUrl::FullyEncoded));
    return result;
}
