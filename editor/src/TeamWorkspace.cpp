#include "TeamWorkspace.hpp"

#include "ApiClient.hpp"
#include "UiSizing.hpp"

#include <QAbstractItemView>
#include <QApplication>
#include <QCheckBox>
#include <QClipboard>
#include <QComboBox>
#include <QDesktopServices>
#include <QDialog>
#include <QDialogButtonBox>
#include <QFileDialog>
#include <QFormLayout>
#include <QHeaderView>
#include <QHBoxLayout>
#include <QIcon>
#include <QInputDialog>
#include <QJsonDocument>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QMessageBox>
#include <QPixmap>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QSpinBox>
#include <QTabWidget>
#include <QTableWidget>
#include <QTextEdit>
#include <QTimer>
#include <QTreeWidget>
#include <QUrl>
#include <QVBoxLayout>

#ifdef FORGE_EDITOR_HAS_WEBENGINE
#include <QWebEnginePage>
#include <QWebEngineProfile>
#include <QWebEngineView>
#endif

namespace {
constexpr auto IdRole = Qt::UserRole + 1;
constexpr auto AliasRole = Qt::UserRole + 2;
constexpr auto TableRole = Qt::UserRole + 3;
constexpr auto RecordRole = Qt::UserRole + 4;

QString arrayText(const QJsonArray &array)
{
    QStringList values;
    values.reserve(array.size());
    for (const auto &value : array) {
        values.append(value.toString());
    }
    return values.join(QStringLiteral(", "));
}

QString jsonText(const QJsonValue &value)
{
    if (value.isString()) {
        return value.toString();
    }
    if (value.isNull() || value.isUndefined()) {
        return QStringLiteral("—");
    }
    if (value.isArray()) {
        return QString::fromUtf8(QJsonDocument(value.toArray()).toJson(QJsonDocument::Compact));
    }
    if (value.isObject()) {
        return QString::fromUtf8(QJsonDocument(value.toObject()).toJson(QJsonDocument::Compact));
    }
    return value.toVariant().toString();
}

QPushButton *actionButton(const QString &text, QWidget *parent)
{
    auto *button = new QPushButton(text, parent);
    button->setObjectName(QStringLiteral("teamActionButton"));
    return button;
}

QJsonArray splitValues(const QString &text)
{
    QJsonArray result;
    QString normalized(text);
    normalized.replace(u'\n', u',');
    for (const auto &raw : normalized.split(u',', Qt::SkipEmptyParts)) {
        const auto value = raw.trimmed();
        bool exists = false;
        for (const auto &current : result) {
            if (current.toString() == value) {
                exists = true;
                break;
            }
        }
        if (!value.isEmpty() && !exists) {
            result.append(value);
        }
    }
    return result;
}
} // namespace

TeamWorkspace::TeamWorkspace(ApiClient *api, QWidget *parent)
    : QWidget(parent)
    , m_api(api)
    , m_profile(new QLabel(QStringLiteral("Sign in to load your server profile."), this))
    , m_projectLabel(new QLabel(QStringLiteral("No project"), this))
    , m_poll(new QTimer(this))
{
    setObjectName(QStringLiteral("teamWorkspace"));
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(12, 12, 12, 12);
    layout->setSpacing(10);
    auto *header = new QWidget(this);
    header->setObjectName(QStringLiteral("teamHeader"));
    auto *headerLayout = new QHBoxLayout(header);
    headerLayout->setContentsMargins(12, 8, 12, 8);
    auto *mark = new QLabel(header);
    mark->setPixmap(QPixmap(QStringLiteral(":/branding/mark.png"))
                        .scaled(42, 42, Qt::KeepAspectRatio, Qt::SmoothTransformation));
    m_profile->setObjectName(QStringLiteral("teamProfile"));
    m_profile->setWordWrap(true);
    m_projectLabel->setObjectName(QStringLiteral("teamProject"));
    m_projectLabel->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    m_projectLabel->hide();
    auto *editProfile = actionButton(QStringLiteral("Edit profile…"), header);
    headerLayout->addWidget(mark);
    headerLayout->addWidget(m_profile, 1);
    headerLayout->addWidget(editProfile);
    headerLayout->addWidget(m_projectLabel);
    layout->addWidget(header);

    auto *tabs = new QTabWidget(this);
    tabs->setObjectName(QStringLiteral("teamTabs"));
    auto *spaces = new QWidget(tabs);
    auto *database = new QWidget(tabs);
    auto *team = new QWidget(tabs);
    auto *notes = new QWidget(tabs);
    auto *audit = new QWidget(tabs);
    buildSpacesTab(spaces);
    buildDatabaseTab(database);
    buildTeamTab(team);
    buildNotesTab(notes);
    buildAuditTab(audit);
    tabs->addTab(spaces, QStringLiteral("Spaces && calls"));
    tabs->addTab(database, QStringLiteral("Database"));
    tabs->addTab(team, QStringLiteral("People && roles"));
    tabs->addTab(notes, QStringLiteral("Notes"));
    tabs->addTab(audit, QStringLiteral("Audit"));
    layout->addWidget(tabs, 1);

    connect(m_api, &ApiClient::jsonReceived, this, &TeamWorkspace::handleJson);
    connect(m_api, &ApiClient::requestFailed, this, &TeamWorkspace::handleError);
    connect(m_api, &ApiClient::fileDownloaded, this,
            [this](const QString &, const QString &path) {
                emit statusMessage(QStringLiteral("Attachment saved atomically to %1").arg(path));
            });
    connect(editProfile, &QPushButton::clicked, this, &TeamWorkspace::editProfile);
    m_poll->setInterval(5000);
    connect(m_poll, &QTimer::timeout, this, [this] {
        const auto area = currentAreaId();
        if (m_api->isConfigured() && !area.isEmpty()) {
            m_api->fetchMessages(area);
        }
    });
}

void TeamWorkspace::buildTeamTab(QWidget *tab)
{
    auto *layout = new QVBoxLayout(tab);
    auto *buttons = new QHBoxLayout;
    auto *refresh = actionButton(QStringLiteral("Refresh people"), tab);
    auto *invite = actionButton(QStringLiteral("Create scoped invitation…"), tab);
    auto *createRole = actionButton(QStringLiteral("New restricted role…"), tab);
    auto *manageButton = actionButton(QStringLiteral("Manage member…"), tab);
    buttons->addWidget(refresh);
    buttons->addWidget(invite);
    buttons->addWidget(createRole);
    buttons->addWidget(manageButton);
    buttons->addStretch();
    layout->addLayout(buttons);
    m_members = new QTreeWidget(tab);
    m_members->setColumnCount(5);
    m_members->setHeaderLabels({QStringLiteral("Member"), QStringLiteral("Username"), QStringLiteral("Title / status"),
                                QStringLiteral("Roles"), QStringLiteral("Projects")});
    m_members->setAlternatingRowColors(true);
    m_members->header()->setSectionResizeMode(0, QHeaderView::ResizeToContents);
    m_members->header()->setSectionResizeMode(3, QHeaderView::Stretch);
    layout->addWidget(m_members, 2);
    auto *roleLabel = new QLabel(QStringLiteral("Effective role catalog"), tab);
    roleLabel->setObjectName(QStringLiteral("panelEyebrow"));
    layout->addWidget(roleLabel);
    m_roles = new QTreeWidget(tab);
    m_roles->setColumnCount(5);
    m_roles->setHeaderLabels({QStringLiteral("Role"), QStringLiteral("Rank"), QStringLiteral("Permissions"),
                              QStringLiteral("Documents"), QStringLiteral("Databases")});
    m_roles->header()->setSectionResizeMode(2, QHeaderView::Stretch);
    layout->addWidget(m_roles, 1);
    connect(refresh, &QPushButton::clicked, this, [this] {
        m_api->fetchMembers();
        m_api->fetchRoles();
    });
    connect(invite, &QPushButton::clicked, this, &TeamWorkspace::createInvitation);
    connect(createRole, &QPushButton::clicked, this, &TeamWorkspace::createRole);
    connect(manageButton, &QPushButton::clicked, this, &TeamWorkspace::manageMember);
    connect(m_members, &QTreeWidget::itemDoubleClicked,
            this, [this](QTreeWidgetItem *, int) { this->manageMember(); });
}

void TeamWorkspace::buildSpacesTab(QWidget *tab)
{
    auto *layout = new QHBoxLayout(tab);
    auto *left = new QWidget(tab);
    left->setMaximumWidth(290);
    auto *leftLayout = new QVBoxLayout(left);
    auto *areaButtons = new QHBoxLayout;
    auto *refresh = actionButton(QStringLiteral("Refresh"), left);
    auto *create = actionButton(QStringLiteral("New area"), left);
    areaButtons->addWidget(refresh);
    areaButtons->addWidget(create);
    leftLayout->addLayout(areaButtons);
    m_areas = new QListWidget(left);
    m_areas->setObjectName(QStringLiteral("areaList"));
    leftLayout->addWidget(m_areas, 1);
    auto *callLabel = new QLabel(
        QStringLiteral("Calls use one-time tickets. Media is WebRTC peer-to-peer; Forge stores no audio/video."), left);
    callLabel->setObjectName(QStringLiteral("policyCard"));
    callLabel->setWordWrap(true);
    leftLayout->addWidget(callLabel);
    auto *callButtons = new QHBoxLayout;
    auto *audio = actionButton(QStringLiteral("Audio"), left);
    auto *video = actionButton(QStringLiteral("Video"), left);
    callButtons->addWidget(audio);
    callButtons->addWidget(video);
    leftLayout->addLayout(callButtons);
    layout->addWidget(left);

    auto *right = new QWidget(tab);
    auto *rightLayout = new QVBoxLayout(right);
    m_messages = new QTreeWidget(right);
    m_messages->setColumnCount(3);
    m_messages->setHeaderLabels(
        {QStringLiteral("When"), QStringLiteral("Member"), QStringLiteral("Message")});
    m_messages->setRootIsDecorated(false);
    m_messages->setAlternatingRowColors(true);
    m_messages->header()->setSectionResizeMode(0, QHeaderView::ResizeToContents);
    m_messages->header()->setSectionResizeMode(1, QHeaderView::ResizeToContents);
    m_messages->header()->setSectionResizeMode(2, QHeaderView::Stretch);
    rightLayout->addWidget(m_messages, 1);
    auto *attachmentHeader = new QHBoxLayout;
    auto *attachmentLabel = new QLabel(QStringLiteral("Shared files"), right);
    attachmentLabel->setObjectName(QStringLiteral("panelEyebrow"));
    auto *upload = actionButton(QStringLiteral("Upload…"), right);
    auto *download = actionButton(QStringLiteral("Download…"), right);
    auto *refreshFiles = actionButton(QStringLiteral("Reload"), right);
    attachmentHeader->addWidget(attachmentLabel);
    attachmentHeader->addStretch();
    attachmentHeader->addWidget(upload);
    attachmentHeader->addWidget(download);
    attachmentHeader->addWidget(refreshFiles);
    rightLayout->addLayout(attachmentHeader);
    m_attachments = new QTreeWidget(right);
    m_attachments->setColumnCount(4);
    m_attachments->setHeaderLabels({QStringLiteral("File"), QStringLiteral("Member"),
                                    QStringLiteral("Size"), QStringLiteral("SHA-256")});
    m_attachments->setRootIsDecorated(false);
    m_attachments->setAlternatingRowColors(true);
    m_attachments->setMaximumHeight(190);
    m_attachments->header()->setSectionResizeMode(0, QHeaderView::Stretch);
    rightLayout->addWidget(m_attachments);
    auto *composer = new QHBoxLayout;
    m_message = new QLineEdit(right);
    m_message->setMaxLength(8000);
    m_message->setPlaceholderText(QStringLiteral("Write to the selected project area…"));
    auto *send = new QPushButton(QStringLiteral("Send"), right);
    send->setObjectName(QStringLiteral("primaryButton"));
    composer->addWidget(m_message, 1);
    composer->addWidget(send);
    rightLayout->addLayout(composer);
    layout->addWidget(right, 1);
    connect(refresh, &QPushButton::clicked, this, [this] {
        if (!m_project.isEmpty()) {
            m_api->fetchAreas(m_project);
        }
    });
    connect(create, &QPushButton::clicked, this, &TeamWorkspace::createArea);
    connect(m_areas, &QListWidget::itemSelectionChanged, this, &TeamWorkspace::selectArea);
    connect(send, &QPushButton::clicked, this, &TeamWorkspace::sendMessage);
    connect(m_message, &QLineEdit::returnPressed, this, &TeamWorkspace::sendMessage);
    connect(audio, &QPushButton::clicked, this, &TeamWorkspace::startAudioCall);
    connect(video, &QPushButton::clicked, this, &TeamWorkspace::startVideoCall);
    connect(upload, &QPushButton::clicked, this, &TeamWorkspace::uploadAttachment);
    connect(download, &QPushButton::clicked, this, &TeamWorkspace::downloadAttachment);
    connect(refreshFiles, &QPushButton::clicked, this, [this] {
        if (!currentAreaId().isEmpty()) {
            m_api->fetchAttachments(currentAreaId());
        }
    });
    connect(m_attachments, &QTreeWidget::itemDoubleClicked,
            this, [this](QTreeWidgetItem *, int) { downloadAttachment(); });
}

void TeamWorkspace::buildDatabaseTab(QWidget *tab)
{
    auto *layout = new QHBoxLayout(tab);
    m_databaseTree = new QTreeWidget(tab);
    m_databaseTree->setHeaderLabels({QStringLiteral("Runtime-declared database objects")});
    m_databaseTree->setMaximumWidth(330);
    layout->addWidget(m_databaseTree);
    m_rows = new QTableWidget(tab);
    m_rows->setEditTriggers(QAbstractItemView::NoEditTriggers);
    m_rows->setAlternatingRowColors(true);
    m_rows->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_rows->horizontalHeader()->setStretchLastSection(true);
    layout->addWidget(m_rows, 1);
    connect(m_databaseTree, &QTreeWidget::itemDoubleClicked, this,
            [this](QTreeWidgetItem *, int) { selectDatabaseTable(); });
}

void TeamWorkspace::buildNotesTab(QWidget *tab)
{
    auto *layout = new QHBoxLayout(tab);
    m_notes = new QTreeWidget(tab);
    m_notes->setColumnCount(3);
    m_notes->setHeaderLabels({QStringLiteral("Title"), QStringLiteral("Author"), QStringLiteral("Visibility")});
    m_notes->setMaximumWidth(430);
    layout->addWidget(m_notes);
    auto *editor = new QWidget(tab);
    auto *editorLayout = new QVBoxLayout(editor);
    m_noteTitle = new QLineEdit(editor);
    m_noteTitle->setMaxLength(160);
    m_noteTitle->setPlaceholderText(QStringLiteral("Note title"));
    m_noteVisibility = new QComboBox(editor);
    m_noteVisibility->addItems(
        {QStringLiteral("open"), QStringLiteral("restricted"), QStringLiteral("private")});
    m_noteBody = new QTextEdit(editor);
    m_noteBody->setAcceptRichText(false);
    m_noteBody->setPlaceholderText(QStringLiteral("Project note. Rich HTML is not stored or rendered."));
    auto *save = new QPushButton(QStringLiteral("Share note"), editor);
    save->setObjectName(QStringLiteral("primaryButton"));
    auto *refresh = actionButton(QStringLiteral("Refresh notes"), editor);
    auto *form = new QFormLayout;
    form->addRow(QStringLiteral("Title"), m_noteTitle);
    form->addRow(QStringLiteral("Visibility"), m_noteVisibility);
    editorLayout->addLayout(form);
    editorLayout->addWidget(m_noteBody, 1);
    auto *buttons = new QHBoxLayout;
    buttons->addWidget(save);
    buttons->addWidget(refresh);
    buttons->addStretch();
    editorLayout->addLayout(buttons);
    layout->addWidget(editor, 1);
    connect(save, &QPushButton::clicked, this, &TeamWorkspace::saveNote);
    connect(refresh, &QPushButton::clicked, this, [this] {
        if (!m_project.isEmpty()) {
            m_api->fetchNotes(m_project);
        }
    });
    connect(m_notes, &QTreeWidget::itemSelectionChanged, this, [this] {
        const auto *item = m_notes->currentItem();
        if (item != nullptr) {
            m_noteTitle->setText(item->text(0));
            m_noteBody->setPlainText(item->data(0, Qt::UserRole).toString());
            const auto visibility = item->text(2);
            m_noteVisibility->setCurrentText(visibility);
        }
    });
}

void TeamWorkspace::buildAuditTab(QWidget *tab)
{
    auto *layout = new QVBoxLayout(tab);
    auto *refresh = actionButton(QStringLiteral("Refresh security audit"), tab);
    layout->addWidget(refresh, 0, Qt::AlignLeft);
    m_audit = new QTreeWidget(tab);
    m_audit->setColumnCount(5);
    m_audit->setHeaderLabels({QStringLiteral("When"), QStringLiteral("Action"), QStringLiteral("Project"),
                              QStringLiteral("Target"), QStringLiteral("Details")});
    m_audit->header()->setSectionResizeMode(4, QHeaderView::Stretch);
    m_audit->setAlternatingRowColors(true);
    layout->addWidget(m_audit, 1);
    connect(refresh, &QPushButton::clicked, this,
            [this] { m_api->fetchAudit(m_project.isEmpty() ? QString() : m_project); });
}

void TeamWorkspace::setCapabilities(const QJsonObject &capabilities)
{
    m_databaseEnabled = capabilities.value(QStringLiteral("database_browser")).toBool(false);
    m_collaborationEnabled = capabilities.value(QStringLiteral("collaboration")).toBool(false);
    m_callsEnabled = capabilities.value(QStringLiteral("calls")).toBool(false);
    m_rank = capabilities.value(QStringLiteral("rank")).toInt();
    m_permissionCatalog = capabilities.value(QStringLiteral("permission_catalog")).toArray();
    const auto advertisedLimit = static_cast<qint64>(
        capabilities.value(QStringLiteral("max_attachment_bytes")).toDouble(16.0 * 1024.0 * 1024.0));
    m_maxAttachmentBytes = static_cast<qsizetype>(qBound<qint64>(1, advertisedLimit, 512LL * 1024LL * 1024LL));
}

void TeamWorkspace::setProject(const QString &project)
{
    if (m_project == project) {
        return;
    }
    m_project = project;
    m_projectLabel->setText(QStringLiteral("PROJECT · %1").arg(project));
    m_projectLabel->setVisible(!project.isEmpty());
    m_areas->clear();
    m_messages->clear();
    m_attachments->clear();
    m_databaseTree->clear();
    m_rows->clear();
    m_notes->clear();
    if (!project.isEmpty() && m_api->isConfigured()) {
        if (m_collaborationEnabled) {
            m_api->fetchAreas(project);
            m_api->fetchNotes(project);
            m_poll->start();
        }
        if (m_databaseEnabled) {
            m_api->fetchDatabases(project);
        }
    } else {
        m_poll->stop();
    }
}

void TeamWorkspace::refreshAll()
{
    if (!m_api->isConfigured()) {
        return;
    }
    m_api->fetchProfile();
    m_api->fetchMembers();
    m_api->fetchRoles();
    m_api->fetchAudit(m_project);
    if (!m_project.isEmpty()) {
        if (m_collaborationEnabled) {
            m_api->fetchAreas(m_project);
            m_api->fetchNotes(m_project);
        }
        if (m_databaseEnabled) {
            m_api->fetchDatabases(m_project);
        }
    }
}

void TeamWorkspace::reset()
{
    m_poll->stop();
    m_project.clear();
    m_roleRecords = {};
    m_memberRecords = {};
    m_profileRecord = {};
    m_permissionCatalog = {};
    m_rank = 0;
    m_profile->setText(QStringLiteral("Sign in to load your server profile."));
    m_projectLabel->setText(QStringLiteral("No project"));
    m_projectLabel->hide();
    for (auto *tree : {m_members, m_roles, m_messages, m_attachments, m_databaseTree, m_notes, m_audit}) {
        tree->clear();
    }
    m_areas->clear();
    m_rows->clear();
}

QString TeamWorkspace::currentAreaId() const
{
    return m_areas->currentItem() == nullptr ? QString()
                                             : m_areas->currentItem()->data(IdRole).toString();
}

void TeamWorkspace::selectArea()
{
    m_messages->clear();
    m_attachments->clear();
    const auto area = currentAreaId();
    if (!area.isEmpty()) {
        m_api->fetchMessages(area);
        m_api->fetchAttachments(area);
    }
}

void TeamWorkspace::sendMessage()
{
    const auto area = currentAreaId();
    const auto body = m_message->text().trimmed();
    if (area.isEmpty() || body.isEmpty()) {
        emit statusMessage(QStringLiteral("Select a project area and enter a message."));
        return;
    }
    m_api->postMessage(area, body);
    m_message->clear();
}

void TeamWorkspace::createArea()
{
    if (m_project.isEmpty()) {
        emit statusMessage(QStringLiteral("Select a remote project before creating an area."));
        return;
    }
    QDialog dialog(this);
    dialog.setWindowTitle(QStringLiteral("New project area"));
    auto *layout = new QVBoxLayout(&dialog);
    auto *name = new QLineEdit(&dialog);
    name->setMaxLength(96);
    auto *description = new QLineEdit(&dialog);
    description->setMaxLength(500);
    auto *visibility = new QComboBox(&dialog);
    visibility->addItems({QStringLiteral("open"), QStringLiteral("restricted")});
    auto *rank = new QSpinBox(&dialog);
    rank->setRange(0, qMax(0, m_rank - 1));
    auto *form = new QFormLayout;
    form->addRow(QStringLiteral("Name"), name);
    form->addRow(QStringLiteral("Description"), description);
    form->addRow(QStringLiteral("Visibility"), visibility);
    form->addRow(QStringLiteral("Minimum rank"), rank);
    layout->addLayout(form);
    auto *buttons = new QDialogButtonBox(QDialogButtonBox::Cancel | QDialogButtonBox::Ok, &dialog);
    connect(buttons, &QDialogButtonBox::accepted, &dialog, &QDialog::accept);
    connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
    layout->addWidget(buttons);
    if (dialog.exec() == QDialog::Accepted && !name->text().trimmed().isEmpty()) {
        m_api->createArea(m_project, name->text().trimmed(), description->text().trimmed(),
                          visibility->currentText(), rank->value());
    }
}

void TeamWorkspace::editProfile()
{
    if (m_profileRecord.isEmpty()) {
        emit statusMessage(QStringLiteral("Your profile is still loading."));
        m_api->fetchProfile();
        return;
    }
    QDialog dialog(this);
    dialog.setWindowTitle(QStringLiteral("Edit server profile"));
    auto *layout = new QVBoxLayout(&dialog);
    auto *displayName = new QLineEdit(m_profileRecord.value(QStringLiteral("display_name")).toString(), &dialog);
    auto *title = new QLineEdit(m_profileRecord.value(QStringLiteral("title")).toString(), &dialog);
    auto *status = new QLineEdit(m_profileRecord.value(QStringLiteral("status")).toString(), &dialog);
    auto *timezoneField = new QLineEdit(m_profileRecord.value(QStringLiteral("timezone")).toString(), &dialog);
    auto *bio = new QPlainTextEdit(m_profileRecord.value(QStringLiteral("bio")).toString(), &dialog);
    displayName->setMaxLength(80);
    title->setMaxLength(120);
    status->setMaxLength(160);
    timezoneField->setMaxLength(64);
    bio->setMaximumHeight(150);
    auto *form = new QFormLayout;
    form->addRow(QStringLiteral("Display name"), displayName);
    form->addRow(QStringLiteral("Title"), title);
    form->addRow(QStringLiteral("Status"), status);
    form->addRow(QStringLiteral("Timezone"), timezoneField);
    form->addRow(QStringLiteral("Bio"), bio);
    layout->addLayout(form);
    auto *notice = new QLabel(
        QStringLiteral("Profile data lives on this Forge server and is visible only through server-enforced team permissions."),
        &dialog);
    notice->setObjectName(QStringLiteral("policyCard"));
    notice->setWordWrap(true);
    layout->addWidget(notice);
    auto *buttons = new QDialogButtonBox(QDialogButtonBox::Cancel | QDialogButtonBox::Save, &dialog);
    connect(buttons, &QDialogButtonBox::accepted, &dialog, &QDialog::accept);
    connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
    layout->addWidget(buttons);
    if (dialog.exec() != QDialog::Accepted) {
        return;
    }
    const auto trimmedDisplayName = displayName->text().trimmed();
    if (trimmedDisplayName.isEmpty() || bio->toPlainText().size() > 2000) {
        emit statusMessage(QStringLiteral("Display name is required and the bio is limited to 2,000 characters."));
        return;
    }
    m_api->updateProfile(QJsonObject{{QStringLiteral("display_name"), trimmedDisplayName},
                                     {QStringLiteral("title"), title->text().trimmed()},
                                     {QStringLiteral("status"), status->text().trimmed()},
                                     {QStringLiteral("timezone"), timezoneField->text().trimmed()},
                                     {QStringLiteral("bio"), bio->toPlainText().trimmed()}});
}

void TeamWorkspace::createRole()
{
    if (m_permissionCatalog.isEmpty() || m_rank <= 1) {
        emit statusMessage(QStringLiteral("This account cannot create restricted roles."));
        return;
    }
    QDialog dialog(this);
    dialog.setWindowTitle(QStringLiteral("New restricted worker role"));
    ForgeEditorUi::resizeToFit(&dialog, QSize(720, 650));
    auto *layout = new QVBoxLayout(&dialog);
    auto *name = new QLineEdit(&dialog);
    name->setMaxLength(64);
    auto *rank = new QSpinBox(&dialog);
    rank->setRange(1, qMin(999, m_rank - 1));
    rank->setValue(qMin(rank->maximum(), 100));
    auto *form = new QFormLayout;
    form->addRow(QStringLiteral("Role name"), name);
    form->addRow(QStringLiteral("Rank"), rank);
    layout->addLayout(form);
    auto *permissionsLabel = new QLabel(QStringLiteral("Explicit permissions"), &dialog);
    permissionsLabel->setObjectName(QStringLiteral("panelEyebrow"));
    layout->addWidget(permissionsLabel);
    auto *permissions = new QTreeWidget(&dialog);
    permissions->setHeaderLabels({QStringLiteral("Permission")});
    permissions->setRootIsDecorated(false);
    for (const auto &value : m_permissionCatalog) {
        auto *item = new QTreeWidgetItem(permissions, {value.toString()});
        item->setFlags(item->flags() | Qt::ItemIsUserCheckable);
        item->setCheckState(0, Qt::Unchecked);
    }
    layout->addWidget(permissions, 1);
    auto *documentAllow = new QLineEdit(QStringLiteral("app.json, config/*.json, graphs/*.forgegraph.json"), &dialog);
    auto *documentDeny = new QLineEdit(QStringLiteral("hooks/*"), &dialog);
    auto *databaseAllow = new QLineEdit(&dialog);
    documentAllow->setPlaceholderText(QStringLiteral("Comma-separated document patterns"));
    documentDeny->setPlaceholderText(QStringLiteral("Comma-separated deny patterns"));
    databaseAllow->setPlaceholderText(QStringLiteral("Comma-separated database aliases or patterns"));
    auto *scopeForm = new QFormLayout;
    scopeForm->addRow(QStringLiteral("Document allow"), documentAllow);
    scopeForm->addRow(QStringLiteral("Document deny"), documentDeny);
    scopeForm->addRow(QStringLiteral("Database allow"), databaseAllow);
    layout->addLayout(scopeForm);
    auto *notice = new QLabel(
        QStringLiteral("The server rejects unknown permissions, unsafe patterns and any rank or scope wider than your own authority."),
        &dialog);
    notice->setObjectName(QStringLiteral("warningCard"));
    notice->setWordWrap(true);
    layout->addWidget(notice);
    auto *buttons = new QDialogButtonBox(QDialogButtonBox::Cancel | QDialogButtonBox::Save, &dialog);
    connect(buttons, &QDialogButtonBox::accepted, &dialog, &QDialog::accept);
    connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
    layout->addWidget(buttons);
    if (dialog.exec() != QDialog::Accepted || name->text().trimmed().isEmpty()) {
        return;
    }
    QJsonArray selectedPermissions;
    for (int index = 0; index < permissions->topLevelItemCount(); ++index) {
        const auto *item = permissions->topLevelItem(index);
        if (item->checkState(0) == Qt::Checked) {
            selectedPermissions.append(item->text(0));
        }
    }
    if (selectedPermissions.isEmpty()) {
        emit statusMessage(QStringLiteral("Select at least one explicit permission for the new role."));
        return;
    }
    m_api->createRole(name->text().trimmed(), rank->value(), selectedPermissions,
                      splitValues(documentAllow->text()), splitValues(documentDeny->text()),
                      splitValues(databaseAllow->text()));
}

void TeamWorkspace::manageMember()
{
    const auto *selected = m_members->currentItem();
    const auto member = selected == nullptr ? QJsonObject{} : selected->data(0, RecordRole).toJsonObject();
    if (member.isEmpty()) {
        emit statusMessage(QStringLiteral("Select a worker to manage."));
        return;
    }
    if (member.value(QStringLiteral("is_founder")).toBool()) {
        emit statusMessage(QStringLiteral("The founder account is protected and cannot be reassigned or disabled."));
        return;
    }
    QDialog dialog(this);
    dialog.setWindowTitle(QStringLiteral("Manage @%1").arg(member.value(QStringLiteral("username")).toString()));
    ForgeEditorUi::resizeToFit(&dialog, QSize(660, 480));
    auto *layout = new QVBoxLayout(&dialog);
    auto *active = new QCheckBox(QStringLiteral("Account active"), &dialog);
    active->setChecked(member.value(QStringLiteral("active")).toBool());
    layout->addWidget(active);
    auto *memberships = new QTreeWidget(&dialog);
    memberships->setColumnCount(2);
    memberships->setHeaderLabels({QStringLiteral("Role"), QStringLiteral("Project scope")});
    memberships->header()->setSectionResizeMode(0, QHeaderView::Stretch);
    for (const auto &value : member.value(QStringLiteral("memberships")).toArray()) {
        const auto membership = value.toObject();
        auto *item = new QTreeWidgetItem(
            memberships, {membership.value(QStringLiteral("role")).toString(),
                          membership.value(QStringLiteral("project")).toString()});
        item->setData(0, IdRole, membership.value(QStringLiteral("role_id")).toString());
    }
    layout->addWidget(memberships, 1);
    auto *role = new QComboBox(&dialog);
    for (const auto &value : m_roleRecords) {
        const auto record = value.toObject();
        if (record.value(QStringLiteral("rank")).toInt() < m_rank) {
            role->addItem(record.value(QStringLiteral("name")).toString(),
                          record.value(QStringLiteral("id")).toString());
        }
    }
    auto *project = new QLineEdit(m_project.isEmpty() ? QStringLiteral("*") : m_project, &dialog);
    project->setMaxLength(64);
    auto *add = actionButton(QStringLiteral("Add membership"), &dialog);
    auto *remove = actionButton(QStringLiteral("Remove selected"), &dialog);
    auto *membershipForm = new QFormLayout;
    membershipForm->addRow(QStringLiteral("Role"), role);
    membershipForm->addRow(QStringLiteral("Project"), project);
    layout->addLayout(membershipForm);
    auto *membershipButtons = new QHBoxLayout;
    membershipButtons->addWidget(add);
    membershipButtons->addWidget(remove);
    membershipButtons->addStretch();
    layout->addLayout(membershipButtons);
    connect(add, &QPushButton::clicked, &dialog, [memberships, role, project] {
        const auto roleId = role->currentData().toString();
        const auto projectScope = project->text().trimmed();
        if (roleId.isEmpty() || projectScope.isEmpty() || memberships->topLevelItemCount() >= 32) {
            return;
        }
        for (int index = 0; index < memberships->topLevelItemCount(); ++index) {
            const auto *existing = memberships->topLevelItem(index);
            if (existing->data(0, IdRole).toString() == roleId && existing->text(1) == projectScope) {
                return;
            }
        }
        auto *item = new QTreeWidgetItem(memberships, {role->currentText(), projectScope});
        item->setData(0, IdRole, roleId);
    });
    connect(remove, &QPushButton::clicked, &dialog, [memberships] {
        delete memberships->takeTopLevelItem(memberships->indexOfTopLevelItem(memberships->currentItem()));
    });
    auto *notice = new QLabel(
        QStringLiteral("Saving replaces the worker's memberships as one server transaction. Founder and peer-or-higher ranks remain protected."),
        &dialog);
    notice->setObjectName(QStringLiteral("warningCard"));
    notice->setWordWrap(true);
    layout->addWidget(notice);
    auto *buttons = new QDialogButtonBox(QDialogButtonBox::Cancel | QDialogButtonBox::Save, &dialog);
    connect(buttons, &QDialogButtonBox::accepted, &dialog, &QDialog::accept);
    connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
    layout->addWidget(buttons);
    if (dialog.exec() != QDialog::Accepted) {
        return;
    }
    QJsonArray values;
    for (int index = 0; index < memberships->topLevelItemCount(); ++index) {
        const auto *item = memberships->topLevelItem(index);
        values.append(QJsonObject{{QStringLiteral("role_id"), item->data(0, IdRole).toString()},
                                  {QStringLiteral("project"), item->text(1)}});
    }
    m_api->updateMember(member.value(QStringLiteral("id")).toString(), values, active->isChecked());
}

void TeamWorkspace::createInvitation()
{
    if (m_roleRecords.isEmpty()) {
        m_api->fetchRoles();
        emit statusMessage(QStringLiteral("Role catalog is loading; try the invitation action again."));
        return;
    }
    QDialog dialog(this);
    dialog.setWindowTitle(QStringLiteral("Create worker invitation"));
    auto *layout = new QVBoxLayout(&dialog);
    auto *role = new QComboBox(&dialog);
    for (const auto &value : m_roleRecords) {
        const auto record = value.toObject();
        if (record.value(QStringLiteral("rank")).toInt() < m_rank) {
            role->addItem(record.value(QStringLiteral("name")).toString(),
                          record.value(QStringLiteral("id")).toString());
        }
    }
    auto *project = new QLineEdit(m_project.isEmpty() ? QStringLiteral("*") : m_project, &dialog);
    auto *hours = new QSpinBox(&dialog);
    hours->setRange(1, 168);
    hours->setValue(24);
    auto *notice = new QLabel(
        QStringLiteral("The token is shown once. Send it through a separate trusted channel; never paste it into project files."),
        &dialog);
    notice->setObjectName(QStringLiteral("warningCard"));
    notice->setWordWrap(true);
    auto *form = new QFormLayout;
    form->addRow(QStringLiteral("Role"), role);
    form->addRow(QStringLiteral("Project scope"), project);
    form->addRow(QStringLiteral("Expires in hours"), hours);
    layout->addWidget(notice);
    layout->addLayout(form);
    auto *buttons = new QDialogButtonBox(QDialogButtonBox::Cancel | QDialogButtonBox::Ok, &dialog);
    connect(buttons, &QDialogButtonBox::accepted, &dialog, &QDialog::accept);
    connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
    layout->addWidget(buttons);
    if (dialog.exec() == QDialog::Accepted && role->currentIndex() >= 0) {
        m_api->createInvitation(role->currentData().toString(), project->text().trimmed(), hours->value());
    }
}

void TeamWorkspace::uploadAttachment()
{
    const auto area = currentAreaId();
    if (area.isEmpty()) {
        emit statusMessage(QStringLiteral("Select a visible project area before sharing a file."));
        return;
    }
    const auto filePath = QFileDialog::getOpenFileName(this, QStringLiteral("Share file with project area"));
    if (!filePath.isEmpty()) {
        m_api->uploadAttachment(area, filePath, m_maxAttachmentBytes);
    }
}

void TeamWorkspace::downloadAttachment()
{
    const auto *item = m_attachments->currentItem();
    if (item == nullptr || item->data(0, IdRole).toString().isEmpty()) {
        emit statusMessage(QStringLiteral("Select a shared file to download."));
        return;
    }
    const auto target = QFileDialog::getSaveFileName(this, QStringLiteral("Save shared file"), item->text(0));
    if (!target.isEmpty()) {
        m_api->downloadAttachment(item->data(0, IdRole).toString(), target, m_maxAttachmentBytes);
    }
}

void TeamWorkspace::saveNote()
{
    if (m_project.isEmpty() || m_noteTitle->text().trimmed().isEmpty()) {
        emit statusMessage(QStringLiteral("Select a project and enter a note title."));
        return;
    }
    m_api->createNote(m_project, currentAreaId(), m_noteTitle->text().trimmed(), m_noteBody->toPlainText(),
                      m_noteVisibility->currentText());
}

void TeamWorkspace::selectDatabaseTable()
{
    const auto *item = m_databaseTree->currentItem();
    if (item == nullptr || item->data(0, TableRole).toString().isEmpty()) {
        return;
    }
    m_api->fetchDatabaseRows(m_project, item->data(0, AliasRole).toString(),
                             item->data(0, TableRole).toString());
}

void TeamWorkspace::startAudioCall()
{
    if (!m_callsEnabled || currentAreaId().isEmpty()) {
        emit statusMessage(QStringLiteral("Select an area on a server that permits calls."));
        return;
    }
    m_api->startCall(currentAreaId(), QStringLiteral("audio"));
}

void TeamWorkspace::startVideoCall()
{
    if (!m_callsEnabled || currentAreaId().isEmpty()) {
        emit statusMessage(QStringLiteral("Select an area on a server that permits calls."));
        return;
    }
    m_api->startCall(currentAreaId(), QStringLiteral("video"));
}

void TeamWorkspace::handleJson(const QString &operation, const QJsonObject &payload)
{
    if (operation == QStringLiteral("team-me") || operation == QStringLiteral("team-profile-update")) {
        m_profileRecord = payload;
        const auto badge = payload.value(QStringLiteral("is_founder")).toBool()
            ? QStringLiteral("FOUNDER")
            : QStringLiteral("MEMBER");
        m_profile->setText(QStringLiteral("%1  ·  @%2\n%3 · %4")
                               .arg(payload.value(QStringLiteral("display_name")).toString(),
                                    payload.value(QStringLiteral("username")).toString(), badge,
                                    payload.value(QStringLiteral("status")).toString(QStringLiteral("Available"))));
        return;
    }
    if (operation == QStringLiteral("team-members")) {
        m_members->clear();
        m_memberRecords = payload.value(QStringLiteral("members")).toArray();
        for (const auto &value : m_memberRecords) {
            const auto member = value.toObject();
            QStringList roles;
            QStringList projects;
            for (const auto &membershipValue : member.value(QStringLiteral("memberships")).toArray()) {
                const auto membership = membershipValue.toObject();
                roles.append(membership.value(QStringLiteral("role")).toString());
                projects.append(membership.value(QStringLiteral("project")).toString());
            }
            auto *row = new QTreeWidgetItem(
                m_members,
                {member.value(QStringLiteral("display_name")).toString(),
                 member.value(QStringLiteral("username")).toString(),
                 QStringLiteral("%1 · %2")
                     .arg(member.value(QStringLiteral("title")).toString(),
                          member.value(QStringLiteral("active")).toBool() ? QStringLiteral("active")
                                                                          : QStringLiteral("disabled")),
                 roles.join(QStringLiteral(", ")), projects.join(QStringLiteral(", "))});
            row->setToolTip(0, member.value(QStringLiteral("status")).toString());
            row->setData(0, RecordRole, member);
        }
        return;
    }
    if (operation == QStringLiteral("team-roles")) {
        m_roles->clear();
        m_roleRecords = payload.value(QStringLiteral("roles")).toArray();
        for (const auto &value : m_roleRecords) {
            const auto role = value.toObject();
            new QTreeWidgetItem(m_roles,
                                {role.value(QStringLiteral("name")).toString(),
                                 QString::number(role.value(QStringLiteral("rank")).toInt()),
                                 arrayText(role.value(QStringLiteral("permissions")).toArray()),
                                 arrayText(role.value(QStringLiteral("document_allow")).toArray()),
                                 arrayText(role.value(QStringLiteral("database_allow")).toArray())});
        }
        return;
    }
    if (operation == QStringLiteral("team-role-create")) {
        m_api->fetchRoles();
        m_api->fetchAudit(m_project);
        emit statusMessage(QStringLiteral("Restricted role created; the server applied rank and scope checks."));
        return;
    }
    if (operation == QStringLiteral("team-member-update")) {
        m_api->fetchMembers();
        m_api->fetchAudit(m_project);
        emit statusMessage(QStringLiteral("Worker memberships updated by the server."));
        return;
    }
    if (operation == QStringLiteral("team-invitation")) {
        const auto token = payload.value(QStringLiteral("invitation")).toString();
        QMessageBox box(this);
        box.setWindowTitle(QStringLiteral("Single-use invitation"));
        box.setIcon(QMessageBox::Information);
        box.setText(QStringLiteral("Copy this token now. It is not listed again:"));
        box.setInformativeText(token);
        auto *copy = box.addButton(QStringLiteral("Copy token"), QMessageBox::ActionRole);
        box.exec();
        if (box.clickedButton() == copy) {
            QApplication::clipboard()->setText(token);
            emit statusMessage(QStringLiteral("Invitation copied. Send it through a separate trusted channel."));
        }
        return;
    }
    if (operation == QStringLiteral("team-areas") || operation == QStringLiteral("team-area-create")) {
        if (operation == QStringLiteral("team-area-create")) {
            m_api->fetchAreas(m_project);
            return;
        }
        const auto previous = currentAreaId();
        m_areas->clear();
        for (const auto &value : payload.value(QStringLiteral("areas")).toArray()) {
            const auto area = value.toObject();
            auto *item = new QListWidgetItem(
                QStringLiteral("%1\n%2 · rank %3")
                    .arg(area.value(QStringLiteral("name")).toString(),
                         area.value(QStringLiteral("visibility")).toString())
                    .arg(area.value(QStringLiteral("minimum_rank")).toInt()),
                m_areas);
            item->setData(IdRole, area.value(QStringLiteral("id")).toString());
            item->setToolTip(area.value(QStringLiteral("description")).toString());
            if (item->data(IdRole).toString() == previous) {
                m_areas->setCurrentItem(item);
            }
        }
        if (m_areas->currentItem() == nullptr && m_areas->count() > 0) {
            m_areas->setCurrentRow(0);
        }
        return;
    }
    if (operation.startsWith(QStringLiteral("team-messages:"))) {
        m_messages->clear();
        for (const auto &value : payload.value(QStringLiteral("messages")).toArray()) {
            const auto message = value.toObject();
            auto *row = new QTreeWidgetItem(
                m_messages,
                {message.value(QStringLiteral("created_at")).toString(),
                 message.value(QStringLiteral("display_name")).toString(),
                 message.value(QStringLiteral("body")).toString()});
            if (message.value(QStringLiteral("kind")).toString() == QStringLiteral("announcement")) {
                row->setIcon(2, QIcon(QStringLiteral(":/branding/mark.png")));
            }
        }
        m_messages->scrollToBottom();
        return;
    }
    if (operation.startsWith(QStringLiteral("team-message:"))) {
        m_api->fetchMessages(currentAreaId());
        return;
    }
    if (operation.startsWith(QStringLiteral("team-attachments:"))) {
        m_attachments->clear();
        for (const auto &value : payload.value(QStringLiteral("attachments")).toArray()) {
            const auto attachment = value.toObject();
            auto *row = new QTreeWidgetItem(
                m_attachments,
                {attachment.value(QStringLiteral("original_name")).toString(),
                 attachment.value(QStringLiteral("display_name")).toString(),
                 QStringLiteral("%1 bytes").arg(static_cast<qint64>(attachment.value(QStringLiteral("size")).toDouble())),
                 attachment.value(QStringLiteral("sha256")).toString()});
            row->setData(0, IdRole, attachment.value(QStringLiteral("id")).toString());
            row->setToolTip(3, attachment.value(QStringLiteral("sha256")).toString());
        }
        return;
    }
    if (operation == QStringLiteral("team-attachment-upload")) {
        m_api->fetchAttachments(currentAreaId());
        emit statusMessage(QStringLiteral("File uploaded to the selected policy-filtered project area."));
        return;
    }
    if (operation == QStringLiteral("team-notes") || operation == QStringLiteral("team-note-create")) {
        if (operation == QStringLiteral("team-note-create")) {
            m_noteTitle->clear();
            m_noteBody->clear();
            m_api->fetchNotes(m_project);
            return;
        }
        m_notes->clear();
        for (const auto &value : payload.value(QStringLiteral("notes")).toArray()) {
            const auto note = value.toObject();
            auto *row = new QTreeWidgetItem(
                m_notes,
                {note.value(QStringLiteral("title")).toString(),
                 note.value(QStringLiteral("display_name")).toString(),
                 note.value(QStringLiteral("visibility")).toString()});
            row->setData(0, Qt::UserRole, note.value(QStringLiteral("body")).toString());
        }
        return;
    }
    if (operation.startsWith(QStringLiteral("team-databases:"))) {
        m_databaseTree->clear();
        for (const auto &databaseValue : payload.value(QStringLiteral("databases")).toArray()) {
            const auto database = databaseValue.toObject();
            const auto alias = database.value(QStringLiteral("alias")).toString();
            auto *databaseItem = new QTreeWidgetItem(m_databaseTree, {alias});
            for (const auto &tableValue : database.value(QStringLiteral("tables")).toArray()) {
                const auto table = tableValue.toObject();
                auto *tableItem = new QTreeWidgetItem(
                    databaseItem,
                    {QStringLiteral("%1  ·  %2")
                         .arg(table.value(QStringLiteral("name")).toString(),
                              table.value(QStringLiteral("row_browsing")).toBool()
                                  ? QStringLiteral("read-only rows")
                                  : QStringLiteral("metadata only"))});
                tableItem->setData(0, AliasRole, alias);
                tableItem->setData(0, TableRole, table.value(QStringLiteral("name")).toString());
                tableItem->setDisabled(!table.value(QStringLiteral("row_browsing")).toBool());
            }
            databaseItem->setExpanded(true);
        }
        return;
    }
    if (operation.startsWith(QStringLiteral("team-rows:"))) {
        const auto columns = payload.value(QStringLiteral("columns")).toArray();
        const auto rows = payload.value(QStringLiteral("rows")).toArray();
        m_rows->clear();
        m_rows->setColumnCount(static_cast<int>(columns.size()));
        m_rows->setRowCount(static_cast<int>(rows.size()));
        QStringList headers;
        for (const auto &column : columns) {
            headers.append(column.toString());
        }
        m_rows->setHorizontalHeaderLabels(headers);
        for (qsizetype rowIndex = 0; rowIndex < rows.size(); ++rowIndex) {
            const auto object = rows.at(rowIndex).toObject();
            for (qsizetype columnIndex = 0; columnIndex < columns.size(); ++columnIndex) {
                m_rows->setItem(static_cast<int>(rowIndex), static_cast<int>(columnIndex),
                                new QTableWidgetItem(jsonText(object.value(columns.at(columnIndex).toString()))));
            }
        }
        m_rows->resizeColumnsToContents();
        emit statusMessage(QStringLiteral("Loaded %1 policy-filtered, read-only database rows.").arg(rows.size()));
        return;
    }
    if (operation == QStringLiteral("team-call")) {
        m_api->createCallTicket(payload.value(QStringLiteral("id")).toString());
        return;
    }
    if (operation.startsWith(QStringLiteral("team-call-ticket:"))) {
        const auto url = m_api->callClientUrl(payload.value(QStringLiteral("call_client_path")).toString(),
                                              payload.value(QStringLiteral("ticket")).toString());
        if (!url.isValid()) {
            emit statusMessage(QStringLiteral("The server returned an invalid call URL."));
        } else {
            openCall(url);
        }
        return;
    }
    if (operation == QStringLiteral("team-audit")) {
        m_audit->clear();
        for (const auto &value : payload.value(QStringLiteral("events")).toArray()) {
            const auto event = value.toObject();
            new QTreeWidgetItem(
                m_audit,
                {event.value(QStringLiteral("created_at")).toString(),
                 event.value(QStringLiteral("action")).toString(),
                 event.value(QStringLiteral("project")).toString(),
                 event.value(QStringLiteral("target")).toString(),
                 jsonText(event.value(QStringLiteral("detail")))});
        }
    }
}

void TeamWorkspace::handleError(const QString &operation, int statusCode, const QString &message)
{
    if (!operation.startsWith(QStringLiteral("team-"))) {
        return;
    }
    emit statusMessage(QStringLiteral("Team workspace · %1 · HTTP %2 · %3").arg(operation).arg(statusCode).arg(message));
}

void TeamWorkspace::openCall(const QUrl &url)
{
#ifdef FORGE_EDITOR_HAS_WEBENGINE
    auto *dialog = new QDialog(this);
    dialog->setAttribute(Qt::WA_DeleteOnClose);
    dialog->setWindowTitle(QStringLiteral("JSON API Forge secure call"));
    ForgeEditorUi::resizeToFit(dialog, QSize(1100, 760));
    auto *layout = new QVBoxLayout(dialog);
    auto *profile = new QWebEngineProfile(dialog);
    profile->setHttpCacheType(QWebEngineProfile::MemoryHttpCache);
    profile->setPersistentCookiesPolicy(QWebEngineProfile::NoPersistentCookies);
    auto *view = new QWebEngineView(dialog);
    view->setPage(new QWebEnginePage(profile, view));
    view->setUrl(url);
    layout->addWidget(view);
    dialog->show();
#else
    if (!QDesktopServices::openUrl(url)) {
        emit statusMessage(QStringLiteral("Could not open the one-time call client URL."));
    } else {
        emit statusMessage(QStringLiteral("Opened the secure call client. Install Qt WebEngine to embed calls in the Editor."));
    }
#endif
}
