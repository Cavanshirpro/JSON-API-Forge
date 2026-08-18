#include "PluginCatalogClient.hpp"

#include "ApiClient.hpp"

#include <QJsonDocument>
#include <QJsonParseError>
#include <QNetworkProxy>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QPointer>
#include <QRegularExpression>
#include <QSharedPointer>
#include <QSslError>
#include <QSet>
#include <QUrlQuery>

namespace {
bool fail(QString *errorMessage, const QString &message)
{
    if (errorMessage != nullptr) {
        *errorMessage = message;
    }
    return false;
}

QString responseDetail(const QByteArray &bytes, const QString &fallback)
{
    QJsonParseError error;
    const auto document = QJsonDocument::fromJson(bytes, &error);
    if (error.error == QJsonParseError::NoError && document.isObject()) {
        const auto detail = document.object().value(QStringLiteral("detail"));
        if (detail.isString()) {
            return detail.toString();
        }
    }
    const auto text = QString::fromUtf8(bytes.left(2048)).trimmed();
    return text.isEmpty() ? fallback : text;
}
} // namespace

PluginCatalogClient::PluginCatalogClient(QObject *parent)
    : QObject(parent)
{
    m_network.setProxy(QNetworkProxy(QNetworkProxy::NoProxy));
}

bool PluginCatalogClient::catalogEndpoint(const QUrl &serverUrl, const QString &project, const QString &resource,
                                          bool allowInsecureHttp, QUrl *endpoint, QString *errorMessage)
{
    static const QRegularExpression SegmentPattern(QStringLiteral(R"(^[A-Za-z0-9][A-Za-z0-9._:-]{0,126}$)"));
    QUrl normalized;
    if (!ApiClient::normalizeServerUrl(serverUrl, allowInsecureHttp, &normalized, errorMessage)) {
        return false;
    }
    if (!SegmentPattern.match(project).hasMatch()) {
        return fail(errorMessage, QStringLiteral("Plugin catalog project is not a safe path segment."));
    }
    const auto resourceParts = resource.split(u'/', Qt::KeepEmptyParts);
    if (resourceParts.isEmpty() || resourceParts.size() > 8) {
        return fail(errorMessage, QStringLiteral("Plugin catalog resource must contain 1–8 path segments."));
    }
    for (const auto &part : resourceParts) {
        if (!SegmentPattern.match(part).hasMatch()) {
            return fail(errorMessage, QStringLiteral("Plugin catalog resource contains an unsafe path segment."));
        }
    }
    auto path = normalized.path();
    path += QStringLiteral("/api/") + project + QStringLiteral("/v1/") + resourceParts.join(u'/');
    normalized.setPath(path);
    QUrlQuery query;
    query.addQueryItem(QStringLiteral("limit"), QStringLiteral("100"));
    query.addQueryItem(QStringLiteral("offset"), QStringLiteral("0"));
    normalized.setQuery(query);
    if (endpoint != nullptr) {
        *endpoint = normalized;
    }
    return true;
}

bool PluginCatalogClient::validateCatalog(const QJsonArray &items, QString *errorMessage)
{
    static const QRegularExpression IdPattern(QStringLiteral(R"(^[a-z0-9]+(?:[.-][a-z0-9]+)*$)"));
    static const QRegularExpression DigestPattern(QStringLiteral(R"(^[a-fA-F0-9]{64}$)"));
    if (items.size() > 100) {
        return fail(errorMessage, QStringLiteral("Plugin catalog exceeds the 100-item response limit."));
    }
    QSet<QString> identities;
    for (qsizetype index = 0; index < items.size(); ++index) {
        if (!items.at(index).isObject()) {
            return fail(errorMessage, QStringLiteral("Plugin catalog item %1 must be an object.").arg(index));
        }
        const auto item = items.at(index).toObject();
        const auto id = item.value(QStringLiteral("plugin_id")).toString(item.value(QStringLiteral("id")).toString());
        const auto name = item.value(QStringLiteral("name")).toString();
        const auto version = item.value(QStringLiteral("version")).toString();
        const auto sha256 = item.value(QStringLiteral("sha256")).toString();
        const auto download = QUrl(item.value(QStringLiteral("download_url")).toString());
        if (!IdPattern.match(id).hasMatch() || name.isEmpty() || name.size() > 160 || version.isEmpty() || version.size() > 64
            || !DigestPattern.match(sha256).hasMatch() || !download.isValid() || download.scheme() != QStringLiteral("https")
            || download.userInfo().size() > 0 || download.hasFragment()) {
            return fail(errorMessage, QStringLiteral("Plugin catalog item %1 has invalid identity, package URL, or SHA-256 metadata.").arg(index));
        }
        const auto identity = id + QChar::Null + version;
        if (identities.contains(identity)) {
            return fail(errorMessage, QStringLiteral("Plugin catalog contains a duplicate plugin/version pair."));
        }
        identities.insert(identity);
        const auto permissions = item.value(QStringLiteral("permissions"));
        if (!permissions.isUndefined()) {
            if (!permissions.isArray() || permissions.toArray().size() > 32) {
                return fail(errorMessage, QStringLiteral("Plugin catalog item %1 has invalid permissions.").arg(index));
            }
            for (const auto &permission : permissions.toArray()) {
                if (!permission.isString() || permission.toString().isEmpty() || permission.toString().size() > 96) {
                    return fail(errorMessage, QStringLiteral("Plugin catalog item %1 has an invalid permission entry.").arg(index));
                }
            }
        }
    }
    return true;
}

void PluginCatalogClient::fetch(const QUrl &serverUrl, const QByteArray &apiKey, const QString &project,
                                const QString &resource, bool allowInsecureHttp)
{
    if (apiKey.isEmpty() || apiKey.size() > 4096 || apiKey.contains('\r') || apiKey.contains('\n') || apiKey.contains('\0')) {
        emit requestFailed(QStringLiteral("API key must be 1–4096 bytes and contain no control line breaks or NUL."));
        return;
    }
    QUrl endpoint;
    QString error;
    if (!catalogEndpoint(serverUrl, project, resource, allowInsecureHttp, &endpoint, &error)) {
        emit requestFailed(error);
        return;
    }
    QNetworkRequest request(endpoint);
    request.setRawHeader("Accept", "application/json");
    request.setRawHeader("X-API-Key", apiKey);
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    request.setTransferTimeout(15'000);
    auto *reply = m_network.get(request);
    const auto buffer = QSharedPointer<QByteArray>::create();
    const auto tooLarge = QSharedPointer<bool>::create(false);
    connect(reply, &QNetworkReply::readyRead, this, [this, reply, buffer, tooLarge] {
        buffer->append(reply->readAll());
        if (buffer->size() > m_maxResponseBytes) {
            *tooLarge = true;
            reply->abort();
        }
    });
    connect(reply, &QNetworkReply::sslErrors, this, [this, reply](const QList<QSslError> &errors) {
        QStringList messages;
        for (const auto &sslError : errors) {
            messages.append(sslError.errorString());
        }
        reply->abort();
        emit requestFailed(QStringLiteral("TLS validation failed: %1").arg(messages.join(QStringLiteral("; "))));
    });
    connect(reply, &QNetworkReply::finished, this, [this, reply, buffer, tooLarge] {
        buffer->append(reply->readAll());
        const auto status = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        const auto redirect = reply->attribute(QNetworkRequest::RedirectionTargetAttribute);
        if (*tooLarge || buffer->size() > m_maxResponseBytes) {
            emit requestFailed(QStringLiteral("Plugin catalog response exceeded 2 MiB."));
        } else if (redirect.isValid()) {
            emit requestFailed(QStringLiteral("Plugin catalog redirects are not followed."));
        } else if (reply->error() != QNetworkReply::NoError || status >= 400) {
            emit requestFailed(responseDetail(*buffer, reply->errorString()));
        } else {
            QJsonParseError parseError;
            const auto document = QJsonDocument::fromJson(*buffer, &parseError);
            if (parseError.error != QJsonParseError::NoError || !document.isObject()
                || !document.object().value(QStringLiteral("items")).isArray()) {
                emit requestFailed(QStringLiteral("Forge catalog response does not contain an items array."));
            } else {
                const auto items = document.object().value(QStringLiteral("items")).toArray();
                QString validationError;
                if (!validateCatalog(items, &validationError)) {
                    emit requestFailed(validationError);
                } else {
                    emit catalogReceived(items);
                }
            }
        }
        reply->deleteLater();
    });
}
