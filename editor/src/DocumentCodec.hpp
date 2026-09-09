#pragma once

#include <QByteArray>
#include <QJsonObject>
#include <QString>

class DocumentCodec final {
public:
    static bool parseObject(const QByteArray &bytes, QJsonObject *object, QString *errorMessage);
    static QByteArray prettyJson(const QJsonObject &object);
    static QString sha256(const QByteArray &bytes);
    static bool isSafeDocumentPath(const QString &path, bool allowHooks);
    static bool saveAtomically(const QString &path, const QByteArray &bytes, QString *errorMessage);
};
