#pragma once

#include <QJsonArray>
#include <QJsonObject>
#include <QPointF>
#include <QStringList>

class GraphModel final {
public:
    GraphModel();

    [[nodiscard]] const QJsonObject &document() const;
    bool setDocument(const QJsonObject &document, QString *errorMessage = nullptr);
    [[nodiscard]] bool validate(QString *errorMessage = nullptr) const;
    [[nodiscard]] QStringList topologicalOrder(QString *errorMessage = nullptr) const;

    [[nodiscard]] QString addNode(const QString &type, const QString &title, const QPointF &position,
                                  const QJsonObject &properties = {});
    bool updateNode(const QString &id, const QString &title, const QJsonObject &properties, QString *errorMessage = nullptr);
    bool moveNode(const QString &id, const QPointF &position);
    bool removeNode(const QString &id);
    bool connectNodes(const QString &fromNode, const QString &fromPort, const QString &toNode, const QString &toPort,
                      QString *errorMessage = nullptr);
    bool removeEdge(const QString &id);

    [[nodiscard]] QJsonObject node(const QString &id) const;
    [[nodiscard]] QJsonObject compiledFragment(QString *errorMessage = nullptr) const;
    [[nodiscard]] static QJsonObject emptyDocument(const QString &targetDocument = QStringLiteral("config/50-graph-operation.json"));

private:
    QJsonObject m_document;
};
