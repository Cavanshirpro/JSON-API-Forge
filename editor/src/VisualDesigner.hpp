#pragma once

#include <QJsonObject>
#include <QWidget>

class QListWidget;
class QTableWidget;
class QTreeWidget;

class VisualDesigner final : public QWidget {
    Q_OBJECT

public:
    explicit VisualDesigner(QWidget *parent = nullptr);
    void setDocument(const QJsonObject &document);
    [[nodiscard]] QJsonObject document() const;
    void addPaletteComponent(const QString &label, const QString &collection, const QJsonObject &value);

signals:
    void documentChanged(const QJsonObject &document);
    void statusMessage(const QString &message);

private:
    void installBuiltInComponents();
    void refreshCanvas();
    void showProperties();
    void applyPropertyEdit(int row, int column);
    void insertTemplate(const QByteArray &payload);
    [[nodiscard]] QJsonObject selectedObject() const;
    void replaceSelectedObject(const QJsonObject &value);

    QListWidget *m_palette = nullptr;
    QTreeWidget *m_canvas = nullptr;
    QTableWidget *m_properties = nullptr;
    QJsonObject m_document;
    bool m_refreshing = false;
};
