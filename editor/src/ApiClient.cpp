#include "ApiClient.hpp"

#include <QJsonDocument>
#include <QJsonParseError>
#include <QHostAddress>
#include <QNetworkProxy>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QPointer>
#include <QSharedPointer>
#include <QSslError>

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
            return QString::fromUtf8(QJsonDocument(QJsonObject{{QStringLiteral("detail"), detail}}).toJson(QJsonDocument::Compact));
        }
    }
    const auto text = QString::fromUtf8(bytes.left(2048)).trimmed();
    return text.isEmpty() ? fallback : text;
}
} // namespace

ApiClient::ApiClient(QObject *parent)
    : QObject(parent)
{
    // Never expose the independent editor token to an ambient desktop proxy.
    m_network.setProxy(QNetworkProxy(QNetworkProxy::NoProxy));
}

ApiClient::~ApiClient()
{
    clearCredentials();
}

bool ApiClient::normalizeServerUrl(const QUrl &input, bool allowInsecureHttp, QUrl *normalized, QString *errorMessage)
{
    if (!input.isValid() || input.host().isEmpty() || !input.userInfo().isEmpty() || input.hasQuery() || input.hasFragment()) {
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
            *errorMessage = QStringLiteral("HTTPS is required. Plain HTTP can only be enabled explicitly for a loopback server.");
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

bool ApiClient::configure(const QUrl &serverUrl, const QByteArray &token, bool allowInsecureHttp, QString *errorMessage)
{
    QUrl normalized;
    if (!normalizeServerUrl(serverUrl, allowInsecureHttp, &normalized, errorMessage)) {
        return false;
    }
    if (token.size() < 32 || token.size() > 512 || token.contains('\r') || token.contains('\n')) {
        if (errorMessage != nullptr) {
            *errorMessage = QStringLiteral("The editor token must be 32–512 characters and contain no line breaks.");
        }
        return false;
    }
    clearCredentials();
    m_serverUrl = normalized;
    m_token = token;
    return true;
}

void ApiClient::clearCredentials()
{
    m_token.fill('\0');
    m_token.clear();
    m_serverUrl.clear();
}

bool ApiClient::isConfigured() const
{
    return m_serverUrl.isValid() && !m_token.isEmpty();
}

QUrl ApiClient::serverUrl() const
{
    return m_serverUrl;
}

QUrl ApiClient::endpointFor(const QStringList &pathSegments) const
{
    auto path = m_serverUrl.path();
    path += u'/' + QString::fromLatin1(EditorPrefix);
    for (const auto &segment : pathSegments) {
        path += u'/' + QString::fromLatin1(QUrl::toPercentEncoding(segment, QByteArray(), QByteArray("/")));
    }
    QUrl result(m_serverUrl);
    result.setPath(path);
    return result;
}

void ApiClient::send(const QString &operation, QNetworkAccessManager::Operation method, const QStringList &pathSegments,
                     const QJsonObject &body)
{
    if (!isConfigured()) {
        emit requestFailed(operation, 0, QStringLiteral("Connect to a Forge server first."));
        return;
    }
    QNetworkRequest request(endpointFor(pathSegments));
    request.setHeader(QNetworkRequest::ContentTypeHeader, QStringLiteral("application/json"));
    request.setRawHeader("Accept", "application/json");
    request.setRawHeader("X-Forge-Editor-Token", m_token);
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
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
    default:
        emit requestFailed(operation, 0, QStringLiteral("Unsupported editor HTTP operation."));
        return;
    }

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
    connect(reply, &QNetworkReply::finished, this, [this, reply, operation, buffer, tooLarge]() {
        buffer->append(reply->readAll());
        if (buffer->size() > m_maxResponseBytes) {
            *tooLarge = true;
        }
        m_activeRequests = qMax(0, m_activeRequests - 1);
        emit connectionActivityChanged(m_activeRequests > 0);
        const auto statusCode = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        const auto redirect = reply->attribute(QNetworkRequest::RedirectionTargetAttribute);
        if (*tooLarge) {
            emit requestFailed(operation, statusCode, QStringLiteral("Server response exceeded the 4 MiB editor limit."));
        } else if (redirect.isValid()) {
            emit requestFailed(operation, statusCode, QStringLiteral("Redirects are not followed by the editor client."));
        } else if (reply->error() != QNetworkReply::NoError || statusCode >= 400) {
            emit requestFailed(operation, statusCode, responseDetail(*buffer, reply->errorString()));
        } else {
            QJsonParseError parseError;
            const auto document = QJsonDocument::fromJson(*buffer, &parseError);
            if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
                emit requestFailed(operation, statusCode, QStringLiteral("Server returned an invalid JSON object."));
            } else {
                emit jsonReceived(operation, document.object());
            }
        }
        reply->deleteLater();
    });
}

void ApiClient::fetchCapabilities()
{
    send(QStringLiteral("capabilities"), QNetworkAccessManager::GetOperation, {QStringLiteral("capabilities")});
}

void ApiClient::fetchProjects()
{
    send(QStringLiteral("projects"), QNetworkAccessManager::GetOperation, {QStringLiteral("projects")});
}

void ApiClient::createProject(const QString &directoryName, const QString &slug)
{
    send(QStringLiteral("create-project"), QNetworkAccessManager::PostOperation, {QStringLiteral("projects")},
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
         QJsonObject{{QStringLiteral("content"), QString::fromUtf8(content)}, {QStringLiteral("expected_sha256"), expectedSha256}});
}

void ApiClient::validateProject(const QString &project)
{
    send(QStringLiteral("validate:%1").arg(project), QNetworkAccessManager::PostOperation,
         {QStringLiteral("projects"), project, QStringLiteral("validate")});
}
