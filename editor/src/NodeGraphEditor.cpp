#include "NodeGraphEditor.hpp"

#include "DocumentCodec.hpp"

#include <QAbstractItemView>
#include <QApplication>
#include <QClipboard>
#include <QDragEnterEvent>
#include <QDialog>
#include <QDropEvent>
#include <QFormLayout>
#include <QGraphicsItem>
#include <QGraphicsPathItem>
#include <QGraphicsScene>
#include <QGraphicsSceneMouseEvent>
#include <QGraphicsView>
#include <QHeaderView>
#include <QHBoxLayout>
#include <QJsonDocument>
#include <QJsonParseError>
#include <QKeyEvent>
#include <QLabel>
#include <QLineF>
#include <QLineEdit>
#include <QListWidget>
#include <QMessageBox>
#include <QMimeData>
#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QScrollBar>
#include <QSplitter>
#include <QToolButton>
#include <QTimer>
#include <QVBoxLayout>
#include <QWheelEvent>
#include <QVector>

#include <algorithm>
#include <functional>
#include <utility>

namespace {
const auto GraphNodeMime = QStringLiteral("application/x-json-api-forge-graph-node");
constexpr qreal NodeWidth = 224.0;
constexpr qreal NodeHeight = 116.0;
constexpr qreal HeaderHeight = 38.0;
constexpr int NodeItemType = QGraphicsItem::UserType + 31;
constexpr int EdgeItemType = QGraphicsItem::UserType + 32;

QColor nodeColor(const QString &type)
{
    if (type.startsWith(QStringLiteral("request."))) {
        return QColor(QStringLiteral("#4ea1ff"));
    }
    if (type.startsWith(QStringLiteral("auth."))) {
        return QColor(QStringLiteral("#c17cff"));
    }
    if (type.startsWith(QStringLiteral("data."))) {
        return QColor(QStringLiteral("#55d6a7"));
    }
    if (type.startsWith(QStringLiteral("logic."))) {
        return QColor(QStringLiteral("#f2b84b"));
    }
    if (type.startsWith(QStringLiteral("python."))) {
        return QColor(QStringLiteral("#73a7ff"));
    }
    if (type.startsWith(QStringLiteral("response."))) {
        return QColor(QStringLiteral("#ff7c91"));
    }
    return QColor(QStringLiteral("#f2b84b"));
}

class GraphNodeItem final : public QGraphicsItem {
public:
    GraphNodeItem(QString id, QString type, QString title)
        : m_id(std::move(id))
        , m_type(std::move(type))
        , m_title(std::move(title))
    {
        setFlags(ItemIsMovable | ItemIsSelectable | ItemSendsGeometryChanges);
        setCacheMode(DeviceCoordinateCache);
        setZValue(2.0);
    }

    [[nodiscard]] int type() const override { return NodeItemType; }
    [[nodiscard]] QRectF boundingRect() const override { return QRectF(0.0, 0.0, NodeWidth, NodeHeight); }
    [[nodiscard]] QString nodeId() const { return m_id; }
    [[nodiscard]] bool hasInput() const { return m_type != QStringLiteral("request.input"); }
    [[nodiscard]] bool hasOutput() const { return m_type != QStringLiteral("response.output"); }
    [[nodiscard]] QPointF inputPoint() const { return mapToScene(QPointF(0.0, 76.0)); }
    [[nodiscard]] QPointF outputPoint() const { return mapToScene(QPointF(NodeWidth, 76.0)); }

    [[nodiscard]] bool inputHit(const QPointF &scenePosition) const
    {
        return hasInput() && QLineF(inputPoint(), scenePosition).length() <= 13.0;
    }

    [[nodiscard]] bool outputHit(const QPointF &scenePosition) const
    {
        return hasOutput() && QLineF(outputPoint(), scenePosition).length() <= 13.0;
    }

    std::function<void(const QString &, const QPointF &)> moved;

protected:
    QVariant itemChange(GraphicsItemChange change, const QVariant &value) override
    {
        const auto result = QGraphicsItem::itemChange(change, value);
        if (change == ItemPositionHasChanged && moved) {
            moved(m_id, value.toPointF());
        }
        return result;
    }

    void paint(QPainter *painter, const QStyleOptionGraphicsItem *, QWidget *) override
    {
        painter->setRenderHint(QPainter::Antialiasing);
        const auto accent = nodeColor(m_type);
        const auto body = isSelected() ? QColor(QStringLiteral("#36393f")) : QColor(QStringLiteral("#292b2f"));
        painter->setPen(QPen(isSelected() ? accent : QColor(QStringLiteral("#52565e")), isSelected() ? 2.0 : 1.0));
        painter->setBrush(body);
        painter->drawRoundedRect(boundingRect().adjusted(1.0, 1.0, -1.0, -1.0), 10.0, 10.0);

        QPainterPath header;
        header.addRoundedRect(QRectF(1.0, 1.0, NodeWidth - 2.0, HeaderHeight), 9.0, 9.0);
        painter->setClipRect(QRectF(1.0, 1.0, NodeWidth - 2.0, HeaderHeight));
        QLinearGradient gradient(0.0, 0.0, NodeWidth, 0.0);
        gradient.setColorAt(0.0, accent.darker(180));
        gradient.setColorAt(1.0, QColor(QStringLiteral("#34373c")));
        painter->setPen(Qt::NoPen);
        painter->setBrush(gradient);
        painter->drawPath(header);
        painter->setClipping(false);

        painter->setPen(QColor(QStringLiteral("#f8f4eb")));
        QFont titleFont = painter->font();
        titleFont.setBold(true);
        titleFont.setPointSizeF(10.0);
        painter->setFont(titleFont);
        painter->drawText(QRectF(14.0, 4.0, NodeWidth - 28.0, 30.0), Qt::AlignVCenter | Qt::AlignLeft,
                          painter->fontMetrics().elidedText(m_title, Qt::ElideRight, static_cast<int>(NodeWidth - 30.0)));

        QFont typeFont = painter->font();
        typeFont.setBold(false);
        typeFont.setPointSizeF(8.0);
        painter->setFont(typeFont);
        painter->setPen(QColor(QStringLiteral("#a8a9ac")));
        painter->drawText(QRectF(14.0, 48.0, NodeWidth - 28.0, 20.0), Qt::AlignLeft | Qt::AlignVCenter, m_type);
        painter->setPen(QColor(QStringLiteral("#85878e")));
        painter->drawText(QRectF(14.0, 82.0, NodeWidth - 28.0, 22.0), Qt::AlignCenter,
                          QStringLiteral("Double-click properties to configure"));

        painter->setPen(QPen(QColor(QStringLiteral("#151619")), 2.0));
        painter->setBrush(accent);
        if (hasInput()) {
            painter->drawEllipse(QPointF(0.0, 76.0), 7.0, 7.0);
        }
        if (hasOutput()) {
            painter->drawEllipse(QPointF(NodeWidth, 76.0), 7.0, 7.0);
        }
    }

private:
    QString m_id;
    QString m_type;
    QString m_title;
};

class GraphEdgeItem final : public QGraphicsPathItem {
public:
    GraphEdgeItem(QString id, GraphNodeItem *source, GraphNodeItem *target)
        : m_id(std::move(id))
        , m_source(source)
        , m_target(target)
    {
        setFlag(ItemIsSelectable);
        setZValue(1.0);
        updatePath();
    }

    [[nodiscard]] int type() const override { return EdgeItemType; }
    [[nodiscard]] QString edgeId() const { return m_id; }

    void updatePath()
    {
        const auto start = m_source->outputPoint();
        const auto end = m_target->inputPoint();
        const auto distance = std::max<qreal>(70.0, std::abs(end.x() - start.x()) * 0.5);
        QPainterPath wire(start);
        wire.cubicTo(start + QPointF(distance, 0.0), end - QPointF(distance, 0.0), end);
        setPath(wire);
        setPen(QPen(isSelected() ? QColor(QStringLiteral("#ffd071")) : QColor(QStringLiteral("#9fa1a6")),
                    isSelected() ? 3.0 : 2.0, Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
    }

protected:
    QVariant itemChange(GraphicsItemChange change, const QVariant &value) override
    {
        if (change == ItemSelectedHasChanged) {
            updatePath();
        }
        return QGraphicsPathItem::itemChange(change, value);
    }

private:
    QString m_id;
    GraphNodeItem *m_source = nullptr;
    GraphNodeItem *m_target = nullptr;
};

class GraphPalette final : public QListWidget {
public:
    using QListWidget::QListWidget;

protected:
    [[nodiscard]] QStringList mimeTypes() const override { return {GraphNodeMime}; }

    [[nodiscard]] QMimeData *mimeData(const QList<QListWidgetItem *> &items) const override
    {
        auto *mime = new QMimeData;
        if (!items.isEmpty()) {
            mime->setData(GraphNodeMime, items.first()->data(Qt::UserRole).toByteArray());
        }
        return mime;
    }
};

class GraphView final : public QGraphicsView {
public:
    explicit GraphView(QGraphicsScene *scene, QWidget *parent = nullptr)
        : QGraphicsView(scene, parent)
    {
        setObjectName(QStringLiteral("graphCanvas"));
        setAcceptDrops(true);
        setRenderHints(QPainter::Antialiasing | QPainter::TextAntialiasing | QPainter::SmoothPixmapTransform);
        setViewportUpdateMode(BoundingRectViewportUpdate);
        setTransformationAnchor(AnchorUnderMouse);
        setResizeAnchor(AnchorViewCenter);
        setDragMode(RubberBandDrag);
        setSceneRect(-50'000.0, -50'000.0, 100'000.0, 100'000.0);
    }

    std::function<void(const QByteArray &, const QPointF &)> nodeDropped;
    std::function<void(const QString &, const QString &)> nodesConnected;
    std::function<void()> deleteRequested;

protected:
    void drawBackground(QPainter *painter, const QRectF &rect) override
    {
        painter->fillRect(rect, QColor(QStringLiteral("#1a1b1e")));
        const int minor = 20;
        const int major = 100;
        const qreal left = std::floor(rect.left() / minor) * minor;
        const qreal top = std::floor(rect.top() / minor) * minor;
        QVector<QLineF> minorLines;
        QVector<QLineF> majorLines;
        for (qreal x = left; x < rect.right(); x += minor) {
            (static_cast<int>(std::abs(x)) % major == 0 ? majorLines : minorLines).append(QLineF(x, rect.top(), x, rect.bottom()));
        }
        for (qreal y = top; y < rect.bottom(); y += minor) {
            (static_cast<int>(std::abs(y)) % major == 0 ? majorLines : minorLines).append(QLineF(rect.left(), y, rect.right(), y));
        }
        painter->setPen(QPen(QColor(QStringLiteral("#25272b")), 0.0));
        painter->drawLines(minorLines);
        painter->setPen(QPen(QColor(QStringLiteral("#35383d")), 0.0));
        painter->drawLines(majorLines);
    }

    void dragEnterEvent(QDragEnterEvent *event) override
    {
        if (event->mimeData()->hasFormat(GraphNodeMime)) {
            event->acceptProposedAction();
            return;
        }
        QGraphicsView::dragEnterEvent(event);
    }

    void dragMoveEvent(QDragMoveEvent *event) override
    {
        if (event->mimeData()->hasFormat(GraphNodeMime)) {
            event->acceptProposedAction();
            return;
        }
        QGraphicsView::dragMoveEvent(event);
    }

    void dropEvent(QDropEvent *event) override
    {
        if (event->mimeData()->hasFormat(GraphNodeMime) && nodeDropped) {
            nodeDropped(event->mimeData()->data(GraphNodeMime), mapToScene(event->position().toPoint()));
            event->acceptProposedAction();
            return;
        }
        QGraphicsView::dropEvent(event);
    }

    void wheelEvent(QWheelEvent *event) override
    {
        const qreal current = transform().m11();
        const qreal factor = event->angleDelta().y() > 0 ? 1.12 : 1.0 / 1.12;
        if ((factor > 1.0 && current < 2.4) || (factor < 1.0 && current > 0.25)) {
            scale(factor, factor);
        }
        event->accept();
    }

    void keyPressEvent(QKeyEvent *event) override
    {
        if ((event->key() == Qt::Key_Delete || event->key() == Qt::Key_Backspace) && deleteRequested) {
            deleteRequested();
            event->accept();
            return;
        }
        QGraphicsView::keyPressEvent(event);
    }

    void mousePressEvent(QMouseEvent *event) override
    {
        if (event->button() == Qt::MiddleButton) {
            m_panning = true;
            m_panStart = event->position().toPoint();
            viewport()->setCursor(Qt::ClosedHandCursor);
            event->accept();
            return;
        }
        const auto scenePosition = mapToScene(event->position().toPoint());
        auto *node = dynamic_cast<GraphNodeItem *>(itemAt(event->position().toPoint()));
        if (event->button() == Qt::LeftButton && node != nullptr && node->outputHit(scenePosition)) {
            m_wireSource = node;
            m_previewWire = scene()->addPath(QPainterPath(), QPen(QColor(QStringLiteral("#f2b84b")), 2.0, Qt::DashLine));
            m_previewWire->setZValue(0.5);
            updatePreviewWire(scenePosition);
            event->accept();
            return;
        }
        QGraphicsView::mousePressEvent(event);
    }

    void mouseMoveEvent(QMouseEvent *event) override
    {
        if (m_panning) {
            const auto delta = event->position().toPoint() - m_panStart;
            m_panStart = event->position().toPoint();
            horizontalScrollBar()->setValue(horizontalScrollBar()->value() - delta.x());
            verticalScrollBar()->setValue(verticalScrollBar()->value() - delta.y());
            event->accept();
            return;
        }
        if (m_wireSource != nullptr) {
            updatePreviewWire(mapToScene(event->position().toPoint()));
            event->accept();
            return;
        }
        QGraphicsView::mouseMoveEvent(event);
    }

    void mouseReleaseEvent(QMouseEvent *event) override
    {
        if (event->button() == Qt::MiddleButton && m_panning) {
            m_panning = false;
            viewport()->unsetCursor();
            event->accept();
            return;
        }
        if (event->button() == Qt::LeftButton && m_wireSource != nullptr) {
            const auto scenePosition = mapToScene(event->position().toPoint());
            auto *target = dynamic_cast<GraphNodeItem *>(itemAt(event->position().toPoint()));
            if (target != nullptr && target->inputHit(scenePosition) && nodesConnected) {
                nodesConnected(m_wireSource->nodeId(), target->nodeId());
            }
            scene()->removeItem(m_previewWire);
            delete m_previewWire;
            m_previewWire = nullptr;
            m_wireSource = nullptr;
            event->accept();
            return;
        }
        QGraphicsView::mouseReleaseEvent(event);
    }

private:
    void updatePreviewWire(const QPointF &end)
    {
        const auto start = m_wireSource->outputPoint();
        const auto distance = std::max<qreal>(60.0, std::abs(end.x() - start.x()) * 0.5);
        QPainterPath path(start);
        path.cubicTo(start + QPointF(distance, 0.0), end - QPointF(distance, 0.0), end);
        m_previewWire->setPath(path);
    }

    GraphNodeItem *m_wireSource = nullptr;
    QGraphicsPathItem *m_previewWire = nullptr;
    bool m_panning = false;
    QPoint m_panStart;
};

QByteArray palettePayload(const QString &type, const QString &title, const QJsonObject &properties)
{
    return QJsonDocument(QJsonObject{{QStringLiteral("type"), type},
                                     {QStringLiteral("title"), title},
                                     {QStringLiteral("properties"), properties}})
        .toJson(QJsonDocument::Compact);
}
} // namespace

NodeGraphEditor::NodeGraphEditor(QWidget *parent)
    : QWidget(parent)
    , m_palette(new GraphPalette(this))
    , m_scene(new QGraphicsScene(this))
    , m_view(new GraphView(m_scene, this))
    , m_target(new QLineEdit(this))
    , m_selectedType(new QLabel(QStringLiteral("No node selected"), this))
    , m_selectedTitle(new QLineEdit(this))
    , m_properties(new QPlainTextEdit(this))
    , m_apply(new QPushButton(QStringLiteral("Apply node properties"), this))
{
    setObjectName(QStringLiteral("nodeGraphEditor"));
    auto *rootLayout = new QVBoxLayout(this);
    rootLayout->setContentsMargins(0, 0, 0, 0);
    rootLayout->setSpacing(0);

    auto *toolbar = new QWidget(this);
    toolbar->setObjectName(QStringLiteral("graphToolbar"));
    auto *toolbarLayout = new QHBoxLayout(toolbar);
    toolbarLayout->setContentsMargins(12, 7, 12, 7);
    toolbarLayout->setSpacing(7);
    auto addTool = [toolbar, toolbarLayout](const QString &text, const QString &tip) {
        auto *button = new QToolButton(toolbar);
        button->setText(text);
        button->setToolTip(tip);
        button->setObjectName(QStringLiteral("graphToolButton"));
        toolbarLayout->addWidget(button);
        return button;
    };
    auto *validateButton = addTool(QStringLiteral("✓ Validate"), QStringLiteral("Validate graph structure and execution DAG"));
    auto *layoutButton = addTool(QStringLiteral("Auto layout"), QStringLiteral("Arrange nodes in topological order"));
    auto *fitButton = addTool(QStringLiteral("Fit"), QStringLiteral("Fit all nodes in the canvas"));
    auto *deleteButton = addTool(QStringLiteral("Delete"), QStringLiteral("Delete selected nodes or wires"));
    auto *compileButton = addTool(QStringLiteral("Compile preview"), QStringLiteral("Compile supported nodes to a Forge config fragment"));
    toolbarLayout->addStretch();
    auto *hint = new QLabel(QStringLiteral("Drag nodes · pull output → input · wheel zoom · middle-drag pan"), toolbar);
    hint->setObjectName(QStringLiteral("mutedText"));
    toolbarLayout->addWidget(hint);
    rootLayout->addWidget(toolbar);

    auto *splitter = new QSplitter(this);
    splitter->setChildrenCollapsible(false);
    splitter->setHandleWidth(1);
    auto *palettePanel = new QWidget(splitter);
    auto *paletteLayout = new QVBoxLayout(palettePanel);
    paletteLayout->setContentsMargins(12, 12, 12, 12);
    auto *paletteTitle = new QLabel(QStringLiteral("NODE LIBRARY"), palettePanel);
    paletteTitle->setObjectName(QStringLiteral("panelEyebrow"));
    paletteLayout->addWidget(paletteTitle);
    auto *paletteHelp = new QLabel(QStringLiteral("Drag a node onto the grid."), palettePanel);
    paletteHelp->setObjectName(QStringLiteral("mutedText"));
    paletteLayout->addWidget(paletteHelp);
    m_palette->setObjectName(QStringLiteral("graphPalette"));
    m_palette->setDragEnabled(true);
    m_palette->setDragDropMode(QAbstractItemView::DragOnly);
    m_palette->setSpacing(4);
    paletteLayout->addWidget(m_palette, 1);

    auto *inspector = new QWidget(splitter);
    auto *inspectorLayout = new QVBoxLayout(inspector);
    inspectorLayout->setContentsMargins(12, 12, 12, 12);
    auto *inspectorTitle = new QLabel(QStringLiteral("GRAPH INSPECTOR"), inspector);
    inspectorTitle->setObjectName(QStringLiteral("panelEyebrow"));
    inspectorLayout->addWidget(inspectorTitle);
    auto *targetLabel = new QLabel(QStringLiteral("Compiled target"), inspector);
    targetLabel->setObjectName(QStringLiteral("mutedText"));
    inspectorLayout->addWidget(targetLabel);
    m_target->setPlaceholderText(QStringLiteral("config/50-operation.json"));
    inspectorLayout->addWidget(m_target);
    inspectorLayout->addSpacing(12);
    m_selectedType->setObjectName(QStringLiteral("graphNodeType"));
    m_selectedType->setWordWrap(true);
    inspectorLayout->addWidget(m_selectedType);
    m_selectedTitle->setPlaceholderText(QStringLiteral("Node title"));
    inspectorLayout->addWidget(m_selectedTitle);
    auto *propertiesLabel = new QLabel(QStringLiteral("Properties (JSON object)"), inspector);
    propertiesLabel->setObjectName(QStringLiteral("mutedText"));
    inspectorLayout->addWidget(propertiesLabel);
    m_properties->setObjectName(QStringLiteral("graphProperties"));
    m_properties->setPlaceholderText(QStringLiteral("{}"));
    inspectorLayout->addWidget(m_properties, 1);
    m_apply->setObjectName(QStringLiteral("primaryButton"));
    inspectorLayout->addWidget(m_apply);

    splitter->addWidget(palettePanel);
    splitter->addWidget(m_view);
    splitter->addWidget(inspector);
    splitter->setSizes({220, 850, 300});
    rootLayout->addWidget(splitter, 1);

    auto *view = static_cast<GraphView *>(m_view);
    view->nodeDropped = [this](const QByteArray &payload, const QPointF &position) { addNodeFromPayload(payload, position); };
    view->nodesConnected = [this](const QString &source, const QString &target) { connectNodes(source, target); };
    view->deleteRequested = [this] { deleteSelection(); };
    connect(m_scene, &QGraphicsScene::selectionChanged, this, &NodeGraphEditor::showSelection);
    connect(m_apply, &QPushButton::clicked, this, &NodeGraphEditor::applyInspector);
    connect(m_target, &QLineEdit::editingFinished, this, &NodeGraphEditor::applyTarget);
    connect(validateButton, &QToolButton::clicked, this, [this] {
        QString error;
        emit statusMessage(m_model.validate(&error) ? QStringLiteral("Graph is valid and acyclic.") : error);
    });
    connect(layoutButton, &QToolButton::clicked, this, &NodeGraphEditor::autoLayout);
    connect(fitButton, &QToolButton::clicked, this, &NodeGraphEditor::fitGraph);
    connect(deleteButton, &QToolButton::clicked, this, &NodeGraphEditor::deleteSelection);
    connect(compileButton, &QToolButton::clicked, this, &NodeGraphEditor::showCompiledPreview);
    installPalette();
    rebuildScene();
}

void NodeGraphEditor::installPalette()
{
    struct Definition {
        const char *label;
        const char *type;
        QJsonObject properties;
    };
    const QList<Definition> definitions{
        {"Request Input", "request.input",
         QJsonObject{{QStringLiteral("method"), QStringLiteral("POST")},
                     {QStringLiteral("input_schema"),
                      QJsonObject{{QStringLiteral("type"), QStringLiteral("object")},
                                  {QStringLiteral("additionalProperties"), false},
                                  {QStringLiteral("properties"), QJsonObject{}}}}}},
        {"Authorization Policy", "auth.policy",
         QJsonObject{{QStringLiteral("permission"), QStringLiteral("operation.execute")}, {QStringLiteral("public"), false}}},
        {"SQL Query", "data.query",
         QJsonObject{{QStringLiteral("sql"), QStringLiteral("SELECT 1 AS ok")},
                     {QStringLiteral("mode"), QStringLiteral("fetch_all")},
                     {QStringLiteral("params"), QJsonObject{}},
                     {QStringLiteral("result_name"), QStringLiteral("rows")},
                     {QStringLiteral("max_rows"), 1000}}},
        {"SQL Mutation", "data.mutate",
         QJsonObject{{QStringLiteral("sql"), QStringLiteral("UPDATE items SET updated_at = CURRENT_TIMESTAMP WHERE id = :id")},
                     {QStringLiteral("mode"), QStringLiteral("execute")},
                     {QStringLiteral("params"), QJsonObject{{QStringLiteral("id"), QStringLiteral("$body.id")}}},
                     {QStringLiteral("result_name"), QStringLiteral("changed")}}},
        {"Branch / Guard (design)", "logic.branch",
         QJsonObject{{QStringLiteral("expression"), QStringLiteral("$body.enabled == true")},
                     {QStringLiteral("description"), QStringLiteral("Design-time branch; compiler support is policy-specific")}}},
        {"Map / Transform (design)", "transform.map",
         QJsonObject{{QStringLiteral("mapping"), QJsonObject{}},
                     {QStringLiteral("description"), QStringLiteral("Document response mapping intent")}}},
        {"Forge Operation", "operation.call",
         QJsonObject{{QStringLiteral("name"), QStringLiteral("graph.operation")},
                     {QStringLiteral("method"), QStringLiteral("POST")},
                     {QStringLiteral("database"), QStringLiteral("primary")},
                     {QStringLiteral("idempotency"), true},
                     {QStringLiteral("summary"), QStringLiteral("Operation generated from a Forge graph")}}},
        {"Python SDK Call", "python.call",
         QJsonObject{{QStringLiteral("hook"), QStringLiteral("hooks.integration:after_operation")},
                     {QStringLiteral("sdk_mode"), QStringLiteral("async_cluster")}}},
        {"Publish Event (design)", "events.publish",
         QJsonObject{{QStringLiteral("channel"), QStringLiteral("domain-updates")},
                     {QStringLiteral("event"), QStringLiteral("operation.completed")}}},
        {"Response Output", "response.output",
         QJsonObject{{QStringLiteral("status_code"), 200}, {QStringLiteral("shape"), QStringLiteral("operation-results")}}},
    };
    for (const auto &definition : definitions) {
        addPaletteNode(QString::fromLatin1(definition.label), QString::fromLatin1(definition.type), definition.properties);
    }
}

void NodeGraphEditor::addPaletteNode(const QString &label, const QString &type, const QJsonObject &properties)
{
    static const QRegularExpression TypePattern(QStringLiteral(R"(^[a-z][a-z0-9]*(?:[._-][a-z0-9]+){1,7}$)"));
    if (label.trimmed().isEmpty() || label.size() > 160 || !TypePattern.match(type).hasMatch()) {
        emit statusMessage(QStringLiteral("A plugin attempted to register an invalid graph node type."));
        return;
    }
    auto *item = new QListWidgetItem(label, m_palette);
    item->setToolTip(type);
    item->setData(Qt::UserRole, palettePayload(type, label, properties));
}

bool NodeGraphEditor::setDocument(const QJsonObject &document, QString *errorMessage)
{
    if (!m_model.setDocument(document, errorMessage)) {
        return false;
    }
    rebuildScene();
    QTimer::singleShot(0, this, &NodeGraphEditor::fitGraph);
    return true;
}

QJsonObject NodeGraphEditor::document() const
{
    return m_model.document();
}

QJsonObject NodeGraphEditor::starterDocument(const QString &targetDocument)
{
    GraphModel model;
    model.setDocument(GraphModel::emptyDocument(targetDocument));
    const auto request = model.addNode(QStringLiteral("request.input"), QStringLiteral("Request Input"), QPointF(0.0, 0.0),
                                       QJsonObject{{QStringLiteral("method"), QStringLiteral("POST")},
                                                   {QStringLiteral("input_schema"),
                                                    QJsonObject{{QStringLiteral("type"), QStringLiteral("object")},
                                                                {QStringLiteral("additionalProperties"), false},
                                                                {QStringLiteral("properties"), QJsonObject{}}}}});
    const auto policy = model.addNode(QStringLiteral("auth.policy"), QStringLiteral("Authorization Policy"), QPointF(300.0, 0.0),
                                      QJsonObject{{QStringLiteral("permission"), QStringLiteral("operation.execute")},
                                                  {QStringLiteral("public"), false}});
    const auto query = model.addNode(QStringLiteral("data.query"), QStringLiteral("Query Data"), QPointF(600.0, 0.0),
                                     QJsonObject{{QStringLiteral("sql"), QStringLiteral("SELECT 1 AS ok")},
                                                 {QStringLiteral("mode"), QStringLiteral("fetch_one")},
                                                 {QStringLiteral("params"), QJsonObject{}},
                                                 {QStringLiteral("result_name"), QStringLiteral("result")},
                                                 {QStringLiteral("max_rows"), 1}});
    const auto operation = model.addNode(QStringLiteral("operation.call"), QStringLiteral("Forge Operation"), QPointF(900.0, 0.0),
                                         QJsonObject{{QStringLiteral("name"), QStringLiteral("graph.operation")},
                                                     {QStringLiteral("method"), QStringLiteral("POST")},
                                                     {QStringLiteral("database"), QStringLiteral("primary")},
                                                     {QStringLiteral("idempotency"), false},
                                                     {QStringLiteral("summary"), QStringLiteral("Generated from the visual graph")}});
    const auto response = model.addNode(QStringLiteral("response.output"), QStringLiteral("Response"), QPointF(1200.0, 0.0),
                                        QJsonObject{{QStringLiteral("status_code"), 200}});
    QString ignored;
    model.connectNodes(request, QStringLiteral("exec"), policy, QStringLiteral("exec"), &ignored);
    model.connectNodes(policy, QStringLiteral("exec"), query, QStringLiteral("exec"), &ignored);
    model.connectNodes(query, QStringLiteral("exec"), operation, QStringLiteral("exec"), &ignored);
    model.connectNodes(operation, QStringLiteral("exec"), response, QStringLiteral("exec"), &ignored);
    return model.document();
}

void NodeGraphEditor::rebuildScene()
{
    m_updating = true;
    m_scene->clear();
    m_nodeItems.clear();
    m_edgeItems.clear();
    m_target->setText(m_model.document().value(QStringLiteral("target_document")).toString());
    for (const auto &value : m_model.document().value(QStringLiteral("nodes")).toArray()) {
        const auto node = value.toObject();
        const auto id = node.value(QStringLiteral("id")).toString();
        auto *item = new GraphNodeItem(id, node.value(QStringLiteral("type")).toString(),
                                       node.value(QStringLiteral("title")).toString(node.value(QStringLiteral("type")).toString()));
        item->setPos(node.value(QStringLiteral("x")).toDouble(), node.value(QStringLiteral("y")).toDouble());
        item->moved = [this](const QString &nodeId, const QPointF &position) {
            if (m_updating) {
                return;
            }
            if (m_model.moveNode(nodeId, position)) {
                updateConnections();
                notifyChanged();
            }
        };
        m_scene->addItem(item);
        m_nodeItems.insert(id, item);
    }
    for (const auto &value : m_model.document().value(QStringLiteral("edges")).toArray()) {
        const auto edge = value.toObject();
        auto *source = dynamic_cast<GraphNodeItem *>(m_nodeItems.value(edge.value(QStringLiteral("from_node")).toString()));
        auto *target = dynamic_cast<GraphNodeItem *>(m_nodeItems.value(edge.value(QStringLiteral("to_node")).toString()));
        if (source != nullptr && target != nullptr) {
            auto *wire = new GraphEdgeItem(edge.value(QStringLiteral("id")).toString(), source, target);
            m_scene->addItem(wire);
            m_edgeItems.append(wire);
        }
    }
    m_updating = false;
    showSelection();
}

void NodeGraphEditor::updateConnections()
{
    for (auto *item : std::as_const(m_edgeItems)) {
        if (auto *edge = dynamic_cast<GraphEdgeItem *>(item); edge != nullptr) {
            edge->updatePath();
        }
    }
}

void NodeGraphEditor::addNodeFromPayload(const QByteArray &payload, const QPointF &position)
{
    QJsonParseError error;
    const auto parsed = QJsonDocument::fromJson(payload, &error);
    if (error.error != QJsonParseError::NoError || !parsed.isObject()) {
        emit statusMessage(QStringLiteral("Node palette payload is invalid."));
        return;
    }
    const auto object = parsed.object();
    const auto id = m_model.addNode(object.value(QStringLiteral("type")).toString(), object.value(QStringLiteral("title")).toString(),
                                    position, object.value(QStringLiteral("properties")).toObject());
    if (id.isEmpty()) {
        emit statusMessage(QStringLiteral("The node could not be added because its definition violates graph policy."));
        return;
    }
    rebuildScene();
    if (auto *item = m_nodeItems.value(id); item != nullptr) {
        item->setSelected(true);
    }
    notifyChanged();
    emit statusMessage(QStringLiteral("Added %1.").arg(object.value(QStringLiteral("title")).toString()));
}

void NodeGraphEditor::connectNodes(const QString &fromNode, const QString &toNode)
{
    QString error;
    if (!m_model.connectNodes(fromNode, QStringLiteral("exec"), toNode, QStringLiteral("exec"), &error)) {
        emit statusMessage(error);
        return;
    }
    rebuildScene();
    notifyChanged();
    emit statusMessage(QStringLiteral("Connected nodes with an acyclic execution wire."));
}

void NodeGraphEditor::showSelection()
{
    if (m_updating) {
        return;
    }
    GraphNodeItem *selected = nullptr;
    for (auto *item : m_scene->selectedItems()) {
        if (item->type() == NodeItemType) {
            selected = static_cast<GraphNodeItem *>(item);
            break;
        }
    }
    m_updating = true;
    if (selected == nullptr) {
        m_selectedType->setText(QStringLiteral("No node selected"));
        m_selectedTitle->clear();
        m_properties->setPlainText(QStringLiteral("{}"));
        m_selectedTitle->setEnabled(false);
        m_properties->setEnabled(false);
        m_apply->setEnabled(false);
    } else {
        const auto value = m_model.node(selected->nodeId());
        m_selectedType->setText(value.value(QStringLiteral("type")).toString());
        m_selectedType->setProperty("nodeId", selected->nodeId());
        m_selectedTitle->setText(value.value(QStringLiteral("title")).toString());
        m_properties->setPlainText(QString::fromUtf8(DocumentCodec::prettyJson(value.value(QStringLiteral("properties")).toObject())));
        m_selectedTitle->setEnabled(true);
        m_properties->setEnabled(true);
        m_apply->setEnabled(true);
    }
    m_updating = false;
}

void NodeGraphEditor::applyInspector()
{
    const auto id = m_selectedType->property("nodeId").toString();
    if (id.isEmpty()) {
        return;
    }
    QJsonObject properties;
    QString parseError;
    if (!DocumentCodec::parseObject(m_properties->toPlainText().toUtf8(), &properties, &parseError)) {
        QMessageBox::warning(this, QStringLiteral("Invalid node properties"), parseError);
        return;
    }
    QString error;
    if (!m_model.updateNode(id, m_selectedTitle->text().trimmed(), properties, &error)) {
        QMessageBox::warning(this, QStringLiteral("Invalid node"), error);
        return;
    }
    rebuildScene();
    if (auto *item = m_nodeItems.value(id); item != nullptr) {
        item->setSelected(true);
    }
    notifyChanged();
    emit statusMessage(QStringLiteral("Node properties updated."));
}

void NodeGraphEditor::applyTarget()
{
    if (m_updating) {
        return;
    }
    auto candidate = m_model.document();
    candidate.insert(QStringLiteral("target_document"), m_target->text().trimmed());
    QString error;
    if (!m_model.setDocument(candidate, &error)) {
        QMessageBox::warning(this, QStringLiteral("Invalid graph target"), error);
        m_updating = true;
        m_target->setText(m_model.document().value(QStringLiteral("target_document")).toString());
        m_updating = false;
        return;
    }
    notifyChanged();
}

void NodeGraphEditor::deleteSelection()
{
    const auto selected = m_scene->selectedItems();
    if (selected.isEmpty()) {
        return;
    }
    bool changed = false;
    for (auto *item : selected) {
        if (item->type() == NodeItemType) {
            changed = m_model.removeNode(static_cast<GraphNodeItem *>(item)->nodeId()) || changed;
        } else if (item->type() == EdgeItemType) {
            changed = m_model.removeEdge(static_cast<GraphEdgeItem *>(item)->edgeId()) || changed;
        }
    }
    if (changed) {
        rebuildScene();
        notifyChanged();
        emit statusMessage(QStringLiteral("Removed selected graph elements."));
    }
}

void NodeGraphEditor::autoLayout()
{
    QString error;
    const auto order = m_model.topologicalOrder(&error);
    if (order.isEmpty()) {
        emit statusMessage(error.isEmpty() ? QStringLiteral("Add nodes before arranging the graph.") : error);
        return;
    }
    QHash<QString, int> level;
    QHash<QString, QStringList> successors;
    for (const auto &value : m_model.document().value(QStringLiteral("edges")).toArray()) {
        const auto edge = value.toObject();
        successors[edge.value(QStringLiteral("from_node")).toString()].append(edge.value(QStringLiteral("to_node")).toString());
    }
    for (const auto &id : order) {
        for (const auto &target : successors.value(id)) {
            level[target] = std::max(level.value(target), level.value(id) + 1);
        }
    }
    QHash<int, int> rows;
    m_updating = true;
    for (const auto &id : order) {
        const auto column = level.value(id);
        const auto row = rows[column]++;
        m_model.moveNode(id, QPointF(column * 300.0, row * 170.0));
    }
    m_updating = false;
    rebuildScene();
    fitGraph();
    notifyChanged();
    emit statusMessage(QStringLiteral("Graph arranged by dependency level."));
}

void NodeGraphEditor::showCompiledPreview()
{
    QString error;
    const auto fragment = m_model.compiledFragment(&error);
    if (fragment.isEmpty()) {
        QMessageBox::warning(this, QStringLiteral("Graph cannot compile"), error);
        return;
    }
    QDialog dialog(this);
    dialog.setWindowTitle(QStringLiteral("Compiled Forge fragment preview"));
    dialog.resize(760, 620);
    auto *layout = new QVBoxLayout(&dialog);
    auto *message = new QLabel(QStringLiteral("Preview only. Save this output to the graph's target document after review."), &dialog);
    message->setObjectName(QStringLiteral("warningCard"));
    message->setWordWrap(true);
    layout->addWidget(message);
    auto *editor = new QPlainTextEdit(&dialog);
    editor->setReadOnly(true);
    editor->setPlainText(QString::fromUtf8(DocumentCodec::prettyJson(fragment)));
    layout->addWidget(editor, 1);
    auto *buttons = new QHBoxLayout;
    auto *copy = new QPushButton(QStringLiteral("Copy JSON"), &dialog);
    auto *close = new QPushButton(QStringLiteral("Close"), &dialog);
    buttons->addStretch();
    buttons->addWidget(copy);
    buttons->addWidget(close);
    layout->addLayout(buttons);
    connect(copy, &QPushButton::clicked, &dialog, [editor] { QApplication::clipboard()->setText(editor->toPlainText()); });
    connect(close, &QPushButton::clicked, &dialog, &QDialog::accept);
    dialog.exec();
}

void NodeGraphEditor::fitGraph()
{
    auto *view = static_cast<GraphView *>(m_view);
    const auto bounds = m_scene->itemsBoundingRect();
    if (!bounds.isEmpty()) {
        view->fitInView(bounds.adjusted(-80.0, -80.0, 80.0, 80.0), Qt::KeepAspectRatio);
    }
}

void NodeGraphEditor::notifyChanged()
{
    if (!m_updating) {
        emit documentChanged(m_model.document());
    }
}
