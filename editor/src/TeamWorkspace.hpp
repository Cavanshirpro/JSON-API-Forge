#pragma once

#include <QJsonArray>
#include <QJsonObject>
#include <QWidget>

class ApiClient;
class QComboBox;
class QLabel;
class QLineEdit;
class QListWidget;
class QTableWidget;
class QTextEdit;
class QTimer;
class QTreeWidget;
class QUrl;

class TeamWorkspace final : public QWidget {
    Q_OBJECT

public:
    explicit TeamWorkspace(ApiClient *api, QWidget *parent = nullptr);
    void setProject(const QString &project);
    void setCapabilities(const QJsonObject &capabilities);
    void refreshAll();
    void reset();

signals:
    void statusMessage(const QString &message);

private slots:
    void handleJson(const QString &operation, const QJsonObject &payload);
    void handleError(const QString &operation, int statusCode, const QString &message);
    void selectArea();
    void sendMessage();
    void createArea();
    void editProfile();
    void createRole();
    void manageMember();
    void createInvitation();
    void uploadAttachment();
    void downloadAttachment();
    void saveNote();
    void selectDatabaseTable();
    void startAudioCall();
    void startVideoCall();

private:
    void buildTeamTab(QWidget *tab);
    void buildSpacesTab(QWidget *tab);
    void buildDatabaseTab(QWidget *tab);
    void buildNotesTab(QWidget *tab);
    void buildAuditTab(QWidget *tab);
    void openCall(const QUrl &url);
    [[nodiscard]] QString currentAreaId() const;

    ApiClient *m_api = nullptr;
    QLabel *m_profile = nullptr;
    QLabel *m_projectLabel = nullptr;
    QTreeWidget *m_members = nullptr;
    QTreeWidget *m_roles = nullptr;
    QListWidget *m_areas = nullptr;
    QTreeWidget *m_messages = nullptr;
    QLineEdit *m_message = nullptr;
    QTreeWidget *m_attachments = nullptr;
    QTreeWidget *m_databaseTree = nullptr;
    QTableWidget *m_rows = nullptr;
    QTreeWidget *m_notes = nullptr;
    QLineEdit *m_noteTitle = nullptr;
    QTextEdit *m_noteBody = nullptr;
    QComboBox *m_noteVisibility = nullptr;
    QTreeWidget *m_audit = nullptr;
    QTimer *m_poll = nullptr;
    QString m_project;
    QJsonObject m_profileRecord;
    QJsonArray m_memberRecords;
    QJsonArray m_roleRecords;
    QJsonArray m_permissionCatalog;
    qsizetype m_maxAttachmentBytes = 16 * 1024 * 1024;
    bool m_databaseEnabled = false;
    bool m_collaborationEnabled = false;
    bool m_callsEnabled = false;
    int m_rank = 0;
};
