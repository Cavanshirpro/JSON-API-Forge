#include "DocumentCodec.hpp"

#include <QCryptographicHash>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonParseError>
#include <QRegularExpression>
#include <QSaveFile>

bool DocumentCodec::parseObject(const QByteArray &bytes, QJsonObject *object, QString *errorMessage)
{
    QJsonParseError error;
    const auto document = QJsonDocument::fromJson(bytes, &error);
    if (error.error != QJsonParseError::NoError) {
        if (errorMessage != nullptr) {
            *errorMessage = QStringLiteral("%1 at byte %2").arg(error.errorString()).arg(error.offset);
        }
        return false;
    }
    if (!document.isObject()) {
        if (errorMessage != nullptr) {
            *errorMessage = QStringLiteral("The JSON document root must be an object.");
        }
        return false;
    }
    if (object != nullptr) {
        *object = document.object();
    }
    return true;
}

QByteArray DocumentCodec::prettyJson(const QJsonObject &object)
{
    return QJsonDocument(object).toJson(QJsonDocument::Indented);
}

QString DocumentCodec::sha256(const QByteArray &bytes)
{
    return QString::fromLatin1(QCryptographicHash::hash(bytes, QCryptographicHash::Sha256).toHex());
}

bool DocumentCodec::isSafeDocumentPath(const QString &path, bool allowHooks)
{
    if (path.isEmpty() || path.startsWith(u'/') || path.contains(u'\\') || path.contains(QChar::Null)) {
        return false;
    }
    const auto parts = path.split(u'/', Qt::KeepEmptyParts);
    if (parts.contains(QString()) || parts.contains(QStringLiteral(".")) || parts.contains(QStringLiteral(".."))) {
        return false;
    }
    if (path == QStringLiteral("app.json")) {
        return true;
    }
    if (parts.size() != 2) {
        return false;
    }
    if (parts.at(0) == QStringLiteral("config")) {
        return parts.at(1).endsWith(QStringLiteral(".json"), Qt::CaseSensitive) && !parts.at(1).startsWith(u'.');
    }
    return allowHooks && parts.at(0) == QStringLiteral("hooks") && parts.at(1).endsWith(QStringLiteral(".py"), Qt::CaseSensitive)
        && !parts.at(1).startsWith(u'.');
}

bool DocumentCodec::saveAtomically(const QString &path, const QByteArray &bytes, QString *errorMessage)
{
    QSaveFile file(path);
    file.setDirectWriteFallback(false);
    if (!file.open(QIODevice::WriteOnly)) {
        if (errorMessage != nullptr) {
            *errorMessage = file.errorString();
        }
        return false;
    }
    if (file.write(bytes) != bytes.size() || !file.commit()) {
        if (errorMessage != nullptr) {
            *errorMessage = file.errorString();
        }
        return false;
    }
    return true;
}
