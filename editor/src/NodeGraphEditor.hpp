#pragma once

#include "GraphModel.hpp"

#include <QHash>
#include <QWidget>

class QGraphicsItem;
class QGraphicsScene;
class QLabel;
class QLineEdit;
class QListWidget;
class QPlainTextEdit;
class QPushButton;

class NodeGraphEditor final : public QWidget {
    Q_OBJECT

public:
    explicit NodeGraphEditor(QWidget *parent = nullptr);

    bool setDocument(const QJsonObject &document, QString *errorMessage = nullptr);
    [[nodiscard]] QJsonObject document() const;
    [[nodiscard]] static QJsonObject starterDocument(const QString &targetDocument);
    void addPaletteNode(const QString &label, const QString &type, const QJsonObject &properties);

signals:
    void documentChanged(const QJsonObject &document);
    void statusMessage(const QString &message);

private:
    void installPalette();
    void rebuildScene();
    void updateConnections();
    void addNodeFromPayload(const QByteArray &payload, const QPointF &position);
    void connectNodes(const QString &fromNode, const QString &toNode);
    void showSelection();
    void applyInspector();
    void applyTarget();
    void deleteSelection();
    void autoLayout();
    void showCompiledPreview();
    void fitGraph();
    void notifyChanged();

    GraphModel m_model;
    QListWidget *m_palette = nullptr;
    QGraphicsScene *m_scene = nullptr;
    QWidget *m_view = nullptr;
    QLineEdit *m_target = nullptr;
    QLabel *m_selectedType = nullptr;
    QLineEdit *m_selectedTitle = nullptr;
    QPlainTextEdit *m_properties = nullptr;
    QPushButton *m_apply = nullptr;
    QHash<QString, QGraphicsItem *> m_nodeItems;
    QList<QGraphicsItem *> m_edgeItems;
    bool m_updating = false;
};
