#pragma once

#include <QJsonArray>
#include <QNetworkAccessManager>
#include <QObject>
#include <QUrl>

class PluginCatalogClient final : public QObject {
    Q_OBJECT

public:
    explicit PluginCatalogClient(QObject *parent = nullptr);

    void fetch(const QUrl &serverUrl, const QByteArray &apiKey, const QString &project, const QString &resource,
               bool allowInsecureHttp = false);
    [[nodiscard]] static bool catalogEndpoint(const QUrl &serverUrl, const QString &project, const QString &resource,
                                              bool allowInsecureHttp, QUrl *endpoint, QString *errorMessage);
    [[nodiscard]] static bool validateCatalog(const QJsonArray &items, QString *errorMessage);

signals:
    void catalogReceived(const QJsonArray &items);
    void requestFailed(const QString &message);

private:
    QNetworkAccessManager m_network;
    qsizetype m_maxResponseBytes = 2 * 1024 * 1024;
};
