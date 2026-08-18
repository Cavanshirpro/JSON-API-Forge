#include "MainWindow.hpp"

#include "CodeEditor.hpp"
#include "ConnectionDialog.hpp"
#include "DocumentCodec.hpp"
#include "JsonHighlighter.hpp"
#include "VisualDesigner.hpp"

#include <QAction>
#include <QApplication>
#include <QCloseEvent>
#include <QDialog>
#include <QDialogButtonBox>
#include <QDir>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QFontDatabase>
#include <QFormLayout>
#include <QGraphicsOpacityEffect>
#include <QHeaderView>
#include <QHBoxLayout>
#include <QInputDialog>
#include <QJsonArray>
#include <QJsonDocument>
#include <QIcon>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QMenuBar>
#include <QMessageBox>
#include <QProgressBar>
#include <QPropertyAnimation>
#include <QPixmap>
#include <QPushButton>
#include <QSettings>
#include <QShortcut>
#include <QSplitter>
#include <QStackedWidget>
#include <QStandardPaths>
#include <QStatusBar>
#include <QStyle>
#include <QRegularExpression>
#include <QTextStream>
#include <QToolBar>
#include <QToolButton>
#include <QTreeWidget>
#include <QVBoxLayout>

namespace {
constexpr auto ProjectPathRole = Qt::UserRole + 1;
constexpr auto ProjectSourceRole = Qt::UserRole + 2;
constexpr auto DocumentPathRole = Qt::UserRole + 3;
constexpr int LocalSource = 1;
constexpr int RemoteSource = 2;

QLabel *eyebrow(const QString &text, QWidget *parent)
{
    auto *label = new QLabel(text, parent);
    label->setObjectName(QStringLiteral("panelEyebrow"));
    return label;
}

QString currentModeName(bool remote)
{
    return remote ? QStringLiteral("REMOTE") : QStringLiteral("LOCAL");
}
} // namespace

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
    , m_api(new ApiClient(this))
{
    QCoreApplication::setOrganizationName(QStringLiteral("Cavanshirpro"));
    QCoreApplication::setApplicationName(QStringLiteral("JSON API Forge Editor"));
    QCoreApplication::setApplicationVersion(QStringLiteral("0.4.2"));
    setWindowTitle(QStringLiteral("JSON API Forge Editor"));
    setWindowIcon(QIcon(QStringLiteral(":/branding/logo.png")));
    resize(1480, 900);
    setMinimumSize(1040, 680);
    buildInterface();
    buildActions();
    applyStyle();
    showWelcome();

    const QStringList pluginDirectories{
        QDir(QCoreApplication::applicationDirPath()).filePath(QStringLiteral("plugins")),
        QDir(QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation)).filePath(QStringLiteral("plugins")),
    };
    m_pluginManager = new PluginManager(pluginDirectories);
    reloadPlugins();

    connect(m_api, &ApiClient::jsonReceived, this, &MainWindow::handleApiJson);
    connect(m_api, &ApiClient::requestFailed, this, &MainWindow::handleApiError);
    connect(m_api, &ApiClient::connectionActivityChanged, this, [this](bool active) { m_activity->setVisible(active); });
    connect(m_api, &ApiClient::tlsRejected, this, [this](const QString &message) {
        QMessageBox::critical(this, QStringLiteral("TLS validation failed"),
                              QStringLiteral("The connection was aborted. Certificate errors are never ignored.\n\n%1").arg(message));
    });
    connect(m_codeEditor, &QPlainTextEdit::textChanged, this, [this] {
        if (!m_updatingEditor && !m_currentDocument.isEmpty()) {
            setDirty(true);
        }
    });
    connect(m_visualDesigner, &VisualDesigner::documentChanged, this, [this] { setDirty(true); });
    connect(m_visualDesigner, &VisualDesigner::statusMessage, this,
            [this](const QString &message) { showStatusMessage(message); });
}

MainWindow::~MainWindow()
{
    if (m_pluginManager != nullptr) {
        m_pluginManager->unloadAll();
        delete m_pluginManager;
    }
}

void MainWindow::buildInterface()
{
    auto *root = new QSplitter(this);
    root->setObjectName(QStringLiteral("rootSplitter"));
    root->setHandleWidth(1);
    root->setChildrenCollapsible(false);
    setCentralWidget(root);

    m_sidebar = new QWidget(root);
    m_sidebar->setObjectName(QStringLiteral("sidebar"));
    m_sidebar->setMinimumWidth(250);
    m_sidebar->setMaximumWidth(340);
    auto *sideLayout = new QVBoxLayout(m_sidebar);
    sideLayout->setContentsMargins(18, 20, 18, 16);
    sideLayout->setSpacing(12);
    auto *brandRow = new QWidget(m_sidebar);
    auto *brandLayout = new QHBoxLayout(brandRow);
    brandLayout->setContentsMargins(0, 0, 0, 0);
    auto *logo = new QLabel(brandRow);
    logo->setPixmap(QPixmap(QStringLiteral(":/branding/logo.png")).scaled(48, 48, Qt::KeepAspectRatio, Qt::SmoothTransformation));
    auto *brandText = new QLabel(QStringLiteral("JSON API\nFORGE"), brandRow);
    brandText->setObjectName(QStringLiteral("brandText"));
    brandLayout->addWidget(logo);
    brandLayout->addWidget(brandText);
    brandLayout->addStretch();
    sideLayout->addWidget(brandRow);

    m_connectionLabel = new QLabel(QStringLiteral("●  Not connected"), m_sidebar);
    m_connectionLabel->setObjectName(QStringLiteral("connectionOffline"));
    sideLayout->addWidget(m_connectionLabel);
    sideLayout->addWidget(eyebrow(QStringLiteral("PROJECTS"), m_sidebar));
    m_projects = new QListWidget(m_sidebar);
    m_projects->setObjectName(QStringLiteral("projectList"));
    m_projects->setSpacing(3);
    sideLayout->addWidget(m_projects, 2);
    sideLayout->addWidget(eyebrow(QStringLiteral("DOCUMENTS"), m_sidebar));
    m_documents = new QTreeWidget(m_sidebar);
    m_documents->setObjectName(QStringLiteral("documentTree"));
    m_documents->setHeaderHidden(true);
    m_documents->setRootIsDecorated(true);
    sideLayout->addWidget(m_documents, 3);
    sideLayout->addWidget(eyebrow(QStringLiteral("SERVER POLICY"), m_sidebar));
    m_policyLabel = new QLabel(QStringLiteral("Connect to discover server-enforced capabilities."), m_sidebar);
    m_policyLabel->setObjectName(QStringLiteral("policyCard"));
    m_policyLabel->setWordWrap(true);
    sideLayout->addWidget(m_policyLabel);

    auto *content = new QWidget(root);
    content->setObjectName(QStringLiteral("contentArea"));
    auto *contentLayout = new QVBoxLayout(content);
    contentLayout->setContentsMargins(0, 0, 0, 0);
    contentLayout->setSpacing(0);
    auto *header = new QWidget(content);
    header->setObjectName(QStringLiteral("workspaceHeader"));
    auto *headerLayout = new QHBoxLayout(header);
    headerLayout->setContentsMargins(22, 12, 18, 12);
    auto *sidebarButton = new QToolButton(header);
    sidebarButton->setText(QStringLiteral("☰"));
    sidebarButton->setToolTip(QStringLiteral("Toggle sidebar (Ctrl+\\)"));
    sidebarButton->setObjectName(QStringLiteral("iconButton"));
    connect(sidebarButton, &QToolButton::clicked, this, &MainWindow::toggleSidebar);
    headerLayout->addWidget(sidebarButton);
    m_breadcrumb = new QLabel(QStringLiteral("No document open"), header);
    m_breadcrumb->setObjectName(QStringLiteral("breadcrumb"));
    headerLayout->addWidget(m_breadcrumb, 1);
    m_activity = new QProgressBar(header);
    m_activity->setRange(0, 0);
    m_activity->setFixedSize(72, 6);
    m_activity->setTextVisible(false);
    m_activity->hide();
    headerLayout->addWidget(m_activity);
    m_codeButton = new QToolButton(header);
    m_codeButton->setText(QStringLiteral("Code"));
    m_codeButton->setCheckable(true);
    m_codeButton->setEnabled(false);
    m_codeButton->setObjectName(QStringLiteral("modeButton"));
    m_visualButton = new QToolButton(header);
    m_visualButton->setText(QStringLiteral("Visual"));
    m_visualButton->setCheckable(true);
    m_visualButton->setEnabled(false);
    m_visualButton->setObjectName(QStringLiteral("modeButton"));
    connect(m_codeButton, &QToolButton::clicked, this, &MainWindow::showCodeMode);
    connect(m_visualButton, &QToolButton::clicked, this, &MainWindow::showVisualMode);
    headerLayout->addWidget(m_codeButton);
    headerLayout->addWidget(m_visualButton);
    contentLayout->addWidget(header);

    m_workspace = new QStackedWidget(content);
    m_workspace->setObjectName(QStringLiteral("workspaceStack"));
    m_welcomePage = new QWidget(m_workspace);
    m_welcomePage->setObjectName(QStringLiteral("welcomePage"));
    auto *welcomeLayout = new QVBoxLayout(m_welcomePage);
    welcomeLayout->setContentsMargins(60, 40, 60, 50);
    welcomeLayout->setAlignment(Qt::AlignCenter);
    welcomeLayout->setSpacing(14);
    auto *welcomeLogo = new QLabel(m_welcomePage);
    welcomeLogo->setObjectName(QStringLiteral("welcomeLogo"));
    welcomeLogo->setPixmap(QPixmap(QStringLiteral(":/branding/logo.png")).scaled(
        180, 180, Qt::KeepAspectRatio, Qt::SmoothTransformation));
    welcomeLogo->setAlignment(Qt::AlignCenter);
    auto *welcomeBadge = new QLabel(QStringLiteral("POLICY-AWARE  ·  LOCAL OR REMOTE"), m_welcomePage);
    welcomeBadge->setObjectName(QStringLiteral("welcomeBadge"));
    welcomeBadge->setAlignment(Qt::AlignCenter);
    auto *welcomeTitle = new QLabel(QStringLiteral("Design APIs without losing the code."), m_welcomePage);
    welcomeTitle->setObjectName(QStringLiteral("welcomeTitle"));
    welcomeTitle->setAlignment(Qt::AlignCenter);
    auto *welcomeText = new QLabel(
        QStringLiteral("Edit validated JSON directly, or shape resources and operations visually.\n"
                       "Server capabilities always decide what can be created or changed."),
        m_welcomePage);
    welcomeText->setObjectName(QStringLiteral("welcomeText"));
    welcomeText->setAlignment(Qt::AlignCenter);
    auto *welcomeButtons = new QWidget(m_welcomePage);
    auto *welcomeButtonLayout = new QHBoxLayout(welcomeButtons);
    welcomeButtonLayout->setContentsMargins(0, 8, 0, 0);
    welcomeButtonLayout->setSpacing(10);
    auto *openWorkspaceButton = new QPushButton(QStringLiteral("Open workspace"), welcomeButtons);
    openWorkspaceButton->setObjectName(QStringLiteral("primaryButton"));
    auto *connectServerButton = new QPushButton(QStringLiteral("Connect to server"), welcomeButtons);
    welcomeButtonLayout->addWidget(openWorkspaceButton);
    welcomeButtonLayout->addWidget(connectServerButton);
    connect(openWorkspaceButton, &QPushButton::clicked, this, &MainWindow::openLocalWorkspace);
    connect(connectServerButton, &QPushButton::clicked, this, &MainWindow::connectToServer);
    welcomeLayout->addWidget(welcomeLogo, 0, Qt::AlignCenter);
    welcomeLayout->addWidget(welcomeBadge);
    welcomeLayout->addWidget(welcomeTitle);
    welcomeLayout->addWidget(welcomeText);
    welcomeLayout->addWidget(welcomeButtons, 0, Qt::AlignCenter);
    m_codeEditor = new CodeEditor(m_workspace);
    auto font = QFontDatabase::systemFont(QFontDatabase::FixedFont);
    font.setPointSize(11);
    m_codeEditor->setFont(font);
    new JsonHighlighter(m_codeEditor->document());
    m_codeEditor->setPlaceholderText(QStringLiteral("Open app.json or a configuration fragment to begin."));
    m_visualDesigner = new VisualDesigner(m_workspace);
    m_workspace->addWidget(m_welcomePage);
    m_workspace->addWidget(m_codeEditor);
    m_workspace->addWidget(m_visualDesigner);
    contentLayout->addWidget(m_workspace, 1);
    root->addWidget(m_sidebar);
    root->addWidget(content);
    root->setSizes({290, 1190});

    m_pluginToolBar = addToolBar(QStringLiteral("Plugin tools"));
    m_pluginToolBar->setObjectName(QStringLiteral("pluginToolBar"));
    m_pluginToolBar->setMovable(false);
    m_pluginToolBar->hide();
    statusBar()->setObjectName(QStringLiteral("statusBar"));
    statusBar()->showMessage(QStringLiteral("Ready"));

    connect(m_projects, &QListWidget::itemSelectionChanged, this, &MainWindow::selectProject);
    connect(m_documents, &QTreeWidget::itemDoubleClicked, this, &MainWindow::openSelectedDocument);
}

void MainWindow::buildActions()
{
    auto *fileMenu = menuBar()->addMenu(QStringLiteral("&File"));
    auto *connectAction = fileMenu->addAction(QStringLiteral("Connect to server…"), this, &MainWindow::connectToServer);
    connectAction->setShortcut(QKeySequence(QStringLiteral("Ctrl+Shift+C")));
    auto *openAction = fileMenu->addAction(QStringLiteral("Open local workspace…"), this, &MainWindow::openLocalWorkspace);
    openAction->setShortcut(QKeySequence::Open);
    fileMenu->addSeparator();
    m_saveAction = fileMenu->addAction(QStringLiteral("Save"), this, &MainWindow::saveDocument);
    m_saveAction->setShortcut(QKeySequence::Save);
    m_saveAction->setEnabled(false);
    m_validateAction = fileMenu->addAction(QStringLiteral("Validate project"), this, &MainWindow::validateProject);
    m_validateAction->setShortcut(QKeySequence(QStringLiteral("Ctrl+Shift+V")));
    m_validateAction->setEnabled(false);
    m_createAction = fileMenu->addAction(QStringLiteral("Create project…"), this, &MainWindow::createProject);
    m_createAction->setShortcut(QKeySequence(QStringLiteral("Ctrl+Shift+N")));
    fileMenu->addSeparator();
    fileMenu->addAction(QStringLiteral("Disconnect"), this, &MainWindow::disconnectServer);
    auto *quitAction = fileMenu->addAction(QStringLiteral("Quit"), qApp, &QApplication::quit);
    quitAction->setShortcut(QKeySequence::Quit);

    auto *viewMenu = menuBar()->addMenu(QStringLiteral("&View"));
    auto *codeAction = viewMenu->addAction(QStringLiteral("Code mode"), this, &MainWindow::showCodeMode);
    codeAction->setShortcut(QKeySequence(QStringLiteral("Ctrl+1")));
    auto *visualAction = viewMenu->addAction(QStringLiteral("Visual mode"), this, &MainWindow::showVisualMode);
    visualAction->setShortcut(QKeySequence(QStringLiteral("Ctrl+2")));
    auto *sidebarAction = viewMenu->addAction(QStringLiteral("Toggle sidebar"), this, &MainWindow::toggleSidebar);
    sidebarAction->setShortcut(QKeySequence(QStringLiteral("Ctrl+\\")));

    auto *pluginMenu = menuBar()->addMenu(QStringLiteral("&Plugins"));
    pluginMenu->addAction(QStringLiteral("Manage plugins…"), this, &MainWindow::managePlugins);
    pluginMenu->addAction(QStringLiteral("Reload approved plugins"), this, &MainWindow::reloadPlugins);

    auto *helpMenu = menuBar()->addMenu(QStringLiteral("&Help"));
    helpMenu->addAction(QStringLiteral("About JSON API Forge Editor"), this, &MainWindow::showAbout);
}

void MainWindow::applyStyle()
{
    QFile style(QStringLiteral(":/styles/dark.qss"));
    if (style.open(QIODevice::ReadOnly)) {
        qApp->setStyleSheet(QString::fromUtf8(style.readAll()));
    }
}

void MainWindow::connectToServer()
{
    if (!confirmDiscard()) {
        return;
    }
    QSettings settings;
    ConnectionDialog dialog(QUrl(settings.value(QStringLiteral("connection/lastServer")).toString()), this);
    if (dialog.exec() != QDialog::Accepted) {
        return;
    }
    QString error;
    if (!m_api->configure(dialog.serverUrl(), dialog.token(), dialog.allowInsecureHttp(), &error)) {
        QMessageBox::warning(this, QStringLiteral("Cannot connect"), error);
        return;
    }
    settings.setValue(QStringLiteral("connection/lastServer"), dialog.serverUrl().toString());
    m_remoteMode = true;
    m_workspaceRoot.clear();
    m_currentProject.clear();
    m_currentDocument.clear();
    m_projects->clear();
    m_documents->clear();
    showWelcome();
    m_connectionLabel->setText(QStringLiteral("●  Connecting…"));
    m_connectionLabel->setObjectName(QStringLiteral("connectionPending"));
    m_connectionLabel->style()->unpolish(m_connectionLabel);
    m_connectionLabel->style()->polish(m_connectionLabel);
    m_api->fetchCapabilities();
}

void MainWindow::disconnectServer()
{
    if (!confirmDiscard()) {
        return;
    }
    m_api->clearCredentials();
    m_remoteMode = false;
    m_projects->clear();
    m_documents->clear();
    m_currentProject.clear();
    m_currentProjectPath.clear();
    m_currentDocument.clear();
    m_currentSha256.clear();
    m_codeEditor->clear();
    m_connectionLabel->setText(QStringLiteral("●  Not connected"));
    m_connectionLabel->setObjectName(QStringLiteral("connectionOffline"));
    m_policyReadOnly = true;
    m_policyCreate = false;
    m_policyHooks = false;
    m_policyMaxBytes = 0;
    updatePolicyPanel();
    setDirty(false);
    showWelcome();
}

void MainWindow::openLocalWorkspace()
{
    if (!confirmDiscard()) {
        return;
    }
    const auto selected = QFileDialog::getExistingDirectory(this, QStringLiteral("Open Forge workspace"), m_workspaceRoot);
    if (selected.isEmpty()) {
        return;
    }
    m_api->clearCredentials();
    m_remoteMode = false;
    populateLocalProjects(selected);
}

void MainWindow::populateLocalProjects(const QString &rootPath)
{
    m_projects->clear();
    m_documents->clear();
    QDir selected(rootPath);
    QDir apps = selected;
    if (QFileInfo(selected.filePath(QStringLiteral("app.json"))).isFile()) {
        apps = QDir(QFileInfo(selected.absolutePath()).absolutePath());
    } else if (QDir(selected.filePath(QStringLiteral("app"))).exists()) {
        apps = QDir(selected.filePath(QStringLiteral("app")));
    }
    m_workspaceRoot = apps.absolutePath();
    const auto projects = apps.entryInfoList(QDir::Dirs | QDir::NoDotAndDotDot | QDir::Readable, QDir::Name);
    for (const auto &project : projects) {
        if (!QFileInfo(QDir(project.absoluteFilePath()).filePath(QStringLiteral("app.json"))).isFile() || project.isSymLink()) {
            continue;
        }
        auto *item = new QListWidgetItem(project.fileName(), m_projects);
        item->setData(ProjectPathRole, project.absoluteFilePath());
        item->setData(ProjectSourceRole, LocalSource);
    }
    if (QFileInfo(apps.filePath(QStringLiteral("app.json"))).isFile()) {
        auto *item = new QListWidgetItem(QFileInfo(apps.absolutePath()).fileName(), m_projects);
        item->setData(ProjectPathRole, apps.absolutePath());
        item->setData(ProjectSourceRole, LocalSource);
    }
    m_connectionLabel->setText(QStringLiteral("●  Local workspace"));
    m_connectionLabel->setObjectName(QStringLiteral("connectionLocal"));
    m_policyReadOnly = false;
    m_policyCreate = true;
    m_policyHooks = true;
    m_policyMaxBytes = 0;
    updatePolicyPanel();
    m_createAction->setEnabled(true);
    if (m_projects->count() > 0) {
        m_projects->setCurrentRow(0);
    } else {
        showStatusMessage(QStringLiteral("No app.json projects found. Use File → Create project."), 6000);
    }
}

void MainWindow::selectProject()
{
    if (!confirmDiscard()) {
        return;
    }
    auto *item = m_projects->currentItem();
    if (item == nullptr) {
        return;
    }
    m_currentProject = item->text();
    m_currentProjectPath = item->data(ProjectPathRole).toString();
    m_documents->clear();
    m_currentDocument.clear();
    showWelcome();
    m_saveAction->setEnabled(false);
    m_validateAction->setEnabled(true);
    if (item->data(ProjectSourceRole).toInt() == RemoteSource) {
        m_api->fetchDocuments(m_currentProject);
    } else {
        populateLocalDocuments(m_currentProjectPath);
    }
}

void MainWindow::populateLocalDocuments(const QString &projectPath)
{
    m_documents->clear();
    auto add = [this](QTreeWidgetItem *parent, const QString &relative) {
        auto *item = new QTreeWidgetItem(parent, {QFileInfo(relative).fileName()});
        item->setData(0, DocumentPathRole, relative);
        return item;
    };
    auto *root = new QTreeWidgetItem(m_documents, {QStringLiteral("Project")});
    add(root, QStringLiteral("app.json"));
    auto *config = new QTreeWidgetItem(m_documents, {QStringLiteral("Config fragments")});
    const QDir configDir(QDir(projectPath).filePath(QStringLiteral("config")));
    for (const auto &file : configDir.entryList({QStringLiteral("*.json")}, QDir::Files | QDir::Readable, QDir::Name)) {
        add(config, QStringLiteral("config/%1").arg(file));
    }
    auto *hooks = new QTreeWidgetItem(m_documents, {QStringLiteral("Python hooks")});
    const QDir hooksDir(QDir(projectPath).filePath(QStringLiteral("hooks")));
    for (const auto &file : hooksDir.entryList({QStringLiteral("*.py")}, QDir::Files | QDir::Readable, QDir::Name)) {
        add(hooks, QStringLiteral("hooks/%1").arg(file));
    }
    root->setExpanded(true);
    config->setExpanded(true);
    hooks->setExpanded(true);
}

void MainWindow::openSelectedDocument()
{
    if (!confirmDiscard()) {
        return;
    }
    auto *item = m_documents->currentItem();
    if (item == nullptr) {
        return;
    }
    const auto relative = item->data(0, DocumentPathRole).toString();
    if (relative.isEmpty()) {
        return;
    }
    if (m_remoteMode) {
        m_api->fetchDocument(m_currentProject, relative);
        return;
    }
    QFile file(QDir(m_currentProjectPath).filePath(relative));
    if (!file.open(QIODevice::ReadOnly)) {
        QMessageBox::warning(this, QStringLiteral("Cannot open document"), file.errorString());
        return;
    }
    const auto bytes = file.readAll();
    loadDocument(relative, bytes, DocumentCodec::sha256(bytes));
}

void MainWindow::loadDocument(const QString &path, const QByteArray &content, const QString &sha256)
{
    m_currentDocument = path;
    m_currentSha256 = sha256;
    m_updatingEditor = true;
    m_codeEditor->setPlainText(QString::fromUtf8(content));
    m_codeEditor->document()->setModified(false);
    m_updatingEditor = false;
    m_breadcrumb->setText(QStringLiteral("%1  /  %2  ·  %3").arg(currentModeName(m_remoteMode), m_currentProject, path));
    const bool jsonDocument = path.endsWith(QStringLiteral(".json"), Qt::CaseSensitive);
    m_codeButton->setEnabled(true);
    m_visualButton->setEnabled(jsonDocument);
    m_saveAction->setEnabled(!m_remoteMode || !m_policyReadOnly);
    setDirty(false);
    showCodeMode();
}

bool MainWindow::prepareCurrentJson(QJsonObject *object, QByteArray *bytes)
{
    if (m_currentDocument.isEmpty()) {
        return false;
    }
    QByteArray current;
    if (m_workspace->currentWidget() == m_visualDesigner && m_currentDocument.endsWith(QStringLiteral(".json"))) {
        current = DocumentCodec::prettyJson(m_visualDesigner->document());
    } else {
        current = m_codeEditor->toPlainText().toUtf8();
    }
    if (m_currentDocument.endsWith(QStringLiteral(".json"))) {
        QString error;
        QJsonObject parsed;
        if (!DocumentCodec::parseObject(current, &parsed, &error)) {
            QMessageBox::warning(this, QStringLiteral("Invalid JSON"), error);
            return false;
        }
        if (object != nullptr) {
            *object = parsed;
        }
    }
    if (bytes != nullptr) {
        *bytes = current;
    }
    return true;
}

void MainWindow::saveDocument()
{
    QByteArray bytes;
    if (!prepareCurrentJson(nullptr, &bytes)) {
        return;
    }
    if (m_remoteMode) {
        if (m_policyReadOnly) {
            QMessageBox::information(this, QStringLiteral("Read-only policy"), QStringLiteral("This server does not permit editor writes."));
            return;
        }
        if (m_currentDocument.startsWith(QStringLiteral("hooks/")) && !m_policyHooks) {
            QMessageBox::warning(this, QStringLiteral("Hook policy"), QStringLiteral("Remote Python hook editing is disabled by the server."));
            return;
        }
        m_api->saveDocument(m_currentProject, m_currentDocument, bytes, m_currentSha256);
        return;
    }
    if (!DocumentCodec::isSafeDocumentPath(m_currentDocument, true)) {
        QMessageBox::critical(this, QStringLiteral("Unsafe path"), QStringLiteral("The selected file is outside the editor document policy."));
        return;
    }
    const auto target = QDir(m_currentProjectPath).filePath(m_currentDocument);
    QString error;
    if (!DocumentCodec::saveAtomically(target, bytes, &error)) {
        QMessageBox::critical(this, QStringLiteral("Save failed"), error);
        return;
    }
    m_currentSha256 = DocumentCodec::sha256(bytes);
    setDirty(false);
    showStatusMessage(QStringLiteral("Saved and fsync-committed %1").arg(m_currentDocument));
}

void MainWindow::validateProject()
{
    if (m_currentProject.isEmpty()) {
        return;
    }
    if (m_remoteMode) {
        m_api->validateProject(m_currentProject);
        return;
    }
    bool valid = true;
    QStringList errors;
    const QDir project(m_currentProjectPath);
    QStringList paths{QStringLiteral("app.json")};
    const QDir config(project.filePath(QStringLiteral("config")));
    for (const auto &name : config.entryList({QStringLiteral("*.json")}, QDir::Files, QDir::Name)) {
        paths.append(QStringLiteral("config/%1").arg(name));
    }
    for (const auto &path : paths) {
        QFile file(project.filePath(path));
        QJsonObject object;
        QString error;
        if (!file.open(QIODevice::ReadOnly) || !DocumentCodec::parseObject(file.readAll(), &object, &error)) {
            valid = false;
            errors.append(QStringLiteral("%1: %2").arg(path, file.isOpen() ? error : file.errorString()));
        }
    }
    if (valid) {
        QMessageBox::information(this, QStringLiteral("Local JSON check"),
                                 QStringLiteral("All project JSON files are syntactically valid objects. Run `forge validate` for full merged schema validation."));
    } else {
        QMessageBox::warning(this, QStringLiteral("Validation failed"), errors.join(u'\n'));
    }
}

void MainWindow::createProject()
{
    bool ok = false;
    const auto name = QInputDialog::getText(this, QStringLiteral("Create project"), QStringLiteral("Directory/name"), QLineEdit::Normal,
                                            QString(), &ok)
                          .trimmed();
    if (!ok || name.isEmpty()) {
        return;
    }
    const auto suggestedSlug = QString(name).toLower().replace(QRegularExpression(QStringLiteral("[^a-z0-9]+")), QStringLiteral("-"))
                                   .remove(QRegularExpression(QStringLiteral("^-|-$")));
    const auto slug = QInputDialog::getText(this, QStringLiteral("Create project"), QStringLiteral("Slug"), QLineEdit::Normal,
                                            suggestedSlug, &ok)
                          .trimmed();
    if (!ok || slug.isEmpty()) {
        return;
    }
    if (m_remoteMode) {
        if (!m_policyCreate || m_policyReadOnly) {
            QMessageBox::warning(this, QStringLiteral("Server policy"), QStringLiteral("Remote project creation is disabled."));
            return;
        }
        m_api->createProject(name, slug);
        return;
    }
    if (m_workspaceRoot.isEmpty() || name.contains(u'/') || name.contains(u'\\') || name == QStringLiteral(".")
        || name == QStringLiteral("..")) {
        QMessageBox::warning(this, QStringLiteral("Invalid project"), QStringLiteral("Choose a local workspace and a safe directory name."));
        return;
    }
    const QDir apps(m_workspaceRoot);
    const auto target = apps.filePath(name);
    if (QFileInfo::exists(target) || !QDir().mkpath(QDir(target).filePath(QStringLiteral("config")))) {
        QMessageBox::warning(this, QStringLiteral("Create failed"), QStringLiteral("The target exists or could not be created."));
        return;
    }
    QDir().mkpath(QDir(target).filePath(QStringLiteral("hooks")));
    const QJsonObject manifest{{QStringLiteral("$schema"), QStringLiteral("../../schemas/manifest.schema.json")},
                               {QStringLiteral("slug"), slug},
                               {QStringLiteral("name"), name},
                               {QStringLiteral("version"), QStringLiteral("1.0.0")},
                               {QStringLiteral("api_prefix"), QStringLiteral("/api/%1/v1").arg(slug)}};
    const QJsonObject databases{
        {QStringLiteral("$schema"), QStringLiteral("../../../schemas/fragment.schema.json")},
        {QStringLiteral("databases"),
         QJsonObject{{QStringLiteral("primary"),
                      QJsonObject{{QStringLiteral("url"),
                                   QStringLiteral("$env:%1_DATABASE_URL:-sqlite+aiosqlite:///./data/%2.db")
                                       .arg(QString(slug).toUpper().replace(u'-', u'_'), slug)}}}}}};
    QString error;
    if (!DocumentCodec::saveAtomically(QDir(target).filePath(QStringLiteral("app.json")), DocumentCodec::prettyJson(manifest), &error)
        || !DocumentCodec::saveAtomically(QDir(target).filePath(QStringLiteral("config/10-databases.json")),
                                          DocumentCodec::prettyJson(databases), &error)) {
        QMessageBox::critical(this, QStringLiteral("Create failed"), error);
        return;
    }
    populateLocalProjects(m_workspaceRoot);
    showStatusMessage(QStringLiteral("Created %1. Full schema validation remains available through the server/CLI.").arg(name), 6000);
}

void MainWindow::showCodeMode()
{
    if (m_currentDocument.isEmpty()) {
        showWelcome();
        return;
    }
    if (m_workspace->currentWidget() == m_visualDesigner && m_visualButton->isEnabled()) {
        m_updatingEditor = true;
        m_codeEditor->setPlainText(QString::fromUtf8(DocumentCodec::prettyJson(m_visualDesigner->document())));
        m_updatingEditor = false;
    }
    m_workspace->setCurrentWidget(m_codeEditor);
    m_codeButton->setChecked(true);
    m_visualButton->setChecked(false);
    animateWorkspace(m_codeEditor);
}

void MainWindow::showWelcome()
{
    m_currentDocument.clear();
    m_currentSha256.clear();
    m_saveAction->setEnabled(false);
    m_codeButton->setChecked(false);
    m_codeButton->setEnabled(false);
    m_visualButton->setChecked(false);
    m_visualButton->setEnabled(false);
    m_breadcrumb->setText(m_currentProject.isEmpty()
                              ? QStringLiteral("Choose a workspace or connect to a Forge server")
                              : QStringLiteral("%1  /  %2  ·  Choose a document")
                                    .arg(currentModeName(m_remoteMode), m_currentProject));
    m_workspace->setCurrentWidget(m_welcomePage);
}

void MainWindow::showVisualMode()
{
    if (!m_visualButton->isEnabled()) {
        return;
    }
    QJsonObject object;
    QString error;
    if (!DocumentCodec::parseObject(m_codeEditor->toPlainText().toUtf8(), &object, &error)) {
        QMessageBox::warning(this, QStringLiteral("Cannot open visual mode"), error);
        return;
    }
    m_visualDesigner->setDocument(object);
    m_workspace->setCurrentWidget(m_visualDesigner);
    m_codeButton->setChecked(false);
    m_visualButton->setChecked(true);
    animateWorkspace(m_visualDesigner);
}

void MainWindow::animateWorkspace(QWidget *widget)
{
    auto *effect = new QGraphicsOpacityEffect(widget);
    widget->setGraphicsEffect(effect);
    auto *animation = new QPropertyAnimation(effect, "opacity", widget);
    animation->setDuration(150);
    animation->setStartValue(0.35);
    animation->setEndValue(1.0);
    animation->setEasingCurve(QEasingCurve::OutCubic);
    connect(animation, &QPropertyAnimation::finished, widget, [widget] { widget->setGraphicsEffect(nullptr); });
    animation->start(QAbstractAnimation::DeleteWhenStopped);
}

void MainWindow::toggleSidebar()
{
    const int start = m_sidebar->width();
    const int end = m_sidebarExpanded ? 0 : 290;
    m_sidebarExpanded = !m_sidebarExpanded;
    m_sidebar->setMinimumWidth(0);
    auto *animation = new QPropertyAnimation(m_sidebar, "maximumWidth", m_sidebar);
    animation->setDuration(180);
    animation->setStartValue(start);
    animation->setEndValue(end);
    animation->setEasingCurve(QEasingCurve::InOutCubic);
    connect(animation, &QPropertyAnimation::finished, this, [this, end] {
        if (end > 0) {
            m_sidebar->setMinimumWidth(250);
            m_sidebar->setMaximumWidth(340);
        } else {
            m_sidebar->setMaximumWidth(0);
        }
    });
    animation->start(QAbstractAnimation::DeleteWhenStopped);
}

void MainWindow::handleApiJson(const QString &operation, const QJsonObject &payload)
{
    if (operation == QStringLiteral("capabilities")) {
        m_policyReadOnly = payload.value(QStringLiteral("read_only")).toBool(true);
        m_policyCreate = payload.value(QStringLiteral("allow_create_projects")).toBool(false);
        m_policyHooks = payload.value(QStringLiteral("allow_hooks")).toBool(false);
        m_policyMaxBytes = payload.value(QStringLiteral("max_document_bytes")).toInt();
        m_connectionLabel->setText(QStringLiteral("●  Secure remote"));
        m_connectionLabel->setObjectName(QStringLiteral("connectionOnline"));
        updatePolicyPanel();
        m_createAction->setEnabled(m_policyCreate && !m_policyReadOnly);
        m_api->fetchProjects();
        return;
    }
    if (operation == QStringLiteral("projects")) {
        m_projects->clear();
        for (const auto &entry : payload.value(QStringLiteral("projects")).toArray()) {
            const auto object = entry.toObject();
            auto *item = new QListWidgetItem(object.value(QStringLiteral("name")).toString(), m_projects);
            item->setText(object.value(QStringLiteral("directory")).toString(item->text()));
            item->setToolTip(object.value(QStringLiteral("slug")).toString());
            item->setData(ProjectPathRole, object.value(QStringLiteral("directory")).toString());
            item->setData(ProjectSourceRole, RemoteSource);
        }
        if (m_projects->count() > 0) {
            m_projects->setCurrentRow(0);
        }
        return;
    }
    if (operation.startsWith(QStringLiteral("documents:"))) {
        m_documents->clear();
        auto *root = new QTreeWidgetItem(m_documents, {QStringLiteral("Server documents")});
        for (const auto &entry : payload.value(QStringLiteral("documents")).toArray()) {
            const auto object = entry.toObject();
            const auto path = object.value(QStringLiteral("path")).toString();
            auto *item = new QTreeWidgetItem(root, {path});
            item->setData(0, DocumentPathRole, path);
            item->setToolTip(0, QStringLiteral("SHA-256 %1").arg(object.value(QStringLiteral("sha256")).toString()));
        }
        root->setExpanded(true);
        return;
    }
    if (operation.startsWith(QStringLiteral("document:"))) {
        loadDocument(payload.value(QStringLiteral("path")).toString(), payload.value(QStringLiteral("content")).toString().toUtf8(),
                     payload.value(QStringLiteral("sha256")).toString());
        return;
    }
    if (operation.startsWith(QStringLiteral("save:"))) {
        m_currentSha256 = payload.value(QStringLiteral("sha256")).toString();
        setDirty(false);
        showStatusMessage(QStringLiteral("Server validated and atomically saved %1").arg(m_currentDocument));
        return;
    }
    if (operation.startsWith(QStringLiteral("validate:"))) {
        QMessageBox::information(this, QStringLiteral("Project valid"),
                                 QStringLiteral("Merged configuration is valid. Resources: %1 · Operations: %2 · Data sources: %3")
                                     .arg(payload.value(QStringLiteral("resources")).toInt())
                                     .arg(payload.value(QStringLiteral("operations")).toInt())
                                     .arg(payload.value(QStringLiteral("data_sources")).toInt()));
        return;
    }
    if (operation == QStringLiteral("create-project")) {
        showStatusMessage(QStringLiteral("Server created the project."));
        m_api->fetchProjects();
    }
}

void MainWindow::handleApiError(const QString &operation, int statusCode, const QString &message)
{
    if (statusCode == 409 && operation.startsWith(QStringLiteral("save:"))) {
        const auto answer = QMessageBox::question(this, QStringLiteral("Document changed on server"),
                                                  QStringLiteral("Your copy is stale. Reload the server version? Unsaved local edits will be lost.\n\n%1")
                                                      .arg(message),
                                                  QMessageBox::Yes | QMessageBox::Cancel, QMessageBox::Cancel);
        if (answer == QMessageBox::Yes) {
            m_api->fetchDocument(m_currentProject, m_currentDocument);
        }
        return;
    }
    QMessageBox::warning(this, QStringLiteral("Editor request failed"),
                         QStringLiteral("%1\n\nOperation: %2\nHTTP: %3").arg(message, operation).arg(statusCode));
}

void MainWindow::updatePolicyPanel()
{
    if (!m_remoteMode) {
        m_policyLabel->setText(QStringLiteral("Local files · atomic save\nHooks: enabled locally\nFull schema: use Forge CLI/server"));
        return;
    }
    m_policyLabel->setText(QStringLiteral("%1\nCreate projects: %2\nPython hooks: %3\nDocument limit: %4 KiB")
                               .arg(m_policyReadOnly ? QStringLiteral("Read only") : QStringLiteral("Validated writes"),
                                    m_policyCreate ? QStringLiteral("allowed") : QStringLiteral("blocked"),
                                    m_policyHooks ? QStringLiteral("allowed") : QStringLiteral("blocked"))
                               .arg(m_policyMaxBytes / 1024));
    m_saveAction->setEnabled(!m_currentDocument.isEmpty() && !m_policyReadOnly);
}

void MainWindow::setDirty(bool dirty)
{
    m_dirty = dirty;
    setWindowModified(dirty);
    const auto title = QStringLiteral("JSON API Forge Editor[*]");
    setWindowTitle(title);
    if (!m_currentDocument.isEmpty()) {
        auto text = QStringLiteral("%1  /  %2  ·  %3").arg(currentModeName(m_remoteMode), m_currentProject, m_currentDocument);
        if (dirty) {
            text += QStringLiteral("  ● unsaved");
        }
        m_breadcrumb->setText(text);
    }
}

bool MainWindow::confirmDiscard()
{
    if (!m_dirty) {
        return true;
    }
    const auto answer = QMessageBox::question(this, QStringLiteral("Unsaved changes"),
                                              QStringLiteral("Discard unsaved changes to %1?").arg(m_currentDocument),
                                              QMessageBox::Discard | QMessageBox::Cancel, QMessageBox::Cancel);
    return answer == QMessageBox::Discard;
}

void MainWindow::managePlugins()
{
    QDialog dialog(this);
    dialog.setWindowTitle(QStringLiteral("Manage native plugins"));
    dialog.resize(780, 480);
    auto *layout = new QVBoxLayout(&dialog);
    auto *warning = new QLabel(
        QStringLiteral("Native plugins execute with your desktop account's full privileges. Enable only plugins you obtained and reviewed from a trusted source. The editor does not auto-enable discovered code."),
        &dialog);
    warning->setWordWrap(true);
    warning->setObjectName(QStringLiteral("warningCard"));
    layout->addWidget(warning);
    auto *tree = new QTreeWidget(&dialog);
    tree->setColumnCount(5);
    tree->setHeaderLabels({QStringLiteral("Enabled"), QStringLiteral("Plugin"), QStringLiteral("Version"), QStringLiteral("Status"),
                           QStringLiteral("Manifest")});
    tree->header()->setSectionResizeMode(1, QHeaderView::ResizeToContents);
    tree->header()->setSectionResizeMode(4, QHeaderView::Stretch);
    const auto enabled = enabledPluginIds();
    for (const auto &descriptor : m_pluginManager->discover()) {
        auto *item = new QTreeWidgetItem(tree, {QString(), descriptor.name, descriptor.version,
                                                descriptor.error.isEmpty() ? QStringLiteral("Compatible") : descriptor.error,
                                                descriptor.manifestPath});
        item->setData(0, Qt::UserRole, descriptor.id);
        item->setFlags(item->flags() | Qt::ItemIsUserCheckable);
        item->setCheckState(0, enabled.contains(descriptor.id) ? Qt::Checked : Qt::Unchecked);
        if (!descriptor.error.isEmpty()) {
            item->setDisabled(true);
        }
    }
    layout->addWidget(tree);
    auto *buttons = new QDialogButtonBox(QDialogButtonBox::Cancel | QDialogButtonBox::Save, &dialog);
    connect(buttons, &QDialogButtonBox::accepted, &dialog, &QDialog::accept);
    connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
    layout->addWidget(buttons);
    if (dialog.exec() != QDialog::Accepted) {
        return;
    }
    QStringList ids;
    for (int index = 0; index < tree->topLevelItemCount(); ++index) {
        const auto *item = tree->topLevelItem(index);
        if (!item->isDisabled() && item->checkState(0) == Qt::Checked) {
            ids.append(item->data(0, Qt::UserRole).toString());
        }
    }
    QSettings().setValue(QStringLiteral("plugins/enabledIds"), ids);
    reloadPlugins();
}

QSet<QString> MainWindow::enabledPluginIds() const
{
    const auto values = QSettings().value(QStringLiteral("plugins/enabledIds")).toStringList();
    return QSet<QString>(values.cbegin(), values.cend());
}

void MainWindow::reloadPlugins()
{
    if (m_pluginManager == nullptr) {
        return;
    }
    m_pluginToolBar->clear();
    const auto messages = m_pluginManager->loadEnabled(enabledPluginIds(), this);
    if (!messages.isEmpty()) {
        showStatusMessage(messages.join(QStringLiteral(" · ")), 8000);
    }
    m_pluginToolBar->setVisible(!m_pluginToolBar->actions().isEmpty());
}

void MainWindow::showAbout()
{
    QMessageBox box(this);
    box.setWindowTitle(QStringLiteral("About JSON API Forge Editor"));
    box.setIconPixmap(QPixmap(QStringLiteral(":/branding/logo.png")).scaled(112, 112, Qt::KeepAspectRatio, Qt::SmoothTransformation));
    box.setText(QStringLiteral("<h2>JSON API Forge Editor 0.4.2</h2><p>A policy-aware C++20 / Qt 6 editor for local and remote Forge projects.</p>"
                               "<p>Code + visual configuration · optimistic concurrency · validated atomic saves · explicit native plugin approval.</p>"));
    box.exec();
}

void MainWindow::addPaletteComponent(const QString &label, const QString &collection, const QJsonObject &documentTemplate)
{
    m_visualDesigner->addPaletteComponent(label, collection, documentTemplate);
}

void MainWindow::addToolAction(QAction *action)
{
    if (action != nullptr) {
        m_pluginToolBar->addAction(action);
        m_pluginToolBar->show();
    }
}

void MainWindow::addDockWidget(Qt::DockWidgetArea area, QDockWidget *dock)
{
    QMainWindow::addDockWidget(area, dock);
}

void MainWindow::showStatusMessage(const QString &message, int timeoutMs)
{
    statusBar()->showMessage(message, timeoutMs);
}

void MainWindow::closeEvent(QCloseEvent *event)
{
    if (confirmDiscard()) {
        event->accept();
    } else {
        event->ignore();
    }
}
